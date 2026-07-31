from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrAbsenceLine(models.Model):
    _name = 'hr.absence.line'
    _description = 'Ausencia'
    _order = 'date_from desc'

    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True)
    version_id = fields.Many2one('hr.version', string='Contrato',
                                  default=lambda self: self.employee_id.version_id)
    work_entry_type_id = fields.Many2one(
        'hr.work.entry.type', string='Tipo de Ausencia', required=True,
        domain=[('is_leave', '=', True)],
        help='Reutiliza los mismos tipos de entrada de trabajo que ya leen las reglas '
             'salariales por código (AU_IGSS, AU_VP, LEAVE110, etc.).')
    date_from = fields.Date(string='Fecha Desde', required=True)
    date_to = fields.Date(string='Fecha Hasta', required=True)
    number_of_days = fields.Float(string='Cantidad de Días', compute='_compute_number_of_days', store=True)
    date_payroll = fields.Date(
        string='Fecha a Descontar en Nómina', required=True,
        help='Determina en qué período de nómina se descuenta esta ausencia '
             '(normalmente igual a la fecha desde, salvo casos de ausencias '
             'reportadas con rezago).')
    reason = fields.Text(string='Motivo')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('approve', 'Aprobado'),
        ('refuse', 'Rechazado'),
    ], string='Estado', default='draft', tracking=True, copy=False)

    @api.depends('date_from', 'date_to')
    def _compute_number_of_days(self):
        for line in self:
            if line.date_from and line.date_to:
                line.number_of_days = (line.date_to - line.date_from).days + 1
            else:
                line.number_of_days = 0

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        for line in self:
            line.version_id = line.employee_id.version_id

    @api.onchange('date_from')
    def _onchange_date_from(self):
        for line in self:
            if line.date_from and not line.date_to:
                line.date_to = line.date_from
            if line.date_from and not line.date_payroll:
                line.date_payroll = line.date_from

    def action_approve(self):
        self.write({'state': 'approve'})

    def action_refuse(self):
        self.write({'state': 'refuse'})

    def action_set_draft(self):
        self.write({'state': 'draft'})

    def unlink(self):
        for line in self:
            if line.state == 'approve':
                raise ValidationError(self.env._('No puede eliminar una ausencia aprobada.'))
        return super().unlink()
