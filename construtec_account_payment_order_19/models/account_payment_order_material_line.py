from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AccountPaymentOrderMaterialLine(models.Model):
    _name = 'account.payment.order.material.line'
    _description = 'Línea de Materiales de una Requisición de Pago'

    order_id = fields.Many2one('account.payment.order', string='Requisición de Pago',
                                required=True, ondelete='cascade')
    product_name = fields.Char(string='Material', required=True,
                                help='Lo que el jefe de técnicos escribe/elige en Community - '
                                     'texto libre, no una relación. El jefe solo pide materiales, '
                                     'sin decidir si ya hay existencia propia o hay que comprarlo '
                                     '- esa determinación es de Enterprise/procurement, ver '
                                     '`product_id`. Columna oculta por defecto en la vista '
                                     '(`optional="hide"`) - se sigue llenando solo, desde '
                                     '`catalogo_id` o desde `description`, ver los onchange/'
                                     '`create()` de este modelo.')
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

    de_bodega = fields.Boolean(
        string='Bodega',
        help='El jefe de técnicos sabe que este material ya está en bodega y pide que se traslade '
             '(no se compra). Compras (Enterprise) revisa la existencia: si no alcanza, el faltante '
             'sí se compra. Una línea de bodega no pide dinero hasta que Compras define cuánto '
             'comprar (2026-10-27).')
    bodega_revisada = fields.Boolean(
        string='Existencia revisada', readonly=True, copy=False,
        help='Compras ya definió cuánto se traslada y cuánto se compra de esta línea de bodega.')
    qty_trasladar = fields.Float(
        string='A trasladar', copy=False,
        help='Cantidad que sale de bodega (la define Compras en Enterprise).')
    qty_comprar = fields.Float(
        string='A comprar', compute='_compute_qty_comprar', store=True,
        help='Lo que sí se compra: toda la cantidad en una línea normal; en una línea de bodega, '
             'el faltante (pedido - a trasladar) una vez que Compras revisó la existencia '
             '(mientras tanto, 0).')

    @api.depends('qty', 'de_bodega', 'bodega_revisada', 'qty_trasladar')
    def _compute_qty_comprar(self):
        for line in self:
            if not line.de_bodega:
                line.qty_comprar = line.qty
            elif line.bodega_revisada:
                line.qty_comprar = max(line.qty - line.qty_trasladar, 0.0)
            else:
                line.qty_comprar = 0.0

    @api.depends('qty_comprar', 'estimated_price')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.qty_comprar * line.estimated_price

    @api.constrains('qty_trasladar', 'qty')
    def _check_qty_trasladar(self):
        for line in self:
            if line.qty_trasladar < 0 or line.qty_trasladar > line.qty:
                raise ValidationError(self.env._(
                    'La cantidad a trasladar de "%s" debe estar entre 0 y la cantidad pedida.',
                    line.product_name))

    @api.model_create_multi
    def create(self, vals_list):
        """`product_name` sigue siendo required=True (lo necesitan la sincronización y la
        generación de la Orden de Compra) pero la columna está oculta por defecto en la vista
        (`optional="hide"`) - si nadie la vuelve a mostrar ni elige un `catalogo_id`, se rellena
        aquí desde `description` (el texto que en la práctica ya es el principal - ver
        `action_generar_orden_compra()`, que ya prefiere `description` sobre `product_name` al
        armar la línea de compra) para que una línea nunca falle al guardar por un campo que el
        jefe de técnicos ni siquiera está viendo."""
        for vals in vals_list:
            if not vals.get('product_name') and vals.get('description'):
                vals['product_name'] = vals['description']
        return super().create(vals_list)

    @api.onchange('description')
    def _onchange_description_fill_product_name(self):
        for line in self:
            if not line.product_name and line.description:
                line.product_name = line.description

    @api.onchange('catalogo_id')
    def _onchange_catalogo_id(self):
        for line in self:
            if line.catalogo_id:
                line.product_name = line.catalogo_id.name
                line.vendor_name = line.catalogo_id.partner_name or line.vendor_name
                line.estimated_price = line.catalogo_id.precio_referencia or line.estimated_price
                line.uom_name = line.catalogo_id.uom_name or line.uom_name
