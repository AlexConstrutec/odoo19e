# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    materiales_catalogo_visible = fields.Boolean(
        string='Visible en Catálogo de Materiales', default=False,
        help='Solo un proveedor marcado aquí alimenta el Catálogo de Materiales '
             '(construtec.materials.catalog.mirror) - ni siquiera se materializa localmente en '
             'Enterprise, mucho menos viaja a Community, hasta que se marca. Curaduría deliberada '
             'a nivel de proveedor (decenas de proveedores), no por cada línea de factura '
             '(construtec.sat.product.catalog sigue registrando TODO como hasta ahora, esto solo '
             'controla qué llega al catálogo que ve el jefe de técnicos al pedir materiales) - '
             'evita que el catálogo se llene de líneas de combustible, servicios contables, etc.')
