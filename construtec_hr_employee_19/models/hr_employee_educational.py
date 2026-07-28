from odoo import fields, models

from .hr_employee_selections import NIVEL_ACADEMICO


class HrEmployeeEducational(models.Model):
    _name = 'hr.employee.educational'
    _description = 'Educación del empleado'

    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True, ondelete='cascade')
    establecimiento = fields.Char(string='Establecimiento')
    titulo = fields.Char(string='Título')
    nivel_academico = fields.Selection(NIVEL_ACADEMICO, string='Nivel Académico')
    año = fields.Integer(string='Año')
    fecha_inicio = fields.Date(string='Fecha de Inicio')
    fecha_fin = fields.Date(string='Fecha de Fin')
