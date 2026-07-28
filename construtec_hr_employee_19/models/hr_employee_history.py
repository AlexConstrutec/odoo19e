from odoo import fields, models


class HrEmployeeHistoryJobSalary(models.Model):
    _name = 'hr.employee.history.job.salary'
    _description = 'Historial laboral de empleado'
    _order = 'date_end desc'

    date_start = fields.Date(string='Fecha de inicio')
    date_end = fields.Date(string='Fecha de fin')
    company = fields.Char(string='Empresa')
    job = fields.Char(string='Puesto')
    employee = fields.Char(string='Empleado')
    salary = fields.Float(string='Salario')
    identification_employee_id = fields.Char(string='DPI')
    version_id = fields.Many2one('hr.version', string='Contrato')
    contrato_registrado = fields.Boolean(string='Contrato registrado ante GT RECIT')
