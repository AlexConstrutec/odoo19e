from odoo import models, fields, api


class HrPayslipEmployees(models.TransientModel):
    _inherit = 'hr.payslip.employees'

    #employee_ids = fields.Many2many('hr.employee', 'hr_employee_group_rel', 'payslip_id', 'employee_id', 'Employees', required=True, store=True, readonly=False)

    def _get_employees(self):
        return False

    @api.depends('department_id')
    def _compute_employee_ids(self):
        return False