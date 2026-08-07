from odoo import api, fields, models
from odoo.exceptions import UserError

TIPO_DTE_SELECTION = [
    ('FACT', 'FACT: Factura'),
    ('FCAM', 'FCAM: Factura Cambiaria'),
    ('FESP', 'FESP: Factura Especial'),
    ('FPEQ', 'FPEQ: Factura Pequeño Contribuyente'),
    ('FCAP', 'FCAP: Factura Cambiaria Pequeño Contribuyente'),
    ('NABN', 'NABN: Nota de Abono'),
    ('NCRE', 'NCRE: Nota de Crédito'),
    ('NDEB', 'NDEB: Nota de Débito'),
]

# Solo la Nota de Crédito se contabiliza como in_refund/out_refund (disminuye lo adeudado).
# La Nota de Débito NO es un refund: aumenta lo adeudado, así que se contabiliza como una
# factura/bill normal adicional (in_invoice/out_invoice) - igual que Odoo maneja sus notas de
# débito nativas via el wizard de "Debit Note" (crea una factura nueva, no una nota de crédito).
TIPOS_DTE_NOTA_CREDITO = ('NCRE',)


class ConstructecSatDocument(models.Model):
    _name = 'construtec.sat.document'
    _description = 'Documento SAT (DTE) importado desde Agencia Virtual'
    _order = 'fecha_certificacion desc'

    direction = fields.Selection([
        ('recibida', 'Recibida'),
        ('emitida', 'Emitida'),
    ], string='Dirección', required=True)
    numero_autorizacion = fields.Char(
        string='No. Autorización SAT', required=True, copy=False, index=True,
        help='UUID de autorización del DTE, tal como lo certifica la SAT. Es el identificador '
             'único usado para evitar reimportar el mismo documento.')
    tipo_dte = fields.Selection(TIPO_DTE_SELECTION, string='Tipo DTE', required=True)
    serie = fields.Char(string='Serie')
    numero_documento = fields.Char(string='Número de Documento')
    fecha_certificacion = fields.Datetime(string='Fecha de Certificación', required=True)
    nit_emisor = fields.Char(string='NIT Emisor')
    nombre_emisor = fields.Char(string='Nombre Emisor')
    nit_receptor = fields.Char(string='NIT Receptor')
    nombre_receptor = fields.Char(string='Nombre Receptor')
    partner_id = fields.Many2one(
        'res.partner', string='Contacto',
        help='Resuelto por NIT (emisor si es Recibida, receptor si es Emitida). Revisa/corrige '
             'antes de convertir a factura si no es el contacto correcto.')
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True, default=lambda self: self.env.company.id)
    currency_id = fields.Many2one(
        'res.currency', string='Moneda', default=lambda self: self.env.company.currency_id.id)
    monto_total = fields.Monetary(string='Monto Total', currency_field='currency_id')
    monto_iva = fields.Monetary(string='Monto IVA', currency_field='currency_id')
    xml_attachment_id = fields.Many2one('ir.attachment', string='XML', copy=False)
    pdf_attachment_id = fields.Many2one('ir.attachment', string='PDF', copy=False)
    line_ids = fields.One2many('construtec.sat.document.line', 'document_id', string='Líneas')
    state = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('convertido_factura', 'Convertido a Factura'),
        ('convertido_orden_compra', 'Convertido a Orden de Compra'),
    ], string='Estado', default='pendiente', copy=False)
    move_id = fields.Many2one('account.move', string='Factura Generada', readonly=True, copy=False)
    purchase_order_id = fields.Many2one(
        'purchase.order', string='Orden de Compra Generada', readonly=True, copy=False)

    _numero_autorizacion_uniq = models.Constraint(
        'unique(numero_autorizacion)',
        'Ya existe un documento SAT importado con este número de autorización.',
    )

    @api.model
    def create_from_dte(self, vals):
        """Punto de entrada único para el API externo (n8n, script, etc.).

        `vals` trae los mismos nombres de campo que el encabezado
        (direction, numero_autorizacion, tipo_dte, serie, numero_documento,
        fecha_certificacion, nit_emisor, nombre_emisor, nit_receptor,
        nombre_receptor, monto_total, monto_iva), más:
          - `lines`: lista de dicts con los campos de
            construtec.sat.document.line (descripcion, cantidad,
            precio_unitario, monto_descuento, monto_iva, monto_total).
          - `xml_filename` / `xml_base64` y `pdf_filename` / `pdf_base64`:
            adjuntos, opcionales.

        Resuelve/crea el res.partner por NIT (emisor si la dirección es
        'recibida', receptor si es 'emitida' — mismo criterio que ya
        documentaba el CLAUDE.md del módulo), crea el encabezado con sus
        líneas y adjuntos en una sola transacción, y deja constancia en
        construtec.sat.import.log. Es idempotente: si numero_autorizacion ya
        existe, no crea nada nuevo y responde state=skipped_duplicate — así
        el llamador puede reintentar sin miedo a duplicar.

        Devuelve un dict con al menos `state` ('success' | 'skipped_duplicate')
        y `document_id`. Si algo falla, registra el error en la bitácora y
        vuelve a lanzar la excepción (el llamador ve el fallo vía el fault de
        XML-RPC/JSON-RPC).
        """
        numero_autorizacion = vals.get('numero_autorizacion')
        direction = vals.get('direction')
        log_model = self.env['construtec.sat.import.log']

        existing = self.search([('numero_autorizacion', '=', numero_autorizacion)], limit=1)
        if existing:
            log_model.create({
                'numero_autorizacion': numero_autorizacion,
                'direction': direction,
                'state': 'skipped_duplicate',
                'message': self.env._('Ya existía un documento con este número de autorización.'),
                'document_id': existing.id,
            })
            return {'state': 'skipped_duplicate', 'document_id': existing.id}

        try:
            if direction == 'recibida':
                nit_partner = vals.get('nit_emisor')
                nombre_partner = vals.get('nombre_emisor')
            else:
                nit_partner = vals.get('nit_receptor')
                nombre_partner = vals.get('nombre_receptor')
            partner = self._sat_find_or_create_partner(nit_partner, nombre_partner)

            line_ids = [(0, 0, {
                'descripcion': line.get('descripcion'),
                'cantidad': line.get('cantidad', 1.0),
                'precio_unitario': line.get('precio_unitario', 0.0),
                'monto_descuento': line.get('monto_descuento', 0.0),
                'monto_iva': line.get('monto_iva', 0.0),
                'monto_total': line.get('monto_total', 0.0),
            }) for line in vals.get('lines', [])]

            document = self.create({
                'direction': direction,
                'numero_autorizacion': numero_autorizacion,
                'tipo_dte': vals.get('tipo_dte'),
                'serie': vals.get('serie'),
                'numero_documento': vals.get('numero_documento'),
                'fecha_certificacion': vals.get('fecha_certificacion'),
                'nit_emisor': vals.get('nit_emisor'),
                'nombre_emisor': vals.get('nombre_emisor'),
                'nit_receptor': vals.get('nit_receptor'),
                'nombre_receptor': vals.get('nombre_receptor'),
                'partner_id': partner.id if partner else False,
                'monto_total': vals.get('monto_total', 0.0),
                'monto_iva': vals.get('monto_iva', 0.0),
                'line_ids': line_ids,
            })

            xml_attachment = self._sat_create_attachment(
                document, vals.get('xml_filename'), vals.get('xml_base64'))
            pdf_attachment = self._sat_create_attachment(
                document, vals.get('pdf_filename'), vals.get('pdf_base64'))
            if xml_attachment or pdf_attachment:
                document.write({
                    'xml_attachment_id': xml_attachment.id if xml_attachment else False,
                    'pdf_attachment_id': pdf_attachment.id if pdf_attachment else False,
                })

            log_model.create({
                'numero_autorizacion': numero_autorizacion,
                'direction': direction,
                'state': 'success',
                'document_id': document.id,
            })
            return {'state': 'success', 'document_id': document.id, 'partner_id': partner.id if partner else False}

        except Exception as exc:
            log_model.create({
                'numero_autorizacion': numero_autorizacion,
                'direction': direction,
                'state': 'error',
                'message': str(exc),
            })
            raise

    def _sat_find_or_create_partner(self, nit, name):
        if not nit:
            return self.env['res.partner']
        partner = self.env['res.partner'].search([('vat', '=', nit)], limit=1)
        if partner:
            return partner
        country_gt = self.env['res.country'].search([('code', '=', 'GT')], limit=1)
        return self.env['res.partner'].create({
            'name': name or nit,
            'vat': nit,
            'country_id': country_gt.id if country_gt else False,
        })

    def _sat_create_attachment(self, document, filename, base64_data):
        if not base64_data:
            return self.env['ir.attachment']
        return self.env['ir.attachment'].create({
            'name': filename or document.numero_autorizacion,
            'datas': base64_data,
            'res_model': 'construtec.sat.document',
            'res_id': document.id,
        })

    def action_convertir_a_factura(self):
        self.ensure_one()
        if self.state != 'pendiente':
            raise UserError(self.env._('Este documento ya fue convertido.'))
        if not self.partner_id:
            raise UserError(self.env._(
                'Define el Contacto (resuelto por NIT) antes de convertir a factura.'))
        if not self.line_ids:
            raise UserError(self.env._('El documento no tiene líneas que convertir.'))
        lineas_sin_cuenta = self.line_ids.filtered(lambda l: not l.account_id)
        if lineas_sin_cuenta:
            raise UserError(self.env._(
                'Completa la Cuenta Contable de todas las líneas antes de convertir.'))

        es_nota_credito = self.tipo_dte in TIPOS_DTE_NOTA_CREDITO
        if self.direction == 'recibida':
            move_type = 'in_refund' if es_nota_credito else 'in_invoice'
        else:
            move_type = 'out_refund' if es_nota_credito else 'out_invoice'

        invoice_line_ids = []
        for linea in self.line_ids:
            vals = {
                'name': linea.descripcion,
                'quantity': linea.cantidad or 1.0,
                'price_unit': linea.precio_unitario,
                'account_id': linea.account_id.id,
                'tax_ids': [(6, 0, linea.tax_ids.ids)],
            }
            if linea.product_id:
                vals['product_id'] = linea.product_id.id
            invoice_line_ids.append((0, 0, vals))

        fecha = self.fecha_certificacion.date()
        move = self.env['account.move'].create({
            'move_type': move_type,
            'partner_id': self.partner_id.id,
            'invoice_date': fecha,
            'date': fecha,
            'currency_id': self.currency_id.id,
            'ref': self.numero_documento or self.numero_autorizacion,
            'invoice_line_ids': invoice_line_ids,
            'sat_document_id': self.id,
        })

        adjuntos = self.xml_attachment_id | self.pdf_attachment_id
        if adjuntos:
            adjuntos.write({'res_model': 'account.move', 'res_id': move.id})
        if self.pdf_attachment_id:
            move.message_main_attachment_id = self.pdf_attachment_id

        self.write({'move_id': move.id, 'state': 'convertido_factura'})

        return self.action_ver_factura()

    def action_ver_factura(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.move_id.id,
            'target': 'current',
        }

    def action_convertir_a_orden_compra(self):
        self.ensure_one()
        if self.direction != 'recibida':
            raise UserError(self.env._(
                'Solo los documentos Recibidos (compras) se pueden convertir a Orden de Compra.'))
        if self.state != 'pendiente':
            raise UserError(self.env._('Este documento ya fue convertido.'))
        if not self.partner_id:
            raise UserError(self.env._(
                'Define el Contacto (resuelto por NIT) antes de convertir a Orden de Compra.'))
        if not self.line_ids:
            raise UserError(self.env._('El documento no tiene líneas que convertir.'))

        order_line_ids = []
        for linea in self.line_ids:
            producto = linea.product_id or self._sat_get_or_create_generic_product(linea.descripcion)
            order_line_ids.append((0, 0, {
                'product_id': producto.id,
                'name': linea.descripcion,
                'product_qty': linea.cantidad or 1.0,
                'price_unit': linea.precio_unitario,
                'tax_ids': [(6, 0, linea.tax_ids.ids)],
            }))

        order = self.env['purchase.order'].create({
            'partner_id': self.partner_id.id,
            'date_order': self.fecha_certificacion,
            'partner_ref': self.numero_documento or self.numero_autorizacion,
            'currency_id': self.currency_id.id,
            'order_line': order_line_ids,
            'sat_document_id': self.id,
        })

        adjuntos = self.xml_attachment_id | self.pdf_attachment_id
        if adjuntos:
            adjuntos.write({'res_model': 'purchase.order', 'res_id': order.id})

        self.write({'purchase_order_id': order.id, 'state': 'convertido_orden_compra'})

        return self.action_ver_orden_compra()

    def action_ver_orden_compra(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'view_mode': 'form',
            'res_id': self.purchase_order_id.id,
            'target': 'current',
        }

    def _sat_get_or_create_generic_product(self, descripcion):
        """Usada solo al convertir a Orden de Compra: las líneas de OC necesitan
        product_id obligatorio, pero las líneas del documento SAT lo dejan en blanco
        a propósito (mapeo manual, ver construtec.sat.document.line.product_id). Si
        falta, se busca/crea un producto genérico "de paso" por nombre exacto de la
        descripción del DTE, marcado como inventariable (is_storable) para que sí
        cuente en control de inventario.
        """
        producto = self.env['product.product'].search([('name', '=', descripcion)], limit=1)
        if producto:
            return producto
        # is_storable vive en product.template, no en product.product: hay que crear la
        # plantilla y tomar su variante (Odoo la crea sola al no haber atributos/variantes).
        template = self.env['product.template'].create({
            'name': descripcion,
            'type': 'consu',
            'is_storable': True,
            'purchase_ok': True,
            'sale_ok': False,
        })
        return template.product_variant_id


class ConstructecSatDocumentLine(models.Model):
    _name = 'construtec.sat.document.line'
    _description = 'Línea de Documento SAT (DTE) importado'

    document_id = fields.Many2one(
        'construtec.sat.document', string='Documento SAT', required=True, ondelete='cascade')
    descripcion = fields.Char(string='Descripción', required=True)
    cantidad = fields.Float(string='Cantidad', default=1.0)
    precio_unitario = fields.Float(string='Precio Unitario')
    monto_descuento = fields.Float(
        string='Descuento',
        help='Monto de descuento tal como viene en el DTE. Es solo informativo: no se traduce '
             'automáticamente al campo "Descuento" (%) de la línea de factura de Odoo.')
    monto_iva = fields.Float(string='IVA')
    monto_total = fields.Float(string='Total')
    product_id = fields.Many2one('product.product', string='Producto')
    account_id = fields.Many2one(
        'account.account', string='Cuenta Contable',
        help='Requerida para poder convertir el documento a factura. Se completa manualmente al '
             'revisar el documento importado - n8n no intenta mapearla automáticamente.')
    tax_ids = fields.Many2many('account.tax', string='Impuestos')
