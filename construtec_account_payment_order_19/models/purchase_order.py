from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    payment_order_id = fields.Many2one(
        'account.payment.order', string='Orden de Pago', ondelete='restrict', store=True,
        help='Orden de Pago (Solicitud de Materiales) que generó esta Orden de Compra vía '
             '`action_generar_orden_compra()` - solo trazabilidad, no participa en la '
             'conciliación (esa sigue haciéndose vía `factura_ids`/`pago_ids` sobre la propia '
             'Orden de Pago, como cualquier Anticipo/Liquidación).')
