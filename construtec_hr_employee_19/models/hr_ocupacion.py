from odoo import fields, models


class HrOcupacion(models.Model):
    _name = 'hr.ocupacion'
    _description = 'Ocupación (catálogo CIUO-08 de MITRAB, "Formato_Informe Empleados.xlsx")'
    _order = 'name'

    name = fields.Char(string='Nombre', required=True)
    code = fields.Char(string='Código', required=True)
