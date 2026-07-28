from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    descuentos = fields.One2many('salary.advance', 'employee_id', string='Descuentos')
    prestamos = fields.One2many('hr.loan', 'employee_id', string='Prestamos')
    calificaciones = fields.One2many('hr.qualification', 'employee_id', string='Calificaciones')
    overtime_ids = fields.One2many('hr.overtime', 'employee_id', string='Horas Extra')
    overtime_rate_ids = fields.One2many('hr.overtime.rate', 'employee_id', string='Tipo Hora Extra')
    # entradas_trabajo = fields.One2many('hr.work.entry', 'employee_id', string='Entradas de trabajo')
    loan_count = fields.Integer(string='Cantidad de préstamos', compute='_compute_loan_count')
    # estado_contrato = fields.Many2one('hr.contract.status', string='Estado de contrato',
    #                                    related='version_id.estado_contrato')
    # frecuencia_pago = fields.Many2one('hr.contract.payment.frequency', string='Frecuencia de pago',
    #                                    related='version_id.frecuencia_pago')

    def _compute_loan_count(self):
        loan_data = self.env['hr.loan']._read_group(
            [('employee_id', 'in', self.ids)], ['employee_id'], ['__count'])
        counts = {employee.id: count for employee, count in loan_data}
        for employee in self:
            employee.loan_count = counts.get(employee.id, 0)
