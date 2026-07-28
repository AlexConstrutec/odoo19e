from datetime import date

from odoo import models, fields, api, exceptions


class HrEmployeeFamilyUser(models.Model):
    _name = 'hr.employee.family'
    _description = 'Circulo Familiar'

    x_edad = fields.Integer(string='Edad', readonly=False)
    x_employee_id = fields.Many2one('hr.employee', string='Empleado', store=True)
    x_fecha_nacimiento = fields.Date(string='Fecha de Nacimiento', store=True)
    x_genero = fields.Selection([
        ('hombre', 'Hombre'),
        ('mujer', 'Mujer'),
    ], string='Género', store=True)
    x_nombre = fields.Char(string='Nombre', store=True)
    x_ocupacion = fields.Char(string='Ocupación', store=True)
    x_parentesco = fields.Selection([
        ('padre', 'Padre/Madre'),
        ('hermano', 'Hermano/Hermana'),
        ('hijo', 'Hijo/Hija')
    ], string='Parentesco', store=True)

    @api.onchange('x_fecha_nacimiento')
    def _onchange_x_fecha_nacimiento(self):
        if self.x_fecha_nacimiento:
            self.x_edad = self._calculate_age(self.x_fecha_nacimiento)
    def _calculate_age(self, birth_date):
        today = date.today()
        return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))