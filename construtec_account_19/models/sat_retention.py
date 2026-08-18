import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ConstructecSatRetention(models.Model):
    _name = 'construtec.sat.retention'
    _description = 'Constancia de Retención de IVA (Agencia Virtual SAT)'
    _order = 'fecha_emision desc'

    numero_constancia = fields.Char(
        string='No. de Constancia', required=True, copy=False, index=True,
        help='Campo "Número de Constancia" del PDF SAT-2229 - único, evita reimportar la misma constancia.')
    fecha_emision = fields.Date(string='Fecha de Emisión')
    nit_contribuyente = fields.Char(
        string='NIT Contribuyente', help='NIT de quien recibió la retención - debería ser el de Construtec, '
                                          'ya que esta pantalla es "Retenciones Recibidas".')
    nombre_contribuyente = fields.Char(string='Nombre Contribuyente')
    nit_agente_retenedor = fields.Char(string='NIT Agente Retenedor')
    nombre_agente_retenedor = fields.Char(string='Nombre Agente Retenedor')
    agente_retenedor_partner_id = fields.Many2one(
        'res.partner', string='Contacto Agente Retenedor',
        help='Resuelto por NIT contra contactos ya existentes (solo búsqueda, no se crea uno nuevo aquí - '
             'este campo es informativo/de reporte, a diferencia de partner_id en construtec.sat.document que '
             'sí se resuelve/crea porque de ahí sale la factura). Corrige a mano si no encontró el contacto '
             'correcto o si no encontró ninguno.')
    tipo_agente_retencion = fields.Char(string='Tipo de Agente de Retención')
    cantidad_facturas = fields.Integer(
        string='Cantidad de Facturas', help='Campo "Cantidad de Facturas" del PDF - para contrastar contra la '
                                             'cantidad real de líneas vinculadas.')
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True, default=lambda self: self.env.company.id)
    currency_id = fields.Many2one(
        'res.currency', string='Moneda', default=lambda self: self.env.company.currency_id.id)
    monto_importe_neto_total = fields.Monetary(
        string='Importe Neto Total (líneas)', currency_field='currency_id',
        compute='_compute_totales_lineas', store=True)
    monto_retencion_total = fields.Monetary(
        string='Retención Total (líneas)', currency_field='currency_id',
        compute='_compute_totales_lineas', store=True)
    monto_retencion_pdf = fields.Monetary(
        string='Retención Total (según PDF)', currency_field='currency_id',
        help='Valor de la fila "TOTAL" leído directamente del PDF - se guarda aparte del calculado desde las '
             'líneas (monto_retencion_total) para poder detectar una discrepancia si el parseo de alguna línea '
             'salió mal.')
    pdf_attachment_id = fields.Many2one('ir.attachment', string='PDF', copy=False)
    requiere_revision_manual = fields.Boolean(
        string='Requiere Revisión Manual',
        help='El PDF trae más de 1 factura y el layout de la tabla DETALLE no se pudo emparejar automáticamente '
             'con los pares Serie/Número (aún no se ha verificado contra un PDF real con varias facturas) - '
             'revisa manualmente los montos por línea.')
    line_ids = fields.One2many('construtec.sat.retention.line', 'retention_id', string='Facturas Cubiertas')
    state = fields.Selection([
        ('pendiente', 'Pendiente de Vincular'),
        ('parcial', 'Parcialmente Vinculada'),
        ('vinculada', 'Vinculada'),
    ], string='Estado', compute='_compute_state', store=True)

    _numero_constancia_uniq = models.Constraint(
        'unique(numero_constancia)',
        'Ya existe una constancia de retención importada con este número.',
    )

    @api.depends('line_ids.monto_importe_neto', 'line_ids.monto_retencion')
    def _compute_totales_lineas(self):
        for retention in self:
            retention.monto_importe_neto_total = sum(retention.line_ids.mapped('monto_importe_neto'))
            retention.monto_retencion_total = sum(retention.line_ids.mapped('monto_retencion'))

    @api.depends('line_ids.sat_document_id')
    def _compute_state(self):
        for retention in self:
            documentos = retention.line_ids.mapped('sat_document_id')
            if not retention.line_ids or not documentos:
                retention.state = 'pendiente'
            elif len(documentos) == len(retention.line_ids):
                retention.state = 'vinculada'
            else:
                retention.state = 'parcial'

    def action_vincular_facturas(self):
        """Reintenta resolver sat_document_id en las líneas que aún no lo tengan - por
        ejemplo, si la constancia se importó ANTES que el documento SAT (emitida)
        correspondiente. Fills-blanks-only: nunca reemplaza un vínculo ya resuelto a
        mano o automáticamente."""
        actualizadas = 0
        for retention in self:
            for line in retention.line_ids.filtered(lambda l: not l.sat_document_id):
                line._sat_buscar_documento()
                if line.sat_document_id:
                    actualizadas += 1
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._('Vincular Facturas'),
                'message': self.env._('Líneas vinculadas: %(n)s', n=actualizadas),
                'type': 'success',
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    @api.model
    def _sat_find_partner_by_nit(self, nit):
        if not nit:
            return self.env['res.partner']
        return self.env['res.partner'].search([('vat', '=', nit)], limit=1)

    @api.model
    def create_from_pdf(self, pdf_base64, pdf_filename=None):
        """Punto de entrada para importar una Constancia de Retención de IVA desde su
        PDF (formulario SAT-2229) - ver sat_retention_import.py::_parse_constancia_pdf
        para el detalle del parseo. Idempotente por numero_constancia, igual que
        construtec.sat.document.create_from_dte.

        Devuelve un dict con `state` ('success' | 'skipped_duplicate') y
        `retention_id`.
        """
        from .sat_retention_import import _parse_constancia_pdf
        import base64

        pdf_bytes = base64.b64decode(pdf_base64)
        vals = _parse_constancia_pdf(pdf_bytes)

        numero_constancia = vals.get('numero_constancia')
        existing = self.search([('numero_constancia', '=', numero_constancia)], limit=1)
        if existing:
            return {'state': 'skipped_duplicate', 'retention_id': existing.id}

        agente_partner = self._sat_find_partner_by_nit(vals.get('nit_agente_retenedor'))

        retention = self.create({
            'numero_constancia': numero_constancia,
            'fecha_emision': vals.get('fecha_emision'),
            'nit_contribuyente': vals.get('nit_contribuyente'),
            'nombre_contribuyente': vals.get('nombre_contribuyente'),
            'nit_agente_retenedor': vals.get('nit_agente_retenedor'),
            'nombre_agente_retenedor': vals.get('nombre_agente_retenedor'),
            'agente_retenedor_partner_id': agente_partner.id if agente_partner else False,
            'tipo_agente_retencion': vals.get('tipo_agente_retencion'),
            'cantidad_facturas': vals.get('cantidad_facturas', 0),
            'monto_retencion_pdf': vals.get('monto_retencion_pdf', 0.0),
            'requiere_revision_manual': vals.get('requiere_revision_manual', False),
            'line_ids': [(0, 0, {
                'serie': linea.get('serie'),
                'numero_factura': linea.get('numero_factura'),
                'concepto': linea.get('concepto'),
                'tarifa': linea.get('tarifa', 0.0),
                'monto_importe_neto': linea.get('monto_importe_neto', 0.0),
                'monto_retencion': linea.get('monto_retencion', 0.0),
            }) for linea in vals.get('lines', [])],
        })

        if pdf_base64:
            attachment = self.env['ir.attachment'].create({
                'name': pdf_filename or f'{numero_constancia}.pdf',
                'datas': pdf_base64,
                'res_model': 'construtec.sat.retention',
                'res_id': retention.id,
            })
            retention.pdf_attachment_id = attachment.id

        return {'state': 'success', 'retention_id': retention.id}


