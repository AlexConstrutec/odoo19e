# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import fields, models


class ConstructecWhatsAppLog(models.Model):
    _name = 'construtec.whatsapp.log'
    _description = 'Registro de intentos de envío de WhatsApp (éxito o error)'
    _order = 'create_date desc'

    company_id = fields.Many2one('res.company', required=True, ondelete='cascade')
    success = fields.Boolean()
    message = fields.Text()
    to_number = fields.Char(string='Destinatario')
    template_id = fields.Many2one('construtec.whatsapp.template', string='Plantilla')
