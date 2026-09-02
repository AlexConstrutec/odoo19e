# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import fields, models


class ConstructecMaterialsVendorMirror(models.Model):
    _name = 'construtec.materials.vendor.mirror'
    _description = (
        'Proveedores conocidos - derivados de TODOS los Documentos SAT recibidos en Enterprise '
        '(construtec.sat.document, direction=recibida), no solo los que ya tienen materiales '
        'catalogados. Mismo patrón que construtec.materials.catalog.mirror: mismo `_name` '
        'instalado en Enterprise y en Community, poblado en Community por un pull propio '
        '(res_company.py::_sync_vendor_catalog_from_enterprise(), mismo toggle/cron/botón que '
        'ya existe para el Catálogo de Materiales) - a diferencia del catálogo de productos, '
        'Enterprise no necesita una copia local de este modelo (nada lo consume ahí todavía), '
        'se mantiene dual-deploy solo por consistencia con el resto de este módulo. También se '
        'crean entradas aquí localmente en Community, sin `origin_id`, cuando "Cargar '
        'Cotización" (construtec_account_payment_order_19) extrae un proveedor que no calza con '
        'ninguno conocido - ver `pendiente_verificar`.'
    )
    _order = 'name'

    origin_id = fields.Integer(
        string='ID en Enterprise', index=True,
        help='El id real del res.partner en Enterprise (de un Documento SAT recibido) - clave de '
             'actualización (upsert). Vacío en entradas creadas localmente desde una cotización '
             'con IA - ver `pendiente_verificar`.')
    name = fields.Char(string='Proveedor', required=True)
    nit = fields.Char(string='NIT')
    pendiente_verificar = fields.Boolean(
        string='Pendiente de Verificar', default=False,
        help='Marcado en proveedores creados automáticamente desde una cotización cargada con '
             'IA ("Cargar Cotización") que no calzaron con ningún proveedor ya conocido - no '
             'vienen de ningún Documento SAT real todavía.')
    company_id = fields.Many2one('res.company', string='Compañía')
    received_date = fields.Datetime(
        string='Última Recepción', default=fields.Datetime.now, readonly=True)

    _origin_id_uniq = models.Constraint(
        'unique(origin_id)',
        'Ya existe una entrada de proveedor para ese id de origen en Enterprise.',
    )
