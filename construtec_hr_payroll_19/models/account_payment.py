from odoo import fields, models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    payslip_id = fields.Many2one('hr.payslip', string='Nómina', copy=False)
