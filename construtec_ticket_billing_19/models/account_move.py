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

    def _compute_ticket_mirror_count(self):
        for move in self:
            move.ticket_mirror_count = len(move.ticket_mirror_ids)

    def action_view_ticket_mirrors(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'construtec_ticket_billing_19.construtec_helpdesk_ticket_mirror_action')
        action['domain'] = [('move_id', '=', self.id)]
        action['context'] = {}
        return action
