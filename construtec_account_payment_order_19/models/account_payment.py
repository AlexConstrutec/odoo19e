from odoo import fields, models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    payment_order_id = fields.Many2one('account.payment.order', string='Orden de Pago', ondelete='restrict',
                                        store=True)
    no_liquidacion = fields.Many2one(
        'account.payment.order', string='No. Liquidación', domain=[('tipo', '=', 'liquidacion')],
        help='Antes era un Integer que buscaba la Orden de Pago por coincidencia de número - '
             'ahora es una relación real. `payment_order_id` (arriba) sigue siendo el campo '
             'principal de trazabilidad; este es un atajo equivalente para cuando se conoce el '
             'número de Liquidación pero no se tiene a la mano la Orden de Pago misma.')
