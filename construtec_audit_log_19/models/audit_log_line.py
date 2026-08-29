from odoo import fields, models


class AuditLogLine(models.Model):
    _name = 'construtec.audit.log.line'
    _description = 'Línea de Bitácora de Auditoría (cambio de un campo)'

    log_id = fields.Many2one(
        'construtec.audit.log', string='Bitácora', required=True, ondelete='cascade',
        readonly=True)
    field_name = fields.Char(string='Campo técnico', required=True, readonly=True)
    field_description = fields.Char(string='Campo', readonly=True)
    old_value = fields.Text(string='Valor anterior', readonly=True)
    new_value = fields.Text(string='Valor nuevo', readonly=True)
