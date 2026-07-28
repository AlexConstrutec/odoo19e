from odoo import models, fields

class HrPayslipPrestaciones(models.Model):
    _name = 'hr.payslip.prestaciones'
    _description = 'Prestaciones de Nómina'

    id_employee_id = fields.Integer(string="IdE", readonly=True, related='employee_id.id')
    employee_id = fields.Many2one('hr.employee', string="Empleado", readonly=True)
    codigo_colaborador = fields.Integer(string="Código Colaborador", readonly=True)
    department_id = fields.Many2one('hr.department', string="Departamento", readonly=True, related='employee_id.department_id')
    date_start_contract = fields.Date(string="Inicio de Contrato", readonly=True, related='employee_id.contract_id.date_start')
    date_end_contract = fields.Date(string="Fin de Contrato", readonly=True, related='employee_id.contract_id.date_end')
    contract_state = fields.Selection([
        ('draft', 'NUEVO'),
        ('open', 'EN PROCESO'),
        ('close', 'VENCIDO'),
        ('cancel', 'CANCELADO'),
    ], string='Estado de Contrato', readonly=True, related='employee_id.contract_id.state')
    empleado = fields.Char(string="Empleado", readonly=True)
    bono14 = fields.Float(string="BONO14", readonly=True)
    aguinaldo = fields.Float(string="AGUINALDO", readonly=True)
    vacaciones = fields.Float(string="VACACIONES", readonly=True)
    indemnizacion = fields.Float(string="INDEMNIZACIÓN", readonly=True)
    date_to = fields.Date(string="Fecha al", readonly=True)
