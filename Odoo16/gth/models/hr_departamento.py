from odoo import models, fields, api, exceptions


class HrDepartamentoUser(models.Model):
    _name = 'hr.departamento'
    _description = 'Departamento'

    name = fields.Char(string='Nombre', store=True)
    code = fields.Integer(string='Codigo', store=True)


    # @api.model
    # def create(self, vals_list):
    #     return super(HrDepartamentoUser, self).create(vals_list)
