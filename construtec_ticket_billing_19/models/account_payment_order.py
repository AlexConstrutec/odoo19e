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

    @api.model_create_multi
    def create(self, vals_list):
        """`ticket_number` no es un campo: lo manda `_prepare_sync_vals()` de Community
        (construtec_helpdesk_field_service). Se resuelve al espejo del ticket; si el ticket
        todavía no llegó, se crea el espejo solo con su número y el siguiente envío del ticket
        lo completa (mismo upsert por número)."""
        for vals in vals_list:
            number = vals.pop('ticket_number', False)
            if number and not vals.get('ticket_mirror_id'):
                vals['ticket_mirror_id'] = self.env[
                    'construtec.helpdesk.ticket.mirror'].sudo()._get_or_create_by_number(number).id
        return super().create(vals_list)
