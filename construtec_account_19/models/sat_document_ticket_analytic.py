# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import api, models


class ConstrutecSatDocument(models.Model):
    _inherit = 'construtec.sat.document'

    def _heredar_analitica_de_requisicion(self):
        """Un Documento SAT vinculado a una Requisición de Pago con ticket toma la Ubicación y el
        Área del ticket (solo si están vacías: nunca pisa lo que el contable ya puso). Los campos
        `area_analytic_account_id`/`ticket_mirror_id` de la requisición los define
        construtec_ticket_billing_19, por eso se leen con getattr (este módulo no depende de él)."""
        for doc in self:
            orden = doc.payment_order_id or doc.move_id.payment_order_id
            if not orden:
                continue
            mirror = getattr(orden, 'ticket_mirror_id', False)
            ubicacion = orden.analytic_account_id or (mirror and mirror.analytic_account_id)
            area = getattr(orden, 'area_analytic_account_id', False) or (
                mirror and mirror.area_analytic_account_id)
            vals = {}
            if ubicacion and not doc.cuenta_analitica_id:
                vals['cuenta_analitica_id'] = ubicacion.id
            if area and not doc.area_negocio_id:
                vals['area_negocio_id'] = area.id
            if vals:
                doc.write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        docs = super().create(vals_list)
        docs.filtered(lambda d: d.payment_order_id or d.move_id)._heredar_analitica_de_requisicion()
        return docs

    def write(self, vals):
        res = super().write(vals)
        if 'payment_order_id' in vals or 'move_id' in vals:
            self._heredar_analitica_de_requisicion()
        return res
