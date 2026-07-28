from odoo import models, fields


class HrOcupacionPuestoUser(models.Model):
    _name = 'hr.ocupacion.puesto'
    _description = 'Ocupacion de puestos de trabajo'

    name = fields.Char(string='Nombre', required=True)
    code = fields.Integer(string='Codigo', default=True)


