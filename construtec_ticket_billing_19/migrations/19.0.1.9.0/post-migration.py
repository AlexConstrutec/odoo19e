# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Aplica Ubicación + Área a notas de crédito/débito de proveedor y a los pagos registrados desde la
factura (no solo los de la requisición) de requisiciones con ticket."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['account.payment.order'].search([('ticket_mirror_id', '!=', False)])._apply_ticket_analytic_to_documents()
