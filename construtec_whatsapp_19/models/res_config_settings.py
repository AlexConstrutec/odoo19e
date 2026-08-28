# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    whatsapp_enabled = fields.Boolean(related='company_id.whatsapp_enabled', readonly=False)
    whatsapp_phone_number_id = fields.Char(
        related='company_id.whatsapp_phone_number_id', readonly=False)
    whatsapp_access_token = fields.Char(
        related='company_id.whatsapp_access_token', readonly=False)
    whatsapp_api_version = fields.Char(
        related='company_id.whatsapp_api_version', readonly=False)
    whatsapp_business_account_id = fields.Char(
        related='company_id.whatsapp_business_account_id', readonly=False)
    whatsapp_log_ids = fields.One2many(
        related='company_id.whatsapp_log_ids', string='Registro de WhatsApp')

    payment_order_whatsapp_enabled = fields.Boolean(
        related='company_id.payment_order_whatsapp_enabled', readonly=False)

    def action_test_whatsapp_connection(self):
        self.ensure_one()
        return self.company_id.action_test_whatsapp_connection()
