# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Los Documentos SAT de requisiciones con ticket heredan Ubicación y Área. La migración de
construtec_account_19 corrió antes de cargar los campos de este módulo y no los vio."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['account.payment.order'].search([('ticket_mirror_id', '!=', False)])._apply_ticket_analytic_to_documents()
