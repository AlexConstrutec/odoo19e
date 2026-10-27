from odoo import fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    payment_order_id = fields.Many2one(
        'account.payment.order', string='Requisición de Pago', copy=False, index=True,
        ondelete='restrict',
        help='Requisición de Materiales que originó este traslado desde bodega.')
