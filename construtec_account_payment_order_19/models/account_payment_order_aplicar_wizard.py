from odoo import fields, models


class AccountPaymentOrderAplicarWizard(models.TransientModel):
    _name = 'account.payment.order.aplicar.wizard'
    _description = (
        'Pregunta al contador, al presionar Aplicar en una Requisición de Pago, si Odoo debe generar '
        'el pago o solo aplicar la requisición (2026-11-05, pedido del usuario).'
    )

    order_id = fields.Many2one('account.payment.order', string='Requisición', required=True,
                               readonly=True, ondelete='cascade')

    def action_con_pago(self):
        self.ensure_one()
        return self.order_id._aplicar(crear_pago=True)

    def action_sin_pago(self):
        self.ensure_one()
        return self.order_id._aplicar(crear_pago=False)
