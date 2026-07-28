from odoo import models, fields, api, exceptions


class HrEmployeeWorkHistoryUser(models.Model):
    _name = 'hr.employee.work.history'
    _description = 'Datos Laborales'

    employee_id = fields.Many2one('hr.employee', string='Empleado', store=True)
    año_inicio = fields.Integer(string='Del Año', store=True)
    año_fin = fields.Integer(string='Al Año', store=True)
    empresa = fields.Char(string='Empresa', store=True)
    funcion = fields.Char(string='Función Principal', store=True)
    jefe_inmediato = fields.Char(string='Jefe Inmediato', store=True)
    motivo_retiro = fields.Char(string='Motivo de Retiro', store=True)
    puesto = fields.Char(string='Puesto', store=True)
    telefono = fields.Char(string='Teléfono Referencia', store=True)
    tiempo_laborado = fields.Char(string='Tiempo Laborado', store=True)
    ubicacion_empresa = fields.Char(string='Ubicación Empresa', store=True)