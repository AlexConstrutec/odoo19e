from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrPayslipInputEmployee(models.Model):
    _name = 'hr.payslip.input.employee'
    _description = 'Otra Entrada de Nómina (Empleado)'
    _order = 'date_from desc'

    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True)
    version_id = fields.Many2one('hr.version', string='Contrato',
                                  default=lambda self: self.employee_id.version_id)
    input_type_id = fields.Many2one(
        'hr.payslip.input.type', string='Tipo de Entrada', required=True,
        help='Catálogo de otras entradas de nómina (bonificaciones, gratificaciones, ajustes, etc.).')
    code = fields.Char(related='input_type_id.code', string='Código', readonly=True)
    amount = fields.Float(string='Monto', required=True)
    name = fields.Char(string='Descripción')
    date_from = fields.Date(string='Fecha Desde', required=True)
    date_to = fields.Date(string='Fecha Hasta', required=True)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('approve', 'Aprobado'),
        ('refuse', 'Rechazado'),
    ], string='Estado', default='draft', tracking=True, copy=False)

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        for entry in self:
            entry.version_id = entry.employee_id.version_id

    @api.onchange('date_from')
    def _onchange_date_from(self):
        for entry in self:
            if entry.date_from and not entry.date_to:
                entry.date_to = entry.date_from

    def action_approve(self):
        self.write({'state': 'approve'})

    def action_refuse(self):
        self.write({'state': 'refuse'})

    def action_set_draft(self):
        self.write({'state': 'draft'})

    def unlink(self):
        for entry in self:
            if entry.state == 'approve':
                raise ValidationError(self.env._('No puede eliminar una entrada aprobada.'))
        return super().unlink()
