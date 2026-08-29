from odoo import fields, models

CONCILIABLE_STATES = ('in_process', 'paid')


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    payment_order_id = fields.Many2one('account.payment.order', string='Orden de Pago', ondelete='restrict',
                                        store=True)

    def write(self, vals):
        afectados = self.env['account.payment']
        if 'state' in vals and vals['state'] not in CONCILIABLE_STATES:
            afectados = self.filtered(
                lambda p: p.state in CONCILIABLE_STATES and p.payment_order_id
                and p.payment_order_id.state == 'liquidado')
        res = super().write(vals)
        if afectados:
            nuevo_state_label = dict(self._fields['state'].selection).get(vals['state'], vals['state'])
            for orden in afectados.mapped('payment_order_id'):
                docs = afectados.filtered(lambda p, orden=orden: p.payment_order_id == orden)
                orden._reaccionar_a_documento_desconciliado(docs, nuevo_state_label)
        return res
