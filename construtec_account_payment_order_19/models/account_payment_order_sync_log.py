from odoo import fields, models


class AccountPaymentOrderSyncLog(models.Model):
    _name = 'account.payment.order.sync.log'
    _description = 'Registro de sincronización de Solicitudes de Pago'
    _order = 'create_date desc'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    success = fields.Boolean(string='Éxito')
    message = fields.Text(string='Resultado', required=True)
