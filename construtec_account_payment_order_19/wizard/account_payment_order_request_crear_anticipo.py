from odoo import fields, models
from odoo.exceptions import UserError


class AccountPaymentOrderRequestCrearAnticipoWizard(models.TransientModel):
    _name = 'account.payment.order.request.crear.anticipo.wizard'
    _description = 'Crear Anticipo desde una Solicitud de Pago'

    request_id = fields.Many2one('account.payment.order.request', string='Solicitud',
                                  required=True, readonly=True)
    partner_id = fields.Many2one('res.partner', string='Contacto', required=True,
                                  help='Contacto que recibirá el Anticipo. No se recibe automáticamente '
                                       'de la Solicitud: resuélvalo/créelo aquí, ya que la instalación '
                                       'donde se originó la Solicitud es una base distinta.')
    journal_id = fields.Many2one('account.journal', string='Diario', required=True)
    payment_method_line_id = fields.Many2one(
        'account.payment.method.line', string='Método de Pago',
        domain="[('id', 'in', journal_id.outbound_payment_method_line_ids)]")
    cuenta_anticipo_id = fields.Many2one(
        'account.account', string='Cuenta de Anticipos por Liquidar', required=True,
        domain=[('account_type', 'in', ('asset_receivable', 'liability_payable'))])
    monto = fields.Float(string='Monto', required=True)

    def action_confirmar(self):
        self.ensure_one()
        if self.request_id.payment_order_id:
            raise UserError(self.env._('Esta solicitud ya tiene una Orden de Pago asociada.'))

        vals = {
            'tipo': 'anticipo',
            'partner_id': self.partner_id.id,
            'journal_id': self.journal_id.id,
            'cuenta_anticipo_id': self.cuenta_anticipo_id.id,
            'monto': self.monto,
        }
        if self.payment_method_line_id:
            vals['payment_method_line_id'] = self.payment_method_line_id.id
        payment_order = self.env['account.payment.order'].create(vals)
        self.request_id.payment_order_id = payment_order.id

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment.order',
            'view_mode': 'form',
            'res_id': payment_order.id,
            'target': 'current',
        }
