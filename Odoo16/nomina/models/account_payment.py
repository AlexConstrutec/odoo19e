from odoo import api, fields, models, _


class AccountMove(models.Model):
    _inherit = "account.payment"

    no_anticipo = fields.Integer(string='No. Anticipo', store=True, readonly=True)