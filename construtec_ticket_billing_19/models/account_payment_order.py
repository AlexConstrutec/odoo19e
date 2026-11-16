# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import api, fields, models


class AccountPaymentOrder(models.Model):
    _inherit = 'account.payment.order'

    ticket_mirror_id = fields.Many2one(
        'construtec.helpdesk.ticket.mirror', string='Ticket', index=True, readonly=True,
        copy=False, ondelete='set null',
        help='El Ticket de Community que originó esta Requisición de Pago (2026-10-24). Llega '
             'por número de ticket, nunca por id: con la propia requisición (`ticket_number`, '
             'ver create()) o cuando Community reenvía el ticket con sus requisiciones '
             '(`payment_order_refs`, ver construtec.helpdesk.ticket.mirror.sync_from_community()).')

    area_analytic_account_id = fields.Many2one(
        'account.analytic.account', string='Área de Negocio', readonly=True, copy=False,
        help='Área del equipo del ticket al CREAR la requisición en Community (foto: no cambia '
             'si el ticket cambia de equipo después). Segundo plan analítico de la Orden de '
             'Compra generada desde aquí.')

    @api.model_create_multi
    def create(self, vals_list):
        """`ticket_number` no es un campo: lo manda `_prepare_sync_vals()` de Community
        (construtec_helpdesk_field_service). Se resuelve al espejo del ticket; si el ticket
        todavía no llegó, se crea el espejo solo con su número y el siguiente envío del ticket
        lo completa (mismo upsert por número)."""
        for vals in vals_list:
            area_ref = vals.pop('area_analytic_enterprise_ref', False)
            if area_ref and not vals.get('area_analytic_account_id'):
                area = self.env['account.analytic.account'].browse(int(area_ref)).exists()
                if area:
                    vals['area_analytic_account_id'] = area.id
            number = vals.pop('ticket_number', False)
            if number and not vals.get('ticket_mirror_id'):
                vals['ticket_mirror_id'] = self.env[
                    'construtec.helpdesk.ticket.mirror'].sudo()._get_or_create_by_number(number).id
        return super().create(vals_list)

    def action_generar_orden_compra(self):
        """Tras generar la Orden de Compra, agrega el Área al reparto analítico de sus líneas
        (Ubicación + Área, un solo renglón con llave "id1,id2" = 100 %). Solo toca líneas cuyo
        reparto sigue siendo el que puso la generación (vacío o solo la Ubicación): nunca pisa
        uno que Compras ya cambió a mano."""
        res = super().action_generar_orden_compra()
        for order in self.filtered('area_analytic_account_id'):
            base = {str(order.analytic_account_id.id): 100.0} if order.analytic_account_id else False
            ids = [a.id for a in (order.analytic_account_id, order.area_analytic_account_id) if a]
            nueva = {','.join(str(i) for i in ids): 100.0}
            for line in order.purchase_order_ids.order_line:
                if (line.analytic_distribution or False) == base:
                    line.analytic_distribution = nueva
        return res

    def _ticket_analytic_distribution(self):
        """Distribución analítica de TODO lo que esta requisición genera en contabilidad (facturas
        de proveedor, pagos y asiento de conciliación): un solo renglón con llave "ubicación,
        área" = 100 %, es decir las DOS cuentas (una por plan, cada plan al 100 %). La Ubicación
        es la de la requisición (viene del ticket); si falta, la del espejo del ticket. El Área es
        la foto del equipo al crear la requisición; si falta, la del espejo del ticket. Sin
        ninguna de las dos devuelve False (no se toca nada)."""
        self.ensure_one()
        ubicacion = self.analytic_account_id or self.ticket_mirror_id.analytic_account_id
        area = self.area_analytic_account_id or self.ticket_mirror_id.area_analytic_account_id
        ids = [a.id for a in (ubicacion, area) if a]
        return {','.join(str(i) for i in ids): 100.0} if ids else False

    def _apply_ticket_analytic_to_lines(self, lines):
        """Pone la distribución en líneas sin una propia, y también AMPLÍA las que tienen
        exactamente "solo la Ubicación al 100 %" (lo que se puso antes de conocer el Área) a
        Ubicación + Área. Cualquier otra distribución (fijada a mano) nunca se toca. Excluye
        líneas de sección/nota."""
        self.ensure_one()
        distribucion = self._ticket_analytic_distribution()
        if not distribucion:
            return
        ubicacion = self.analytic_account_id or self.ticket_mirror_id.analytic_account_id
        solo_ubicacion = {str(ubicacion.id): 100.0} if ubicacion else None
        por_cambiar = lines.filtered(
            lambda l: l.display_type not in ('line_section', 'line_note')
            and l.analytic_distribution != distribucion
            and (not l.analytic_distribution
                 or (solo_ubicacion and l.analytic_distribution == solo_ubicacion)))
        if por_cambiar:
            por_cambiar.analytic_distribution = distribucion

    def _apply_ticket_analytic_to_documents(self):
        """Aplica la distribución a todo lo que la requisición ya generó: facturas de proveedor,
        pagos y asiento de conciliación."""
        for order in self:
            for factura in self.env['account.move'].search([
                    ('payment_order_id', '=', order.id), ('move_type', '=', 'in_invoice')]):
                order._apply_ticket_analytic_to_lines(factura.invoice_line_ids)
            for pago in self.env['account.payment'].search([('payment_order_id', '=', order.id)]):
                order._apply_ticket_analytic_to_lines(pago.move_id.line_ids)
            if order.move_id:
                order._apply_ticket_analytic_to_lines(order.move_id.line_ids)

    def action_conciliar(self):
        res = super().action_conciliar()
        for order in self:
            if order.move_id:
                order._apply_ticket_analytic_to_lines(order.move_id.line_ids)
        return res
