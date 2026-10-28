# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Recalcula `res.partner.employee` de todos los contactos con ficha de empleado: algunos se quedaron
en falso (ej. Mynor Rodrigo Mijangos Cotí, 2026-10-28) y no aparecían en los selectores de técnico."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    empleados = env['hr.employee'].with_context(active_test=False).search([])
    partners = empleados.mapped('work_contact_id')
    if partners:
        env.add_to_compute(partners._fields['employee'], partners)
        partners.flush_recordset(['employee'])
