# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Reaplica Ubicacion+Area a lo contabilizado de las requisiciones con ticket (una creada en
Enterprise y ligada a mano a un ticket ya no se suelta al reenviar el ticket)."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['account.payment.order'].search([('ticket_mirror_id', '!=', False)])._apply_ticket_analytic_to_documents()
