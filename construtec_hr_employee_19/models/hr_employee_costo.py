# License LGPL-3.0
"""Costo del empleado (F3, 2026-11-17): en Enterprise suma la bonificación incentivo al costo mensual.
El cálculo base vive en `construtec_account_payment_order_19` (`hr.employee._compute_costo_personal`)."""
from odoo import api, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    @api.depends('x_bonificacion_incentivo')
    def _compute_costo_personal(self):
        return super()._compute_costo_personal()

    def _costo_bonificacion(self):
        self.ensure_one()
        return super()._costo_bonificacion() + (self.sudo().x_bonificacion_incentivo or 0.0)
