from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'
    representante_legal = fields.Char(string="Representante Legal")
