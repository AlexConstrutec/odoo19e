from odoo import api, fields, models


class AccountPaymentOrderMaterialLine(models.Model):
    _name = 'account.payment.order.material.line'
    _description = 'Línea de Materiales de una Orden de Pago'

    order_id = fields.Many2one('account.payment.order', string='Orden de Pago',
                                required=True, ondelete='cascade')
    product_name = fields.Char(string='Material', required=True,
                                help='Lo que el jefe de técnicos escribe/elige en Community - '
                                     'texto libre, no una relación. El jefe solo pide materiales, '
                                     'sin decidir si ya hay existencia propia o hay que comprarlo '
                                     '- esa determinación es de Enterprise/procurement, ver '
                                     '`product_id`.')
    description = fields.Char(string='Descripción')
    uom_name = fields.Char(string='Unidad de Medida')
    qty = fields.Float(string='Cantidad', default=1)
    estimated_price = fields.Float(string='Precio Estimado')
    subtotal = fields.Float(string='Subtotal', compute='_compute_subtotal', store=True)
    vendor_name = fields.Char(
        string='Proveedor Sugerido',
        help='Sugerencia en texto del jefe de técnicos, viaja por sincronización igual que '
             '`product_name` - nunca se trata como relación. El proveedor real de la Orden de '
             'Compra es `order_id.proveedor_materiales_id`, elegido a mano en Enterprise.')
    catalogo_id = fields.Many2one(
        'construtec.materials.catalog.mirror', string='Producto SAT',
        domain="[('bien_o_servicio', '=', 'B')]",
        help='Ayuda opcional, nunca obligatoria - elegir una entrada aquí autocompleta Material/'
             'Proveedor Sugerido/Precio Estimado/Unidad de Medida desde el Catálogo de Materiales '
             '(derivado de los Documentos SAT). Filtrado a solo "Bien" - el catálogo sincroniza '
             'también Servicios, '
             'pero una Solicitud de Materiales no los necesita (otra sección futura del proyecto '
             'sí los usará, desde el mismo catálogo). El buscador prefiere lo del proveedor ya '
             'escrito en esta línea (`vendor_name`) dentro de ese filtro, sin restringir más allá '
             'de eso - se puede elegir cualquier otro Bien, o ignorar esto por completo y '
             'escribir/crear un material que no esté en el catálogo.')
    product_id = fields.Many2one(
        'product.product', string='Producto (Enterprise)',
        help='Vacío al llegar de Community - se llena a mano en Enterprise antes de generar la '
             'Orden de Compra (mismo principio que `partner_id` de Anticipo: nunca se confía un '
             'id cruzado entre bases, un humano en Enterprise resuelve el producto real). Si '
             'procurement sabe que ya hay existencia propia de este material, simplemente deja '
             'esta línea sin producto - `action_generar_orden_compra()` la omite.')
    purchase_order_line_id = fields.Many2one(
        'purchase.order.line', string='Línea de Orden de Compra', readonly=True, copy=False,
        help='Se llena al generar la Orden de Compra (`action_generar_orden_compra()`) - evita '
             'generar dos veces la misma línea.')

    @api.depends('qty', 'estimated_price')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.qty * line.estimated_price

    @api.onchange('catalogo_id')
    def _onchange_catalogo_id(self):
        for line in self:
            if line.catalogo_id:
                line.product_name = line.catalogo_id.name
                line.vendor_name = line.catalogo_id.partner_name or line.vendor_name
                line.estimated_price = line.catalogo_id.precio_referencia or line.estimated_price
                line.uom_name = line.catalogo_id.uom_name or line.uom_name