class ConstructecSatRetentionLine(models.Model):
    _name = 'construtec.sat.retention.line'
    _description = 'Factura cubierta por una Constancia de Retención de IVA'

    retention_id = fields.Many2one(
        'construtec.sat.retention', string='Constancia', required=True, ondelete='cascade')
    serie = fields.Char(string='Serie')
    numero_factura = fields.Char(string='Número de Factura')
    concepto = fields.Char(string='Concepto')
    tarifa = fields.Float(string='Tarifa (%)')
    currency_id = fields.Many2one(related='retention_id.currency_id', string='Moneda', store=True)
    monto_importe_neto = fields.Monetary(string='Importe Neto del Bien', currency_field='currency_id')
    monto_retencion = fields.Monetary(string='Retención', currency_field='currency_id')
    sat_document_id = fields.Many2one(
        'construtec.sat.document', string='Documento SAT',
        domain="[('direction', '=', 'emitida')]",
        help='Resuelto automáticamente por Serie + Número de Documento contra construtec.sat.document con '
             'direction=emitida - esta pantalla es "Retenciones Recibidas": Construtec es quien recibió la '
             'retención en una venta propia, nunca en una compra. Corrige a mano si resolvió el documento '
             'incorrecto, o si no encontró ninguno (por ejemplo, si el documento SAT todavía no se ha '
             'importado - en ese caso usa el botón "Vincular Facturas" del encabezado una vez exista).')
    move_id = fields.Many2one(related='sat_document_id.move_id', string='Factura', store=True)
    partner_id = fields.Many2one(related='sat_document_id.partner_id', string='Cliente', store=True)

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        for line in lines:
            if not line.sat_document_id:
                line._sat_buscar_documento()
        return lines

    def _sat_buscar_documento(self):
        self.ensure_one()
        if not self.serie or not self.numero_factura:
            return
        documento = self.env['construtec.sat.document'].search([
            ('direction', '=', 'emitida'),
            ('serie', '=', self.serie),
            ('numero_documento', '=', self.numero_factura),
        ], limit=1)
        if documento:
            self.sat_document_id = documento.id
