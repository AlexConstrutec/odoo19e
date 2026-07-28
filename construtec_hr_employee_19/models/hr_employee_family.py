from datetime import date

from odoo import api, fields, models


class HrEmployeeFamily(models.Model):
    _name = 'hr.employee.family'
    _description = 'Círculo familiar del empleado'

    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True, ondelete='cascade')
    nombre = fields.Char(string='Nombre')
    parentesco = fields.Selection([
        ('padre', 'Padre/Madre'),
        ('hermano', 'Hermano/Hermana'),
        ('hijo', 'Hijo/Hija'),
    ], string='Parentesco')
    genero = fields.Selection([
        ('hombre', 'Hombre'),
        ('mujer', 'Mujer'),
    ], string='Género')
    fecha_nacimiento = fields.Date(string='Fecha de Nacimiento')
    edad = fields.Integer(string='Edad')
    ocupacion = fields.Char(string='Ocupación')

    @api.onchange('fecha_nacimiento')
    def _onchange_fecha_nacimiento(self):
        for record in self:
            if record.fecha_nacimiento:
                today = date.today()
                record.edad = today.year - record.fecha_nacimiento.year - (
                    (today.month, today.day) < (record.fecha_nacimiento.month, record.fecha_nacimiento.day))
