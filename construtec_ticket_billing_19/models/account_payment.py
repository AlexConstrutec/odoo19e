# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def action_post(self):
        """Los pagos de una Requisición de Pago llevan la distribución analítica del ticket
        (Ubicación + Área, 100 % cada plan) en las líneas de su asiento."""
        res = super().action_post()
        for payment in self.filtered('payment_order_id'):
            payment.payment_order_id._apply_ticket_analytic_to_lines(payment.move_id.line_ids)
        return res
