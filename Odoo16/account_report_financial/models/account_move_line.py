from odoo import models, api


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    @api.depends('product_id', 'journal_id')
    def _compute_name(self):
        for record in self:
            xname = record.name
            res = super(AccountMoveLine, record)._compute_name()
            record.name = xname
            return res