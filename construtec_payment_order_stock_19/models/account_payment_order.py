from odoo import fields, models
from odoo.exceptions import UserError


class AccountPaymentOrder(models.Model):
    _inherit = 'account.payment.order'

    traslado_picking_ids = fields.One2many(
        'stock.picking', 'payment_order_id', string='Traslados desde Bodega', readonly=True)

    def _lineas_bodega(self):
        return self.material_line_ids.filtered('de_bodega')

    def _check_bodega_gestion(self):
        if self.tipo != 'anticipo_materiales' or self.state not in ('en_compras', 'aprobado'):
            raise UserError(self.env._(
                'El traslado desde bodega se gestiona en la Solicitud de Materiales en Gestión de '
                'Compras (o Aprobada).'))
        self._check_puede_gestionar_compras()

    def action_revisar_existencias(self):
        """Compras revisa la existencia de las líneas marcadas "Bodega": propone trasladar
        mínimo(pedido, disponible) y deja el faltante para comprar. Solo líneas aún sin revisar
        (para corregir una, se edita "A trasladar" a mano)."""
        self.ensure_one()
        self._check_bodega_gestion()
        lineas = self._lineas_bodega().filtered(lambda l: not l.bodega_revisada)
        if not lineas:
            raise UserError(self.env._('No hay líneas de bodega pendientes de revisar.'))
        sin_producto = lineas.filtered(lambda l: not l.product_id)
        if sin_producto:
            raise UserError(self.env._(
                'Asigna el Producto (Enterprise) de las líneas de bodega para consultar su '
                'existencia: %s.', ', '.join(sin_producto.mapped(
                    lambda l: l.description or l.product_name))))
        sin_bodega = lineas.filtered(lambda l: not l.warehouse_id)
        if sin_bodega:
            raise UserError(self.env._('Elige la Bodega de origen de las líneas de bodega.'))
        resumen = []
        for linea in lineas:
            disponible = max(linea.qty_disponible, 0.0)
            trasladar = min(linea.qty, disponible)
            linea.write({'qty_trasladar': trasladar})
            resumen.append('%s: trasladar %s, comprar %s' % (
                linea.description or linea.product_name, trasladar, linea.qty - trasladar))
        self._sync_monto_desde_total_acreditar()
        self.message_post(body=self.env._('Existencias revisadas por %(user)s - %(resumen)s',
                                          user=self.env.user.name, resumen='; '.join(resumen)))
        return True

    def action_generar_traslado(self):
        """Crea (con permisos de sistema: Compras no necesita Inventario) un traslado por bodega de
        origen con lo que sale de bodega, hacia la ubicación de clientes (consumo en obra). Queda
        reservado, listo para que Compras lo valide con "Validar traslado"."""
        self.ensure_one()
        self._check_bodega_gestion()
        self._check_bodega_revisada()
        lineas = self._lineas_bodega().filtered(
            lambda l: l.qty_trasladar > 0 and not l.traslado_picking_id)
        if not lineas:
            raise UserError(self.env._('No hay material de bodega pendiente de trasladar.'))
        destino = self.env.ref('stock.stock_location_customers')
        Picking = self.env['stock.picking'].sudo()
        for bodega in lineas.mapped('warehouse_id'):
            de_bodega = lineas.filtered(lambda l: l.warehouse_id == bodega)
            picking = Picking.create({
                'picking_type_id': bodega.out_type_id.id,
                'location_id': bodega.lot_stock_id.id,
                'location_dest_id': destino.id,
                'origin': self.name,
                'payment_order_id': self.id,
                'company_id': bodega.company_id.id,
                'move_ids': [(0, 0, {
                    'product_id': l.product_id.id,
                    'product_uom_qty': l.qty_trasladar,
                    'product_uom': l.product_id.uom_id.id,
                    'location_id': bodega.lot_stock_id.id,
                    'location_dest_id': destino.id,
                }) for l in de_bodega],
            })
            picking.action_confirm()
            picking.action_assign()
            de_bodega.sudo().write({'traslado_picking_id': picking.id})
            self.message_post(body=self.env._(
                'Traslado %(name)s generado desde %(bodega)s (%(n)s línea(s)).',
                name=picking.name, bodega=bodega.name, n=len(de_bodega)))
        return True

    def action_validar_traslado(self):
        """Compras valida los traslados pendientes (sin necesitar permisos de Inventario)."""
        self.ensure_one()
        self._check_bodega_gestion()
        pendientes = self.sudo().traslado_picking_ids.filtered(
            lambda p: p.state not in ('done', 'cancel'))
        if not pendientes:
            raise UserError(self.env._('No hay traslados pendientes de validar.'))
        for picking in pendientes:
            if picking.state != 'assigned':
                picking.action_assign()
            if picking.state != 'assigned':
                raise UserError(self.env._(
                    'El traslado %s no tiene toda la existencia reservada: revisa la bodega.',
                    picking.name))
            picking.with_context(skip_backorder=True, skip_sms=True).button_validate()
            if picking.state != 'done':
                raise UserError(self.env._('No se pudo validar el traslado %s.', picking.name))
            self.message_post(body=self.env._(
                'Traslado %(name)s validado por %(user)s.', name=picking.name,
                user=self.env.user.name))
        return True

    def _check_traslados_listos(self):
        super()._check_traslados_listos()
        for linea in self._lineas_bodega().filtered(lambda l: l.qty_trasladar > 0):
            picking = linea.sudo().traslado_picking_id
            if not picking or picking.state != 'done':
                raise UserError(self.env._(
                    'Falta trasladar y validar desde bodega: %s.',
                    linea.description or linea.product_name))
        return True
