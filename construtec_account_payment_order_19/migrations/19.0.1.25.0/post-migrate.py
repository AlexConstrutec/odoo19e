# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""`costo_facturas` pasó de subtotal sin IVA a total con IVA (2026-10-27). Un campo guardado no se
recalcula solo al cambiar la fórmula: se recalcula aquí para las requisiciones del lado Enterprise
(en Community el valor viene del pull de estado y se actualiza solo en la siguiente corrida)."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    ordenes = env['account.payment.order'].search(
        [('company_id.payment_order_role', '=', 'procesador')])
    if ordenes:
        env.add_to_compute(env['account.payment.order']._fields['costo_facturas'], ordenes)
        ordenes.flush_recordset(['costo_facturas'])
