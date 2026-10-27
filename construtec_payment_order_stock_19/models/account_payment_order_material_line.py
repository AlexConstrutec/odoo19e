from odoo import api, fields, models


class AccountPaymentOrderMaterialLine(models.Model):
    _inherit = 'account.payment.order.material.line'

    warehouse_id = fields.Many2one(
        'stock.warehouse', string='Bodega de origen',
        default=lambda self: self.env['stock.warehouse'].sudo().search(
            [('company_id', '=', self.env.company.id)], limit=1),
        help='Bodega de la que Compras traslada este material (solo líneas marcadas "Bodega").')
    qty_disponible = fields.Float(
        string='Disponible', compute='_compute_qty_disponible',
        help='Existencia libre del producto en la bodega de origen, en vivo.')
    traslado_picking_id = fields.Many2one(
        'stock.picking', string='Traslado', readonly=True, copy=False,
        help='Traslado de inventario que sacó este material de bodega.')

    @api.depends('product_id', 'warehouse_id', 'de_bodega')
    def _compute_qty_disponible(self):
        for line in self:
            product = line.product_id.sudo()
            if line.de_bodega and product and line.warehouse_id:
                line.qty_disponible = product.with_context(
                    warehouse_id=line.warehouse_id.id).free_qty
            else:
                line.qty_disponible = 0.0

    def write(self, vals):
        # Compras corrigiendo a mano cuánto se traslada también cuenta como "existencia revisada".
        if 'qty_trasladar' in vals and 'bodega_revisada' not in vals:
            vals = dict(vals, bodega_revisada=True)
        return super().write(vals)
