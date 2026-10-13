from odoo import api, models


class AccountPartialReconcile(models.Model):
    _inherit = 'account.partial.reconcile'

    def _ordenes_pago_directo(self):
        """Requisiciones de Pago Directo cuyas facturas participan en estas conciliaciones."""
        moves = (self.debit_move_id | self.credit_move_id).move_id
        return moves.filtered(
            lambda m: m.move_type in ('in_invoice', 'in_refund')
            and m.payment_order_id.tipo == 'pago_directo').payment_order_id

    @api.model_create_multi
    def create(self, vals_list):
        partials = super().create(vals_list)
        partials._ordenes_pago_directo()._sync_pagos_nativos()
        return partials

    def unlink(self):
        ordenes = self._ordenes_pago_directo()
        res = super().unlink()
        ordenes._sync_pagos_nativos()
        return res
