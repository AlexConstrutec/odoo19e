from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    payment_order_default_material_product_id = fields.Many2one(
        related='company_id.payment_order_default_material_product_id', readonly=False)
