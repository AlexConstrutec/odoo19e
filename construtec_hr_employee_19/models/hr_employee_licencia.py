from odoo import fields, models


class HrEmployeeLicencia(models.Model):
    _name = 'hr.employee.licencia'
    _description = 'Licencia de conducir del empleado'

    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True, ondelete='cascade')
    tipo_vehiculo = fields.Selection([
        ('vehiculo', 'Vehículo'),
        ('motocicleta', 'Motocicleta'),
    ], string='Tipo de Vehículo')
    tipo_licencia = fields.Selection([
        ('n/p', 'N/P'),
        ('m', 'M'),
        ('c', 'C'),
        ('b', 'B'),
        ('a', 'A'),
        ('e', 'E'),
    ], string='Tipo de Licencia')
    numero_licencia = fields.Char(string='Número de Licencia')
