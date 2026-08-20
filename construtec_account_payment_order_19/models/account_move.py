from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    payment_order_id = fields.Many2one('account.payment.order', string='Orden de Pago', ondelete='restrict',
                                        store=True)
    no_liquidacion = fields.Many2one(
        'account.payment.order', string='No. Liquidación', domain=[('tipo', '=', 'liquidacion')],
        help='Ver account_payment.py - mismo campo, mismo criterio, antes Integer con búsqueda '
             'por coincidencia de número, ahora una relación real.')
