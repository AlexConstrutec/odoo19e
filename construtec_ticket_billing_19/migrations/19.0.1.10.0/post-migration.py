# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Costeo F1 (2026-11-17): el costo real de los espejos pasa a la cascada por requisición (facturas
sin IVA o pagos, más traslados) y `costo_total`/`costo_general` pasan de valor empujado a calculado.
Se recalculan todos los espejos."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Mirror = env['construtec.helpdesk.ticket.mirror'].with_context(active_test=False)
    espejos = Mirror.search([])
    for nombre in ('costo_pagos', 'costo_facturas', 'costo_real', 'costo_total', 'costo_general'):
        env.add_to_compute(Mirror._fields[nombre], espejos)
    espejos.flush_recordset()
