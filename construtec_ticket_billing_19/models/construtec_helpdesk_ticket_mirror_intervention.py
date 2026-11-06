# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import fields, models


class ConstructecHelpdeskTicketMirrorIntervention(models.Model):
    _name = 'construtec.helpdesk.ticket.mirror.intervention'
    _description = 'Intervención directa de un ticket de Community (espejo)'
    _order = 'fecha desc, id desc'

    mirror_id = fields.Many2one(
        'construtec.helpdesk.ticket.mirror', required=True, ondelete='cascade', index=True)
    origin_id = fields.Integer(string='ID en Community', readonly=True)
    fecha = fields.Date()
    tecnico = fields.Char(string='Quién')
    observacion = fields.Text(string='Observación')
    monto = fields.Monetary(currency_field='currency_id')
    currency_id = fields.Many2one(related='mirror_id.currency_id', store=True)
