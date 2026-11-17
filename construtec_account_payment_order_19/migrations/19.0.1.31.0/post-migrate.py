# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Costeo F1 (2026-11-17): la base de las facturas pasa a ir SIN IVA, aparecen costo por pagos y
facturas con IVA, y el costo real pasa a ser en cascada (facturas, o pagos si no hay facturas).
Se recalcula todo lo ya guardado. En Community, los montos de pagos/facturas llegan con el siguiente
pull de estado (el compute solo conserva lo que ya hay)."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Order = env['account.payment.order'].with_context(active_test=False)
    orders = Order.search([])
    for nombre in ('costo_facturas', 'facturas_con_iva', 'costo_pagos', 'costo_real'):
        env.add_to_compute(Order._fields[nombre], orders)
    orders.flush_recordset()
