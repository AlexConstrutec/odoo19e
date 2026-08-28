from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    payment_order_id = fields.Many2one('account.payment.order', string='Orden de Pago', ondelete='restrict',
                                        store=True)
