from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    bank_rec_commission_account_id = fields.Many2one(
        related='company_id.bank_rec_commission_account_id', readonly=False)
    bank_rec_interest_income_account_id = fields.Many2one(
        related='company_id.bank_rec_interest_income_account_id', readonly=False)
    bank_rec_interest_expense_account_id = fields.Many2one(
        related='company_id.bank_rec_interest_expense_account_id', readonly=False)
    bank_rec_match_days = fields.Integer(
        related='company_id.bank_rec_match_days', readonly=False)
    bank_rec_alert_months = fields.Integer(
        related='company_id.bank_rec_alert_months', readonly=False)
