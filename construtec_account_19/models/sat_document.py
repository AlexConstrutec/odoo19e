import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

TIPO_DTE_SELECTION = [
    ('FACT', 'FACT: Factura'),
    ('FCAM', 'FCAM: Factura Cambiaria'),
    ('FESP', 'FESP: Factura Especial'),
    ('FPEQ', 'FPEQ: Factura Pequeño Contribuyente'),
    ('FCAP', 'FCAP: Factura Cambiaria Pequeño Contribuyente'),
    ('NABN', 'NABN: Nota de Abono'),
    ('NCRE', 'NCRE: Nota de Crédito'),
    ('NDEB', 'NDEB: Nota de Débito'),
    ('RECI', 'RECI: Recibo'),
    ('CIVA', 'CIVA: Constancia de IVA'),
    ('FAPE', 'FAPE: Factura de Pequeño Contribuyente Especial'),
    # Los siguientes no se han visto todavía en un documento real (a diferencia
    # de los de arriba, verificados contra XML reales) - agregados por
    # adelantado según el catálogo público de la SAT para evitar el mismo
    # fallo de "Wrong value for tipo_dte" si aparecen. La SAT sigue agregando
    # tipos con el tiempo (p.ej. Decreto 31-2024), así que esta lista puede
    # seguir quedando corta - si falla uno nuevo, se agrega igual que estos.
    ('FEXP', 'FEXP: Factura Electrónica de Exportación'),
    ('RDON', 'RDON: Recibo por Donación'),
    ('RSP', 'RSP: Recibo por Servicios Profesionales'),
    ('NENV', 'NENV: Nota de Envío'),
    ('RECC', 'RECC: Recibo de Caja Chica'),
    ('REPA', 'REPA: Recibo de Pago'),
    ('CRET', 'CRET: Comprobante de Retención'),
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
    nit_contacto = fields.Char(
        related='partner_id.vat', string='NIT', store=True,
        help='NIT del Contacto ya resuelto (partner_id) - a diferencia de nit_emisor/nit_receptor, '
             'este siempre es "el NIT de la otra parte" sin importar la dirección del documento.')
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True, default=lambda self: self.env.company.id)
    currency_id = fields.Many2one(
        'res.currency', string='Moneda', default=lambda self: self.env.company.currency_id.id)
    moneda_codigo = fields.Char(
        string='Código Moneda DTE',
        help='Código de moneda tal como viene en el DTE (ej. GTQ), informativo - no cambia '
             'currency_id automáticamente.')
    monto_total = fields.Monetary(string='Monto Total', currency_field='currency_id')
    monto_iva = fields.Monetary(string='Monto IVA', currency_field='currency_id')
    monto_petroleo = fields.Monetary(string='Impuesto Petróleo', currency_field='currency_id')
    monto_turismo_hospedaje = fields.Monetary(string='Impuesto Turismo Hospedaje', currency_field='currency_id')
    monto_turismo_pasajes = fields.Monetary(string='Impuesto Turismo Pasajes', currency_field='currency_id')
    monto_timbre_prensa = fields.Monetary(string='Timbre de Prensa', currency_field='currency_id')
    monto_bomberos = fields.Monetary(string='Impuesto Bomberos', currency_field='currency_id')
    monto_tasa_municipal = fields.Monetary(string='Tasa Municipal', currency_field='currency_id')
    monto_bebidas_alcoholicas = fields.Monetary(string='Impuesto Bebidas Alcohólicas', currency_field='currency_id')
    monto_tabaco = fields.Monetary(string='Impuesto Tabaco', currency_field='currency_id')
    monto_cemento = fields.Monetary(string='Impuesto Cemento', currency_field='currency_id')
    monto_bebidas_no_alcoholicas = fields.Monetary(
        string='Impuesto Bebidas No Alcohólicas', currency_field='currency_id')
    monto_tarifa_portuaria = fields.Monetary(string='Tarifa Portuaria', currency_field='currency_id')
    codigo_establecimiento = fields.Char(string='Código Establecimiento')
    nombre_establecimiento = fields.Char(string='Nombre Establecimiento', help='Solo viene en el Excel del portal.')
    nombre_comercial_emisor = fields.Char(string='Nombre Comercial Emisor')
    direccion_emisor = fields.Char(string='Dirección Emisor')
    nit_certificador = fields.Char(string='NIT Certificador')
    nombre_certificador = fields.Char(string='Nombre Certificador')
    clasificacion_emisor = fields.Char(string='Clasificación Emisor', help='Solo viene en el Excel del portal.')
    exportacion = fields.Char(string='Exportación', help='Solo viene en el Excel del portal.')
    estado_sat = fields.Char(
        string='Estado en SAT',
        help='Vigente/Anulado según el Excel del portal al momento de importar. No se actualiza '
             'solo - si la SAT anula el documento después de importado, hay que reimportar el '
             'Excel de ese rango para refrescarlo.')
    anulado = fields.Boolean(string='Anulado')
    fecha_anulacion = fields.Datetime(string='Fecha de Anulación')
    xml_attachment_id = fields.Many2one('ir.attachment', string='XML', copy=False)
    pdf_attachment_id = fields.Many2one('ir.attachment', string='PDF', copy=False)
    cuenta_analitica_id = fields.Many2one('account.analytic.account', string='Cuenta Analítica')
    cuenta_contable_id = fields.Many2one('account.account', string='Cuenta Contable')
    line_ids = fields.One2many('construtec.sat.document.line', 'document_id', string='Líneas')
    state = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('convertido_factura', 'Convertido a Factura'),
        ('convertido_orden_compra', 'Convertido a Orden de Compra'),
        ('convertido_pedido_venta', 'Convertido a Pedido de Venta'),
    ], string='Estado', default='pendiente', copy=False)
    move_id = fields.Many2one('account.move', string='Factura Generada', readonly=True, copy=False)
    purchase_order_id = fields.Many2one(
        'purchase.order', string='Orden de Compra Generada', readonly=True, copy=False)
    sale_order_id = fields.Many2one(
        'sale.order', string='Pedido de Venta Generado', readonly=True, copy=False)

    _numero_autorizacion_uniq = models.Constraint(
        'unique(numero_autorizacion)',
        'Ya existe un documento SAT importado con este número de autorización.',
    )

    @api.onchange('cuenta_contable_id')
    def _onchange_cuenta_contable_id(self):
        """Feedback inmediato en el formulario, antes de guardar - ver el write()
        de más abajo para que la herencia también aplique al guardar/editar por
        API o edición masiva en la vista lista (el onchange por sí solo no
        cubre esos casos, solo la UI). Solo rellena líneas SIN cuenta propia -
        una línea que ya tiene su propia cuenta contable prevalece sobre la del
        encabezado (pedido explícito del usuario, ver CLAUDE.md)."""
        if self.cuenta_contable_id:
            for line in self.line_ids:
                if not line.account_id:
                    line.account_id = self.cuenta_contable_id

    def write(self, vals):
        res = super().write(vals)
        if 'cuenta_contable_id' in vals:
            for document in self:
                if document.cuenta_contable_id:
                    document.line_ids.filtered(lambda l: not l.account_id).write(
                        {'account_id': document.cuenta_contable_id.id})
        return res

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

        Devuelve un dict con al menos `state` ('success' | 'skipped_duplicate' |
        'nit_no_permitido') y `document_id`. Si algo falla, registra el error
        en la bitácora y vuelve a lanzar la excepción (el llamador ve el
        fallo vía el fault de XML-RPC/JSON-RPC).
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

        nits_permitidos = self._sat_nits_permitidos()
        nit_propio = vals.get('nit_receptor') if direction == 'recibida' else vals.get('nit_emisor')
        if nits_permitidos and (nit_propio or '').strip() not in nits_permitidos:
            log_model.create({
                'numero_autorizacion': numero_autorizacion,
                'direction': direction,
                'state': 'nit_no_permitido',
                'message': self.env._(
                    'NIT %(nit)s no está en la lista de NITs permitidos (%(permitidos)s).',
                    nit=nit_propio, permitidos=', '.join(sorted(nits_permitidos)),
                ),
            })
            return {'state': 'nit_no_permitido', 'document_id': False}

        try:
            if direction == 'recibida':
                nit_partner = vals.get('nit_emisor')
                nombre_partner = vals.get('nombre_emisor')
            else:
                nit_partner = vals.get('nit_receptor')
                nombre_partner = vals.get('nombre_receptor')
            partner = self._sat_find_or_create_partner(nit_partner, nombre_partner)

            line_ids = [(0, 0, {
                'numero_linea': line.get('numero_linea', 0),
                'bien_o_servicio': line.get('bien_o_servicio'),
                'descripcion': line.get('descripcion'),
                'cantidad': line.get('cantidad', 1.0),
                'precio_unitario': line.get('precio_unitario', 0.0),
                'monto_descuento': line.get('monto_descuento', 0.0),
                'otro_descuento': line.get('otro_descuento', 0.0),
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
                'nombre_comercial_emisor': vals.get('nombre_comercial_emisor'),
                'direccion_emisor': vals.get('direccion_emisor'),
                'codigo_establecimiento': vals.get('codigo_establecimiento'),
                'nit_receptor': vals.get('nit_receptor'),
                'nombre_receptor': vals.get('nombre_receptor'),
                'nit_certificador': vals.get('nit_certificador'),
                'nombre_certificador': vals.get('nombre_certificador'),
                'moneda_codigo': vals.get('moneda_codigo'),
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

            # Catálogo de referencia de precios de proveedor (ver
            # construtec.sat.product.catalog) - no debe impedir que el documento
            # SAT en sí se guarde si algo sale mal aquí (ej. carrera entre dos
            # importaciones concurrentes chocando con la restricción unique).
            catalog_model = self.env['construtec.sat.product.catalog']
            for line in document.line_ids:
                try:
                    catalog_model._sat_register_from_line(document, line)
                except Exception:
                    _logger.exception(
                        'No se pudo registrar en el catálogo de productos la línea "%s" del documento %s',
                        line.descripcion, numero_autorizacion,
                    )

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

    @api.model
    def update_from_excel_row(self, numero_autorizacion, vals):
        """Complementa un documento YA creado (por create_from_dte/create_from_dte_xml)
        con los campos que solo trae el Excel del portal - notablemente si fue
        anulado después de certificado, cosa que el XML nunca refleja. No crea
        nada nuevo: si no existe un documento con ese numero_autorizacion, no
        hace nada (silenciosamente) - el Excel es un resumen de MUCHOS
        documentos y no todos tienen por qué tener ya su XML importado.
        Devuelve True si actualizó algo, False si no encontró el documento.
        """
        document = self.search([('numero_autorizacion', '=', numero_autorizacion)], limit=1)
        if not document:
            return False
        document.write(vals)
        return True

    @api.model
    def _sat_nits_permitidos(self):
        """NIT "propio" aceptado al importar: el de la compañía activa
        (res.company.vat, la misma que se ve/edita en Ajustes > Compañías -
        no un parámetro aparte que haya que mantener sincronizado a mano). Un
        documento 'recibida' se rechaza si su nit_receptor no coincide, y uno
        'emitida' si su nit_emisor no coincide - así, si el outbox trae
        mezclados documentos de más de una cuenta SAT (ej. la personal del
        usuario y la de la empresa), solo entra a Odoo lo que de verdad es de
        esta compañía. Si la compañía no tiene NIT configurado, no se filtra
        nada.
        """
        company_vat = (self.env.company.vat or '').strip()
        return {company_vat} if company_vat else set()

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
                'analytic_distribution': linea.analytic_distribution,
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
                'analytic_distribution': linea.analytic_distribution,
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

    def action_convertir_a_pedido_venta(self):
        self.ensure_one()
        if self.direction != 'emitida':
            raise UserError(self.env._(
                'Solo los documentos Emitidos (ventas) se pueden convertir a Pedido de Venta.'))
        if self.state != 'pendiente':
            raise UserError(self.env._('Este documento ya fue convertido.'))
        if not self.partner_id:
            raise UserError(self.env._(
                'Define el Contacto (resuelto por NIT) antes de convertir a Pedido de Venta.'))
        if not self.line_ids:
            raise UserError(self.env._('El documento no tiene líneas que convertir.'))

        order_line_ids = []
        for linea in self.line_ids:
            producto = linea.product_id or self._sat_get_or_create_generic_product(linea.descripcion)
            order_line_ids.append((0, 0, {
                'product_id': producto.id,
                'name': linea.descripcion,
                'product_uom_qty': linea.cantidad or 1.0,
                'price_unit': linea.precio_unitario,
                'tax_ids': [(6, 0, linea.tax_ids.ids)],
                'analytic_distribution': linea.analytic_distribution,
            }))

        order = self.env['sale.order'].create({
            'partner_id': self.partner_id.id,
            'date_order': self.fecha_certificacion,
            'client_order_ref': self.numero_documento or self.numero_autorizacion,
            'currency_id': self.currency_id.id,
            'order_line': order_line_ids,
            'sat_document_id': self.id,
        })

        adjuntos = self.xml_attachment_id | self.pdf_attachment_id
        if adjuntos:
            adjuntos.write({'res_model': 'sale.order', 'res_id': order.id})

        self.write({'sale_order_id': order.id, 'state': 'convertido_pedido_venta'})

        return self.action_ver_pedido_venta()

    def action_ver_pedido_venta(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': self.sale_order_id.id,
            'target': 'current',
        }

    def _sat_get_or_create_generic_product(self, descripcion):
        """Usada al convertir a Orden de Compra o a Pedido de Venta: ambas líneas
        necesitan product_id obligatorio, pero las líneas del documento SAT lo dejan
        en blanco a propósito (mapeo manual, ver construtec.sat.document.line.product_id).
        Si falta, se busca/crea un producto genérico "de paso" por nombre exacto de la
        descripción del DTE, marcado como inventariable (is_storable) y habilitado tanto
        para compra como para venta, ya que el mismo producto genérico puede terminar
        usándose desde cualquiera de las dos conversiones según qué documento SAT lo cree.
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
            'sale_ok': True,
        })
        return template.product_variant_id


class ConstructecSatDocumentLine(models.Model):
    _name = 'construtec.sat.document.line'
    _inherit = ['analytic.mixin']
    _description = 'Línea de Documento SAT (DTE) importado'

    document_id = fields.Many2one(
        'construtec.sat.document', string='Documento SAT', required=True, ondelete='cascade')
    numero_autorizacion = fields.Char(
        related='document_id.numero_autorizacion', string='No. Autorización SAT', store=True)
    partner_id = fields.Many2one(
        related='document_id.partner_id', string='Contacto', store=True)
    nit_contacto = fields.Char(related='document_id.nit_contacto', string='NIT', store=True)
    fecha_certificacion = fields.Datetime(
        related='document_id.fecha_certificacion', string='Fecha de Certificación', store=True)
    numero_linea = fields.Integer(string='No. Línea')
    bien_o_servicio = fields.Selection(
        [('B', 'Bien'), ('S', 'Servicio')], string='Bien/Servicio')
    descripcion = fields.Char(string='Descripción', required=True)
    cantidad = fields.Float(string='Cantidad', default=1.0)
    precio_unitario = fields.Float(string='Precio Unitario')
    monto_descuento = fields.Float(
        string='Descuento',
        help='Monto de descuento tal como viene en el DTE. Es solo informativo: no se traduce '
             'automáticamente al campo "Descuento" (%) de la línea de factura de Odoo.')
    otro_descuento = fields.Float(
        string='Otro Descuento', help='Campo "OtrosDescuento" del DTE, informativo.')
    monto_iva = fields.Float(string='IVA')
    monto_total = fields.Float(string='Total')
    product_id = fields.Many2one('product.product', string='Producto')
    account_id = fields.Many2one(
        'account.account', string='Cuenta Contable',
        help='Requerida para poder convertir el documento a factura. Se completa manualmente al '
             'revisar el documento importado - n8n no intenta mapearla automáticamente.')
    tax_ids = fields.Many2many('account.tax', string='Impuestos')

    @api.model_create_multi
    def create(self, vals_list):
        """Si se agrega una línea nueva a mano (ej. dividiendo una línea existente)
        y el encabezado ya tiene cuenta_contable_id, la línea nueva la hereda por
        defecto - sin pisar un account_id que el propio vals ya traiga explícito.
        El caso masivo (crear todas las líneas al importar el documento) no se ve
        afectado: en ese momento cuenta_contable_id todavía no está puesto."""
        for vals in vals_list:
            if not vals.get('account_id') and vals.get('document_id'):
                document = self.env['construtec.sat.document'].browse(vals['document_id'])
                if document.cuenta_contable_id:
                    vals['account_id'] = document.cuenta_contable_id.id
        return super().create(vals_list)
