from odoo import models, fields, api

class HrRequestEmployeeSalary(models.Model):
    _name = "hr.request.employee.salary"
    _description = "Salario - Requisición de personal"
    name = fields.Selection(
        [('minimo', 'Mínimo'),
         ('diurno', 'Diurno'),
         ('nocturno', 'Nocturno'),
         ('bonif_in', 'Bonificación Incentivo'),
         ('bonif_prod', 'Bonificaciónn Productividad'),
         ('bonif_fij', 'Bonificacion Fija'),
         ('otro', 'Otro')], string='Nombre', required=True, store=True)
    monto = fields.Float(string='Monto', required=True, store=True)
    request_employee_id = fields.Many2one('hr.request.employee', string='Requisición de personal', required=True, store=True,  readonly=True, index=True)

    @api.onchange('name')
    def _onchange_name(self):
        if self.name == 'minimo':
            valor = self.env['hr.rule.parameter.value'].search([('rule_parameter_id.name', '=', 'Salario Minimo')], order="id desc", limit=1)
            self.monto = float(valor.parameter_value)
        elif self.name == 'diurno':
            valor = self.env['hr.rule.parameter.value'].search([('rule_parameter_id.name', '=', 'Diurno')], order="id desc", limit=1)
            self.monto = float(valor.parameter_value)
        elif self.name == 'nocturno':
            valor = self.env['hr.rule.parameter.value'].search([('rule_parameter_id.name', '=', 'Nocturno')], order="id desc", limit=1)
            self.monto = float(valor.parameter_value)
        elif self.name == 'bonif_in':
            valor = self.env['hr.rule.parameter.value'].search([('rule_parameter_id.name', '=', 'Bonificación Incentivo')], order="id desc", limit=1)
            self.monto = float(valor.parameter_value)
        elif self.name == 'bonif_prod':
            self.monto = 0
        elif self.name == 'bonif_fij':
            self.monto = 0
        else:
            self.monto = 0