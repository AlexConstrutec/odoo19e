from odoo import fields, models
from odoo.exceptions import UserError


class AuditLog(models.Model):
    _name = 'construtec.audit.log'
    _description = 'Bitácora de Auditoría'
    _order = 'create_date desc, id desc'
    _rec_name = 'res_name'

    rule_id = fields.Many2one(
        'construtec.audit.log.rule', string='Regla', ondelete='set null', readonly=True)
    res_model = fields.Char(string='Modelo', required=True, readonly=True, index=True)
    res_id = fields.Integer(string='ID del registro', required=True, readonly=True, index=True)
    res_name = fields.Char(string='Registro', readonly=True)
    method = fields.Selection(
        [('create', 'Creación'), ('write', 'Modificación'), ('unlink', 'Eliminación')],
        string='Operación', required=True, readonly=True, index=True)
    user_id = fields.Many2one('res.users', string='Usuario', readonly=True)
    line_ids = fields.One2many(
        'construtec.audit.log.line', 'log_id', string='Cambios de campos', readonly=True)

    def action_open_record(self):
        self.ensure_one()
        if self.method == 'unlink':
            raise UserError(self.env._('Este registro ya fue eliminado - no se puede abrir.'))
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.res_model,
            'res_id': self.res_id,
            'view_mode': 'form',
            'target': 'current',
        }
