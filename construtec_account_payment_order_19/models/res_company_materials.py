from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    payment_order_default_material_product_id = fields.Many2one(
        'product.product', string='Producto por defecto de Materiales',
        domain=[('purchase_ok', '=', True)],
        help='Producto de Odoo que se usa, en la Orden de Compra de una Solicitud de Materiales, '
             'para las líneas que todavía no tienen un Producto asignado (2026-10-17: para no '
             'tener que buscar un producto por cada material). El nombre que sale en la Orden de '
             'Compra sigue siendo el material pedido; el producto por defecto solo aporta la '
             'unidad de medida, los impuestos y la cuenta de compra. Si se deja vacío, solo se '
             'compran las líneas que ya tienen Producto.')
