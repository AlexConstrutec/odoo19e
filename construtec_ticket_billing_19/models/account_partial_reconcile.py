# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import api, models


class AccountPartialReconcile(models.Model):
    _inherit = 'account.partial.reconcile'

    def _apply_ticket_analytic_to_payments(self):
        """Pagos conciliados con un documento que nace de un ticket: llevan su misma distribución
        analítica (Ubicación + Área, 100 % cada plan) en las líneas de su asiento.
        - Proveedor: factura/nota ligada a una Requisición de Pago -> la distribución de la requisición.
        - Cliente: factura de venta con tickets -> la distribución de la factura.
        Solo líneas sin distribución propia (o con solo la Ubicación, en el caso de la requisición)."""
        for partial in self:
            moves = (partial.debit_move_id | partial.credit_move_id).move_id
            pagos = moves.filtered('origin_payment_id')
            for doc in moves - pagos:
                if doc.move_type in ('in_invoice', 'in_refund') and doc.payment_order_id:
                    for pago in pagos:
                        doc.payment_order_id._apply_ticket_analytic_to_lines(pago.line_ids)
                elif doc.move_type == 'out_invoice' and doc.ticket_mirror_ids:
                    distribucion = doc._compute_ticket_analytic_distribution()
                    if not distribucion:
                        continue
                    for pago in pagos:
                        vacias = pago.line_ids.filtered(lambda l: not l.analytic_distribution)
                        if vacias:
                            vacias.analytic_distribution = distribucion

    @api.model_create_multi
    def create(self, vals_list):
        partials = super().create(vals_list)
        partials._apply_ticket_analytic_to_payments()
        return partials
