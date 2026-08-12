from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    descuentos = fields.One2many('salary.advance', 'employee_id', string='Descuentos')
    prestamos = fields.One2many('hr.loan', 'employee_id', string='Prestamos')
    calificaciones = fields.One2many('hr.qualification', 'employee_id', string='Calificaciones')
    overtime_ids = fields.One2many('hr.overtime', 'employee_id', string='Horas Extra')
    absence_ids = fields.One2many('hr.absence.line', 'employee_id', string='Ausencias')
    payslip_input_ids = fields.One2many('hr.payslip.input.employee', 'employee_id', string='Otras Entradas')
    # entradas_trabajo = fields.One2many('hr.work.entry', 'employee_id', string='Entradas de trabajo')
    loan_count = fields.Integer(string='Cantidad de préstamos', compute='_compute_loan_count')
    isr_count = fields.Integer(string='Cantidad de retenciones ISR', compute='_compute_isr_count')
    absence_count = fields.Integer(string='Cantidad de ausencias', compute='_compute_absence_count')
    payslip_input_count = fields.Integer(string='Cantidad de otras entradas', compute='_compute_payslip_input_count')
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

    def _compute_isr_count(self):
        isr_data = self.env['hr.isr.retencion']._read_group(
            [('employee_id', 'in', self.ids)], ['employee_id'], ['__count'])
        counts = {employee.id: count for employee, count in isr_data}
        for employee in self:
            employee.isr_count = counts.get(employee.id, 0)

    def _compute_absence_count(self):
        absence_data = self.env['hr.absence.line']._read_group(
            [('employee_id', 'in', self.ids)], ['employee_id'], ['__count'])
        counts = {employee.id: count for employee, count in absence_data}
        for employee in self:
            employee.absence_count = counts.get(employee.id, 0)

    def _compute_payslip_input_count(self):
        input_data = self.env['hr.payslip.input.employee']._read_group(
            [('employee_id', 'in', self.ids)], ['employee_id'], ['__count'])
        counts = {employee.id: count for employee, count in input_data}
        for employee in self:
            employee.payslip_input_count = counts.get(employee.id, 0)
