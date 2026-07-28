from odoo import fields, models


class HrEmployeeWorkHistory(models.Model):
    _name = 'hr.employee.work.history'
    _description = 'Datos laborales previos del empleado'

    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True, ondelete='cascade')
    empresa = fields.Char(string='Empresa')
    puesto = fields.Char(string='Puesto')
    funcion = fields.Char(string='Función Principal')
    año_inicio = fields.Integer(string='Del Año')
    año_fin = fields.Integer(string='Al Año')
    tiempo_laborado = fields.Char(string='Tiempo Laborado')
    jefe_inmediato = fields.Char(string='Jefe Inmediato')
    telefono = fields.Char(string='Teléfono Referencia')
    ubicacion_empresa = fields.Char(string='Ubicación Empresa')
    motivo_retiro = fields.Char(string='Motivo de Retiro')
