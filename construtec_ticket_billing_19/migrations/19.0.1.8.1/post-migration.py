# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Amplía a Ubicación + Área las líneas que quedaron solo con la Ubicación (19.0.1.8.0) en
facturas de proveedor, pagos y asientos de requisiciones con ticket."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['account.payment.order'].search([('ticket_mirror_id', '!=', False)])._apply_ticket_analytic_to_documents()
