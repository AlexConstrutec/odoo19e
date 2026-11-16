# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Documentos SAT ya vinculados a una requisición con ticket heredan Ubicación y Área (solo vacíos)."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    docs = env['construtec.sat.document'].search(['|', ('payment_order_id', '!=', False), ('move_id.payment_order_id', '!=', False)])
    docs._heredar_analitica_de_requisicion()
