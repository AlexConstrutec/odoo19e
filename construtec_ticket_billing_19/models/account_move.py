# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    ticket_mirror_ids = fields.One2many(
        comodel_name='construtec.helpdesk.ticket.mirror', inverse_name='move_id',
        string='Tickets de Community',
        help='Tickets de Community ya vinculados a esta Factura - ver construtec.helpdesk.'
             'ticket.mirror.move_id.')
    ticket_mirror_count = fields.Integer(compute='_compute_ticket_mirror_count')
    available_ticket_mirror_ids = fields.Many2many(
        comodel_name='construtec.helpdesk.ticket.mirror',
        compute='_compute_available_ticket_mirror_ids',
        help='Auxiliar solo para el domain de `ticket_mirror_ids` en la vista - un Many2one/'
             'One2many no puede navegar un domain complejo (billing_state/is_closed) directo '
             'en un string de vista sin materializar un campo top-level primero (mismo '
             'patrón ya usado en construtec_account_payment_order_19 para `anticipos_'
             'disponibles_ids`/`available_payment_method_line_ids`). Incluye siempre los '
             'tickets YA vinculados a esta factura, aunque dejen de calificar después (ej. '
             'al postear, billing_state pasa a facturado) - si se pusiera el domain '
             'directo en el campo `ticket_mirror_ids`, un ticket ya vinculado desaparecería '
             'de la lista en cuanto cambiara de estado (mismo bug real ya documentado para '
             '`factura_ids`/`pago_ids` en ese otro módulo).')

    def _compute_ticket_mirror_count(self):
        for move in self:
            move.ticket_mirror_count = len(move.ticket_mirror_ids)

    def _compute_available_ticket_mirror_ids(self):
        Mirror = self.env['construtec.helpdesk.ticket.mirror']
        candidatos = Mirror.search([
            ('billing_state', '=', 'no_facturado'),
            ('is_closed', '=', True),
        ])
        for move in self:
            move.available_ticket_mirror_ids = candidatos | move.ticket_mirror_ids

    def action_view_ticket_mirrors(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'construtec_ticket_billing_19.construtec_helpdesk_ticket_mirror_action')
        action['domain'] = [('move_id', '=', self.id)]
        action['context'] = {}
        return action
