from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    representante_legal = fields.Char(string='Representante Legal')
