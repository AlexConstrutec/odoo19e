from odoo import _, api, fields, models


class AccountPaymentOrderBulkImportWizardLine(models.TransientModel):
    _name = 'account.payment.order.bulk.import.wizard.line'
    _description = 'Fila de Vista Previa - Importación Masiva de Órdenes de Pago'

    wizard_id = fields.Many2one(
        'account.payment.order.bulk.import.wizard', required=True, ondelete='cascade')
    incluir = fields.Boolean(string='Incluir', default=True)
    fila_excel = fields.Integer(string='Fila en Excel', readonly=True)
    grupo = fields.Char(
        string='Grupo', readonly=True,
        help='Filas con el mismo valor aquí se agrupan en UNA sola Orden de Pago al Aplicar.')

    solicitante_texto = fields.Char(string='Solicitante (texto original)', readonly=True)
    solicitante_id = fields.Many2one(
        'res.partner', string='Solicitante', domain="[('employee', '=', True)]")
    cuenta_analitica_texto = fields.Char(string='Cuenta Analítica (texto original)', readonly=True)
    analytic_account_id = fields.Many2one('account.analytic.account', string='Cuenta Analítica')
    fecha = fields.Date(string='Fecha')

    # Solo Viáticos.
    periodo_del = fields.Date(string='Período Del')
    periodo_al = fields.Date(string='Período Al')
    depositar_directo_tecnicos = fields.Boolean(string='¿Depositar Directo a Técnicos?')
    tecnico_texto = fields.Char(string='Técnico (texto original)', readonly=True)
    employee_partner_id = fields.Many2one(
        'res.partner', string='Técnico', domain="[('employee', '=', True)]")
    cantidad = fields.Integer(string='Cantidad', default=1)
    costo_individual = fields.Float(string='Costo Individual')
    total = fields.Float(string='Total', compute='_compute_total')
    cuenta_acreditar = fields.Char(string='Cuenta a Acreditar')
    banco = fields.Char(string='Banco')
    tipo_cuenta = fields.Selection(
        [('monetaria', 'Monetaria'), ('ahorro', 'Ahorro')], string='Tipo de Cuenta')

    # Solo Materiales.
    proveedor_materiales_name = fields.Char(string='Proveedor')
    material_description = fields.Char(string='Material / Descripción')
    uom_name = fields.Char(string='Unidad de Medida')
    qty = fields.Float(string='Cantidad', default=1)
    estimated_price = fields.Float(string='Precio Estimado')
    subtotal = fields.Float(string='Subtotal', compute='_compute_subtotal')

    estado = fields.Selection([
        ('ok', 'OK'),
        ('revisar', 'Revisar'),
    ], string='Estado', default='ok', readonly=True)
    motivo_revisar = fields.Char(string='Motivo', readonly=True)

    def _compute_total(self):
        for line in self:
            line.total = line.cantidad * line.costo_individual

    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.qty * line.estimated_price

    @api.onchange('solicitante_id', 'analytic_account_id', 'employee_partner_id')
    def _onchange_resolucion(self):
        """Si el usuario corrige a mano un campo que quedó sin resolver durante el análisis,
        recalcula `estado` en vivo - sin esto, una fila corregida en la vista previa seguiría
        marcada 'Revisar' y `action_aplicar()` la bloquearía igual."""
        for line in self:
            motivos = []
            if not line.solicitante_id:
                motivos.append(_('Falta Solicitante'))
            if not line.analytic_account_id:
                motivos.append(_('Falta Cuenta Analítica'))
            if line.wizard_id.tipo == 'anticipo_viaticos' and not line.employee_partner_id:
                motivos.append(_('Falta Técnico'))
            line.estado = 'revisar' if motivos else 'ok'
            line.motivo_revisar = '; '.join(motivos) if motivos else False
