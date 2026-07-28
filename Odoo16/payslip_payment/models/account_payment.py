from odoo import models, fields, api


class AccountPayment(models.Model):
    _inherit = 'account.payment'
    payslip_id = fields.Many2one('hr.payslip', string='Nomina', store=True, copy=True, help="Payslip where the move line come from")

    @api.onchange('amount', 'allocation_amount', 'state', 'write_date')
    def compute_balance(self):
        for payment in self:
            if payment.payslip_id:
                payment.payslip_id.balance = 0.0
                for line in payment.payslip_id.line_ids:
                    if line.salary_rule_id.code == 'NET':
                        payment.payslip_id.balance += line.total
                if payment.payslip_id.payment_ids:
                    for payment in payment.payslip_id.payment_ids:
                        payment.payslip_id.balance -= payment.amount