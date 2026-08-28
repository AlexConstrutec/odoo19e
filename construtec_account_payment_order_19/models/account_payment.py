from odoo import fields, models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    payment_order_id = fields.Many2one('account.payment.order', string='Orden de Pago', ondelete='restrict',
                                        store=True)
