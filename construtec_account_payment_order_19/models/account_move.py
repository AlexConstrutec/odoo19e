from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    payment_order_id = fields.Many2one('account.payment.order', string='Orden de Pago', ondelete='restrict',
                                        store=True)

    def write(self, vals):
        afectadas = self.env['account.move']
        if 'state' in vals and vals['state'] != 'posted':
            afectadas = self.filtered(
                lambda m: m.state == 'posted' and m.payment_order_id
                and m.payment_order_id.state == 'liquidado')
        res = super().write(vals)
        if afectadas:
            nuevo_state_label = dict(self._fields['state'].selection).get(vals['state'], vals['state'])
            for orden in afectadas.mapped('payment_order_id'):
                docs = afectadas.filtered(lambda m, orden=orden: m.payment_order_id == orden)
                orden._reaccionar_a_documento_desconciliado(docs, nuevo_state_label)
        return res
