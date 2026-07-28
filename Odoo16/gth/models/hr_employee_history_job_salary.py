from odoo import models, fields, api, exceptions


class HrEmployeeHistoryJobSalary(models.Model):
    _name = 'hr.employee.history.job.salary'
    _description = 'Historial de trabajo de empleado'
    _order = 'date_end desc'

    date_start = fields.Date(string="Fecha de inicio", store=True)
    date_end = fields.Date(string="Fecha de fin", store=True)
    company = fields.Char(string="Empresa", store=True)
    job = fields.Char(string="Puesto", store=True)
    employee= fields.Char(string="Empleado", store=True)
    salary = fields.Float(string="Salario", store=True)
    identification_employee_id = fields.Char(string="DPI", store=True)
    contract_id = fields.Many2one('hr.contract', string="Contrato", store=True)
    contrato_registrado = fields.Boolean(string="Contrato registrado", store=True)

    # contract_id = fields.Many2one('hr.contract', string="Contrato", store=True)
    # motivo_terminacion = fields.Selection([
    #     ('reuncia', 'Renuncia'),
    #     ('despido', 'Despido'),
    #     ('despido_justificado', 'Despido Justificado'),
    #     ('fin_apoyo', 'Finalización Apoyo'),
    #     ('retired', 'Abandono de labores'),
    #     ('fin_contrato', 'Finalización de Contrato Definido'),
    #     ('reestructuracion', 'Reestructuración'),
    #     ('mutuo_acuerdo', 'Mutuo Acuerdo'),
	# ('sustitucion', 'Sustitución Patronal'),
    #     ('fallecimiento', 'Fallecimiento'),], string="Motivo de terminacion", store=True)



