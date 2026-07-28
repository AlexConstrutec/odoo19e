from odoo import api, fields, models


class HrOvertimeShift(models.Model):
    _name = 'hr.overtime.shift'
    _description = 'Jornada de Hora Extra'
    _order = 'name'

    name = fields.Char(string='Jornada', required=True)
    active = fields.Boolean(string='Activo', default=True)


class HrOvertimeRate(models.Model):
    _name = 'hr.overtime.rate'
    _description = 'Tipo de Hora Extra'

    _employee_shift_uniq = models.Constraint(
        'unique (employee_id, shift_id)',
        'Ya existe una tarifa de hora extra para este empleado y esta jornada.',
    )

    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True, ondelete='cascade')
    shift_id = fields.Many2one('hr.overtime.shift', string='Jornada', required=True)
    hourly_amount = fields.Float(string='Valor Hora Extra', required=True)
    name = fields.Char(string='Nombre', related='shift_id.name', store=True)


class HrOvertime(models.Model):
    _name = 'hr.overtime'
    _description = 'Horas Extra'
    _order = 'date desc'

    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True, ondelete='cascade')
    date = fields.Date(string='Fecha', required=True, default=fields.Date.context_today)
    rate_id = fields.Many2one('hr.overtime.rate', string='Tipo Hora', required=True)
    number_of_hours = fields.Float(string='Cant. Horas', required=True)
    unit_amount = fields.Float(string='Monto Unitario', compute='_compute_amounts', store=True, readonly=True)
    total_amount = fields.Float(string='Monto Total', compute='_compute_amounts', store=True, readonly=True)
    name = fields.Char(string='Descripción', compute='_compute_name', store=True, readonly=True)

    @api.depends('rate_id.hourly_amount', 'number_of_hours')
    def _compute_amounts(self):
        for overtime in self:
            overtime.unit_amount = overtime.rate_id.hourly_amount
            overtime.total_amount = overtime.unit_amount * overtime.number_of_hours

    @api.depends('employee_id.name', 'date')
    def _compute_name(self):
        for overtime in self:
            overtime.name = f'{overtime.employee_id.name} - {overtime.date}' if overtime.employee_id and overtime.date else ''

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        for overtime in self:
            if overtime.rate_id.employee_id != overtime.employee_id:
                overtime.rate_id = False
