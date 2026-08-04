from odoo import api, fields, models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    payment_order_id = fields.Many2one('account.payment.order', string='Orden de Pago', ondelete='restrict',
                                        store=True)
    no_liquidacion = fields.Integer(string='No. Liquidación', store=True,
                                     related='payment_order_id.no_liquidacion', readonly=False)

    @api.onchange('no_liquidacion')
    def _onchange_no_liquidacion(self):
        if self.no_liquidacion:
            orden = self.env['account.payment.order'].search([('no_liquidacion', '=', self.no_liquidacion)], limit=1)
            if orden:
                self.payment_order_id = orden.id

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec, vals in zip(records, vals_list):
            if vals.get('no_liquidacion') and not rec.payment_order_id:
                orden = self.env['account.payment.order'].search(
                    [('no_liquidacion', '=', vals['no_liquidacion'])], limit=1)
                if orden:
                    rec.payment_order_id = orden.id
        return records

    def write(self, vals):
        res = super().write(vals)
        if vals.get('no_liquidacion'):
            orden = self.env['account.payment.order'].search(
                [('no_liquidacion', '=', vals['no_liquidacion'])], limit=1)
            if orden:
                self.payment_order_id = orden.id
        return res
