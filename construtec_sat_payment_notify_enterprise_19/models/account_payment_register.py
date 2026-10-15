from odoo import api, fields, models


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    notify_supplier_whatsapp = fields.Boolean(
        string='Avisar al proveedor por WhatsApp', default=False,
        help='Community le manda al proveedor un WhatsApp avisando de este pago (≤ 20 min). Solo '
             'para facturas que vienen de un Documento SAT.')
    can_notify_supplier_whatsapp = fields.Boolean(compute='_compute_can_notify_supplier_whatsapp')

    @api.depends('partner_type', 'payment_type', 'line_ids')
    def _compute_can_notify_supplier_whatsapp(self):
        for wizard in self:
            wizard.can_notify_supplier_whatsapp = (
                wizard.partner_type == 'supplier' and wizard.payment_type == 'outbound'
                and bool(wizard.line_ids.move_id.sat_document_id))

    def _create_payment_vals_from_wizard(self, batch_result):
        vals = super()._create_payment_vals_from_wizard(batch_result)
        if self.notify_supplier_whatsapp and self.can_notify_supplier_whatsapp:
            vals['notify_supplier_whatsapp'] = True
        return vals

    def _create_payment_vals_from_batch(self, batch_result):
        vals = super()._create_payment_vals_from_batch(batch_result)
        if self.notify_supplier_whatsapp and self.can_notify_supplier_whatsapp:
            vals['notify_supplier_whatsapp'] = True
        return vals
