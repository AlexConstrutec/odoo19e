# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import fields, models


class ConstructecWhatsAppRecipientGroup(models.Model):
    _name = 'construtec.whatsapp.recipient.group'
    _description = ('Lista de contactos a notificar por WhatsApp - NO es un grupo real de '
                     'WhatsApp (la API oficial de Meta no soporta enviar a grupos, solo 1:1); '
                     'esto es una lista en Odoo que, al enviar, dispara un mensaje individual a '
                     'cada contacto de la lista.')

    name = fields.Char(required=True, help='Ej. "Aprobadores Nivel Alto".')
    partner_ids = fields.Many2many(
        'res.partner', string='Contactos',
        help='El número usado para enviar es `partner.phone` - res.partner en Odoo 19 ya no '
             'tiene un campo `mobile` separado.')
    active = fields.Boolean(default=True)

    def _get_phone_numbers(self):
        self.ensure_one()
        return [partner.phone for partner in self.partner_ids if partner.phone]
