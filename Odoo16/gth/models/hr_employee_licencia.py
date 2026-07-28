
from odoo import models, fields, api, exceptions


class HrEmployeeLicenciaUser(models.Model):
    _name = 'hr.employee.licencia'
    _description = 'Licnencias de Conducir'

    employee_id = fields.Many2one('hr.employee', string='Empleado', store=True)
    # identification_employee_id = fields.Char(string="DPI", store=True)
    tipo_vehiculo = fields.Selection([
        ('vehiculo', 'Vehiculo'),
        ('motocicleta', 'Motocicleta'),
    ], string='Tipo de Vehículo', store=True)
    tipo_licencia = fields.Selection([
        ('n/p', 'N/P'),
        ('m', 'M'),
        ('c', 'C'),
        ('b', 'B'),
        ('a', 'A'),
        ('e', 'E'),
    ], string='Tipo de Licencia', store=True)
    numero_licencia = fields.Char(string='Número de Licencia', store=True)

