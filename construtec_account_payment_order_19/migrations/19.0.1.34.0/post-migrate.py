# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Los empleados que ya tenían departamento antes de la distribución analítica del departamento se
quedaron sin ella (solo se hereda al elegir o cambiar el departamento). Se rellena a todos los que no
tienen una propia con la de su departamento; nunca se pisa una existente (2026-11-17)."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    versiones = env['hr.version'].with_context(active_test=False).search([('department_id', '!=', False)])
    versiones._heredar_distribucion_departamento()
