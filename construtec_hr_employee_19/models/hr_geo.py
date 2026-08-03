from odoo import fields, models


class HrDepartamento(models.Model):
    _name = 'hr.departamento'
    _description = 'Departamento (Guatemala)'
    _order = 'code'

    name = fields.Char(string='Nombre', required=True)
    code = fields.Integer(string='Código', required=True)


class HrMunicipio(models.Model):
    _name = 'hr.municipio'
    _description = 'Municipio (Guatemala)'
    _order = 'code'

    name = fields.Char(string='Nombre', required=True)
    code = fields.Integer(string='Código', required=True)
    departamento_id = fields.Many2one('hr.departamento', string='Departamento', required=True)
