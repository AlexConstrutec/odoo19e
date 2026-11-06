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
