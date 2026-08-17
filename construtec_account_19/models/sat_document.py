import base64
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero

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
    numero_autorizacion_referencia = fields.Char(
        string='No. Autorización Documento de Referencia',
        help='Solo en Notas de Crédito/Débito (NCRE/NDEB): número de autorización del documento '
             'que esta nota corrige, tal como lo trae el complemento "Notas" del propio DTE. Se '
             'usa para vincular la nota con la factura ya convertida en Odoo, si ya existe.')
    motivo_ajuste_nota = fields.Char(
        string='Motivo de Ajuste', help='Campo "MotivoAjuste" del complemento de la nota, informativo.')
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
                'numero_autorizacion_referencia': vals.get('numero_autorizacion_referencia'),
                'motivo_ajuste_nota': vals.get('motivo_ajuste_nota'),
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
                'monto_petroleo': vals.get('monto_petroleo', 0.0),
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
            categorization_model = self.env['construtec.sat.categorization.rule']
            for line in document.line_ids:
                try:
                    catalog_model._sat_register_from_line(document, line)
                except Exception:
                    _logger.exception(
                        'No se pudo registrar en el catálogo de productos la línea "%s" del documento %s',
                        line.descripcion, numero_autorizacion,
                    )
                # Reglas de categorización (ver construtec.sat.categorization.rule):
                # solo aplican aquí las reglas SIN campo_condicion, porque los montos
                # de impuestos específicos (monto_petroleo, etc.) todavía no existen
                # en este punto - solo el Excel del portal los trae (ver
                # update_from_excel_row, que vuelve a intentarlo cuando ya están).
                try:
                    categorization_model._sat_apply_to_line(document, line)
                except Exception:
                    _logger.exception(
                        'No se pudo aplicar una regla de categorización a la línea "%s" del documento %s',
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

        # Recién aquí existen de verdad los montos de impuestos específicos
        # (monto_petroleo, etc. - ver EXCEL_HEADER_MAP en sat_document_import.py),
        # así que es el momento de reintentar las reglas de categorización que
        # tienen campo_condicion - al importar el XML esos montos siempre eran
        # cero. Solo si el documento sigue pendiente: si ya se convirtió, tocar
        # line_ids aquí no cambiaría nada en la factura ya generada.
        if document.state == 'pendiente':
            categorization_model = self.env['construtec.sat.categorization.rule']
            for line in document.line_ids:
                try:
                    categorization_model._sat_apply_to_line(document, line)
                except Exception:
                    _logger.exception(
                        'No se pudo aplicar una regla de categorización a la línea "%s" del documento %s',
                        line.descripcion, numero_autorizacion,
                    )
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

    def _sat_get_default_iva_tax(self):
        """Impuesto de IVA a asignar por defecto en action_convertir_a_factura cuando
        una línea trae monto_iva > 0 en el propio DTE pero no tiene tax_ids puesto a
        mano. Se busca por tipo/importe (12%, purchase en recibidas o sale en
        emitidas) en vez de por un external ID fijo: los impuestos que vienen de un
        account.chart.template (ej. l10n_gt) se instancian con un ID distinto por
        compañía, no hay un ID único reutilizable entre instalaciones. Si no
        encuentra ninguno (plan de cuentas de Guatemala no aplicado, o ningún
        impuesto de 12% configurado), regresa vacío - se deja sin tax_ids en vez de
        adivinar con otro impuesto, igual que el resto de este módulo.
        """
        type_tax_use = 'purchase' if self.direction == 'recibida' else 'sale'
        return self.env['account.tax'].search([
            ('company_id', '=', self.company_id.id),
            ('type_tax_use', '=', type_tax_use),
            ('amount_type', '=', 'percent'),
            ('amount', '=', 12.0),
        ], limit=1)

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

    def _sat_revertir_a_pendiente(self):
        """Si el asiento contable/orden de compra/pedido de venta generado a partir de
        este documento se borra, el documento vuelve a 'pendiente' - para que se
        pueda volver a convertir en vez de quedar con un estado "convertido" que
        apunta a un registro que ya no existe. Llamado desde los unlink() de
        account.move/purchase.order/sale.order en este módulo (cada uno tiene su
        propio sat_document_id de vuelta hacia acá) - nunca desde aquí mismo."""
        for document in self:
            if document.state == 'pendiente':
                continue
            document.write({
                'state': 'pendiente',
                'move_id': False,
                'purchase_order_id': False,
                'sale_order_id': False,
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
        es_nota_debito = self.tipo_dte == 'NDEB'
        if self.direction == 'recibida':
            move_type = 'in_refund' if es_nota_credito else 'in_invoice'
        else:
            move_type = 'out_refund' if es_nota_credito else 'out_invoice'

        # NCRE/NDEB: si el DTE trae a qué documento corrige (complemento "Notas",
        # ver _extraer_referencia_nota en sat_document_import.py) y ese documento
        # ya fue convertido en Odoo, se vincula el move resultante con el original
        # (reversed_entry_id / debit_origin_id) - ver CLAUDE.md para el porqué:
        # sin esto, la nota queda como un asiento suelto que hay que conciliar a
        # mano, y no hay garantía de que el usuario le ponga los mismos impuestos
        # que la factura original. Si no se encuentra (documento fuera de rango,
        # aún no importado, o el DTE no traía el complemento), se seguía haciendo
        # lo mismo que antes: se crea igual, sin vínculo, y se avisa por chatter.
        documento_referencia = self.env['construtec.sat.document']
        if (es_nota_credito or es_nota_debito) and self.numero_autorizacion_referencia:
            documento_referencia = self.search([
                ('numero_autorizacion', '=', self.numero_autorizacion_referencia),
                ('move_id', '!=', False),
            ], limit=1)

        # Si el documento de referencia tiene un único impuesto uniforme en todas
        # sus líneas, se usa como default para las líneas de la nota que todavía
        # no tengan tax_ids propios - nunca se pisa uno ya puesto a mano, y si la
        # factura original usó impuestos distintos por línea no se adivina cuál
        # corresponde a cuál (mismo criterio de "no adivinar" del resto del
        # módulo).
        tax_ids_default = False
        if documento_referencia and documento_referencia.move_id:
            lineas_producto = documento_referencia.move_id.invoice_line_ids.filtered(
                lambda l: l.display_type == 'product')
            combinaciones_impuestos = {tuple(sorted(l.tax_ids.ids)) for l in lineas_producto}
            if len(combinaciones_impuestos) == 1:
                tax_ids_default = list(next(iter(combinaciones_impuestos)))

        invoice_line_ids = []
        for linea in self.line_ids:
            if linea.tax_ids:
                tax_ids_linea = linea.tax_ids.ids
            elif tax_ids_default:
                tax_ids_linea = tax_ids_default
            elif not float_is_zero(linea.monto_iva, precision_digits=2):
                # La línea SÍ trae IVA en el propio DTE pero nadie le puso tax_ids
                # a mano todavía - se asigna la "etiqueta" de IVA correspondiente
                # (por dirección: crédito fiscal en recibidas, IVA por pagar en
                # emitidas) buscada por importe/tipo, no por un ID fijo de plantilla
                # (los impuestos generados desde account.chart.template tienen un
                # ID distinto por compañía, no uno fijo reutilizable entre
                # instalaciones). Los demás impuestos específicos del DTE
                # (monto_petroleo, etc.) NO se traducen a account.tax a propósito -
                # ver CLAUDE.md, sección de impuestos.
                tax_ids_linea = self._sat_get_default_iva_tax().ids
            else:
                tax_ids_linea = []
            vals = {
                'name': linea.descripcion,
                'quantity': linea.cantidad or 1.0,
                'price_unit': linea.precio_unitario,
                'account_id': linea.account_id.id,
                'tax_ids': [(6, 0, tax_ids_linea)],
                'analytic_distribution': linea.analytic_distribution,
            }
            if linea.product_id:
                vals['product_id'] = linea.product_id.id
            invoice_line_ids.append((0, 0, vals))

        fecha = self.fecha_certificacion.date()
        move_vals = {
            'move_type': move_type,
            'partner_id': self.partner_id.id,
            'invoice_date': fecha,
            'invoice_date_due': fecha,
            'date': fecha,
            'currency_id': self.currency_id.id,
            'ref': self.numero_documento or self.numero_autorizacion,
            'invoice_line_ids': invoice_line_ids,
            'sat_document_id': self.id,
        }
        if documento_referencia and documento_referencia.move_id:
            if es_nota_credito:
                move_vals['reversed_entry_id'] = documento_referencia.move_id.id
            elif es_nota_debito:
                move_vals['debit_origin_id'] = documento_referencia.move_id.id

        move = self.env['account.move'].create(move_vals)

        if (es_nota_credito or es_nota_debito) and not (documento_referencia and documento_referencia.move_id):
            move.message_post(body=self.env._(
                'No se encontró en Odoo el documento de referencia de esta nota '
                '(No. Autorización %(numero)s) - se creó sin vincular a la factura/nota '
                'original. Verifica manualmente que los impuestos coincidan y concilia '
                'a mano si corresponde.',
                numero=self.numero_autorizacion_referencia or self.env._('no informado en el DTE'),
            ))

        adjuntos = self.xml_attachment_id | self.pdf_attachment_id
        if adjuntos:
            adjuntos.write({'res_model': 'account.move', 'res_id': move.id})
        if self.pdf_attachment_id:
            move.message_main_attachment_id = self.pdf_attachment_id

        self.write({'move_id': move.id, 'state': 'convertido_factura'})

        return self.action_ver_factura()

    def action_convertir_a_factura_masivo(self):
        """Versión en lote de action_convertir_a_factura(), para seleccionar varios
        documentos SAT en la vista lista (compras, ventas, notas de crédito/débito -
        cualquier mezcla) y convertirlos de una vez, desde el menú Acciones. Reusa
        exactamente la misma lógica/validaciones por documento (move_type según
        dirección + tipo_dte, vínculo con el documento de referencia si aplica,
        etc.) - esto solo la llama en bucle.

        Un documento con error (ej. sin Cuenta Contable en alguna línea, o ya
        convertido) NO detiene el resto: se sigue con los demás y se reporta un
        resumen al final. Cada intento corre en su propio savepoint - si algo
        falla a nivel de base de datos (no solo una validación de UserError antes
        de tocar la BD), evita que ese fallo deje la transacción de todo el lote
        en un estado inválido para los documentos restantes.
        """
        convertidos = 0
        ya_convertidos = 0
        errores = []
        for document in self:
            if document.state != 'pendiente':
                ya_convertidos += 1
                continue
            try:
                with self.env.cr.savepoint():
                    document.action_convertir_a_factura()
                convertidos += 1
            except Exception as exc:
                _logger.exception(
                    'Conversión masiva a factura/nota: error al convertir %s', document.numero_autorizacion)
                errores.append(f'{document.numero_autorizacion}: {exc}')

        if errores:
            _logger.warning('Conversión masiva a factura/nota: %s errores.\n%s', len(errores), '\n'.join(errores))

        mensaje = (
            f"Convertidos: {convertidos} | "
            f"Ya convertidos (omitidos): {ya_convertidos} | "
            f"Errores: {len(errores)}"
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Conversión masiva a Factura/Nota',
                'message': mensaje,
                'sticky': bool(errores),
                'type': 'warning' if errores else 'success',
                # Sin esto, si el botón se dispara desde el formulario abierto de UNO
                # de los documentos convertidos, ese formulario se queda mostrando
                # los datos viejos (state='Pendiente', botones de conversión, etc.)
                # hasta que el usuario refresca la página a mano - una notificación
                # sola no hace que el cliente web vuelva a leer el registro.
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def action_aplicar_reglas_categorizacion(self):
        """Reintenta las Reglas de Categorización (construtec.sat.categorization.rule)
        sobre uno o varios documentos YA existentes - pensado para cuando se crea o
        edita una regla después de haber importado las facturas, o para documentos
        cuyo Excel llegó antes de que existiera la regla que necesitaban. Reusa
        _sat_apply_to_line() (mismo método que corre automático al importar), así
        que sigue sin pisar ningún account_id/tax_ids que una línea ya tenga.
        Solo tiene efecto en documentos 'pendiente' - uno ya convertido no cambia
        nada al tocar sus líneas."""
        categorization_model = self.env['construtec.sat.categorization.rule']
        documentos_procesados = 0
        lineas_actualizadas = 0
        for document in self:
            if document.state != 'pendiente':
                continue
            documentos_procesados += 1
            for line in document.line_ids:
                if categorization_model._sat_apply_to_line(document, line):
                    lineas_actualizadas += 1

        mensaje = f"Documentos revisados: {documentos_procesados} | Líneas actualizadas: {lineas_actualizadas}"
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Reglas de Categorización',
                'message': mensaje,
                'sticky': False,
                'type': 'success',
                # Igual que en action_convertir_a_factura_masivo: sin esto, el
                # formulario abierto del documento sigue mostrando las líneas sin
                # cuenta/impuestos aunque el backend sí las haya rellenado - hay
                # que forzar al cliente web a releer el registro.
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    _CAMPOS_RECTIFICABLES_DESDE_XML = [
        'tipo_dte', 'numero_autorizacion_referencia', 'motivo_ajuste_nota',
        'serie', 'numero_documento', 'fecha_certificacion',
        'nit_emisor', 'nombre_emisor', 'nombre_comercial_emisor', 'direccion_emisor',
        'codigo_establecimiento', 'nit_receptor', 'nombre_receptor',
        'nit_certificador', 'nombre_certificador', 'moneda_codigo',
        'monto_total', 'monto_iva', 'monto_petroleo', 'monto_turismo_hospedaje',
        'monto_turismo_pasajes', 'monto_timbre_prensa', 'monto_bomberos',
        'monto_tasa_municipal', 'monto_bebidas_alcoholicas', 'monto_tabaco',
        'monto_cemento', 'monto_bebidas_no_alcoholicas', 'monto_tarifa_portuaria',
    ]

    def action_rectificar_desde_xml(self):
        """Botón/acción "Rectificar desde XML": vuelve a leer el XML YA ADJUNTO a
        este documento con el parser actual (_parse_dte_xml) y refresca los campos
        de encabezado que salen de ahí - caso real que lo motivó: una factura de
        combustible cuyo Impuesto Petróleo quedó en 0.00 porque, al momento de
        importarla, el parser solo leía el TotalImpuesto de NombreCorto='IVA' del
        header y descartaba cualquier otro (como PETROLEO) - ya corregido en
        _parse_dte_xml, pero los documentos importados ANTES de ese fix se
        quedaron con el dato viejo. Sirve en general para cualquier corrección al
        parser, no solo esta.

        Deliberadamente NO toca numero_autorizacion (es la clave de búsqueda),
        direction, partner_id, state, ni line_ids - solo los campos listados en
        _CAMPOS_RECTIFICABLES_DESDE_XML, que son exactamente los que
        create_from_dte() ya escribe desde el mismo parser al crear el documento.
        No re-resuelve el contacto ni toca las líneas (cuentas/impuestos/producto
        ya asignados a mano) para no pisar decisiones ya tomadas por el usuario.

        Tras rectificar, reintenta las Reglas de Categorización sobre las líneas
        (por si un monto que antes estaba en 0, como monto_petroleo, ahora
        satisface la condición de alguna regla). Solo tiene efecto en documentos
        'pendiente' que además tengan un XML adjunto - se omiten sin error los
        que no.
        """
        # Import diferido (no al nivel del módulo): sat_document_import.py extiende
        # este mismo modelo (_inherit = 'construtec.sat.document') - un import al
        # nivel de módulo aquí arriba dispara su ejecución ANTES de que esta clase
        # termine de definirse con _name, y el registro de Odoo revienta con
        # "Model 'construtec.sat.document' does not exist in registry." (bug real,
        # encontrado y corregido durante el desarrollo de esta misma acción).
        from .sat_document_import import _parse_dte_xml

        categorization_model = self.env['construtec.sat.categorization.rule']
        rectificados = 0
        omitidos = 0
        errores = []
        for document in self:
            if document.state != 'pendiente' or not document.xml_attachment_id:
                omitidos += 1
                continue
            try:
                with self.env.cr.savepoint():
                    xml_bytes = base64.b64decode(document.xml_attachment_id.datas)
                    datos = _parse_dte_xml(xml_bytes)
                    vals = {
                        campo: datos[campo] for campo in self._CAMPOS_RECTIFICABLES_DESDE_XML
                        if campo in datos
                    }
                    document.write(vals)
                    for line in document.line_ids:
                        categorization_model._sat_apply_to_line(document, line)
                rectificados += 1
            except Exception as exc:
                _logger.exception('Rectificar desde XML: error en documento %s', document.numero_autorizacion)
                errores.append(f'{document.numero_autorizacion}: {exc}')

        mensaje = (
            f"Rectificados: {rectificados} | "
            f"Omitidos (ya convertidos o sin XML): {omitidos} | "
            f"Errores: {len(errores)}"
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Rectificar desde XML',
                'message': mensaje,
                'sticky': bool(errores),
                'type': 'warning' if errores else 'success',
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

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
