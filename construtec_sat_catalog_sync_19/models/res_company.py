import logging

from odoo import api, fields, models

from ..tools.enterprise_sync_api import EnterpriseSyncError, fetch_materials_catalog, fetch_vendor_catalog

_logger = logging.getLogger(__name__)

MATERIALS_CATALOG_SYNC_CRON_XMLID = (
    'construtec_sat_catalog_sync_19.ir_cron_materials_catalog_sync')


class ResCompany(models.Model):
    _inherit = 'res.company'

    materials_catalog_sync_enabled = fields.Boolean(
        string='Sincronización del Catálogo de Materiales Habilitada',
        help='Si está activo, esta compañía jala periódicamente (y bajo demanda) la copia local '
             'de Enterprise del Catálogo de Materiales (construtec.materials.catalog.mirror) - '
             'mismo patrón "pull" ya usado para empleados/cuentas analíticas en '
             'construtec_account_payment_order_19, replicado aquí de forma independiente porque '
             'este módulo es deliberadamente standalone (depends=[\'base\'] solamente). '
             'Reemplaza el diseño anterior, donde Enterprise empujaba esto por XML-RPC.')
    materials_catalog_sync_url = fields.Char(string='URL de Enterprise')
    materials_catalog_sync_db = fields.Char(string='Base de Datos de Enterprise')
    materials_catalog_sync_login = fields.Char(string='Usuario de Integración en Enterprise')
    materials_catalog_sync_api_key = fields.Char(string='API Key de Enterprise')
    materials_catalog_sync_interval_number = fields.Integer(
        string='Sincronizar Catálogo de Materiales cada', default=1)
    materials_catalog_sync_interval_type = fields.Selection([
        ('minutes', 'Minutos'),
        ('hours', 'Horas'),
        ('days', 'Días'),
    ], string='Unidad del intervalo (Catálogo de Materiales)', default='hours')

    def _apply_materials_catalog_sync_interval_to_cron(self):
        """Mismo patrón/limitación que el resto de los cron de sincronización de este proyecto
        (un solo cron global, no por compañía) - ver construtec_account_payment_order_19/
        models/res_company.py, _apply_employee_sync_interval_to_cron()."""
        self.ensure_one()
        cron = self.env.ref(MATERIALS_CATALOG_SYNC_CRON_XMLID, raise_if_not_found=False)
        if cron:
            cron.sudo().write({
                'interval_number': self.materials_catalog_sync_interval_number or 1,
                'interval_type': self.materials_catalog_sync_interval_type or 'hours',
            })

    def _sync_materials_catalog_from_enterprise(self):
        """Pull directo de la copia local de Enterprise del Catálogo de Materiales
        (construtec.materials.catalog.mirror) - reemplaza el diseño anterior (Enterprise
        empujando por XML-RPC hacia Community en cada cambio, ver CLAUDE.md). Reutiliza el
        `sync_from_enterprise()` ya existente en este mismo modelo para el upsert - el mismo
        método que antes solo recibía la llamada RPC entrante, ahora también llamado
        localmente con lo que se acaba de traer. Upsert por `origin_id` (el id de la entrada en
        `construtec.sat.product.catalog`, Enterprise) - el mismo contrato de siempre, sin
        cambios en ese método."""
        self.ensure_one()
        if not self.materials_catalog_sync_enabled:
            return True, self.env._('Sincronización del Catálogo de Materiales no habilitada.')
        try:
            entries = fetch_materials_catalog(
                self.materials_catalog_sync_url, self.materials_catalog_sync_db,
                self.materials_catalog_sync_login, self.materials_catalog_sync_api_key)
        except EnterpriseSyncError as exc:
            _logger.warning(
                'Sincronización del Catálogo de Materiales falló para %s: %s', self.name, exc)
            return False, str(exc)

        Mirror = self.env['construtec.materials.catalog.mirror'].sudo()
        for entry in entries:
            vals = dict(entry)
            vals.pop('id', None)
            Mirror.sync_from_enterprise(vals)
        message = self.env._('%(count)s entradas procesadas.', count=len(entries))
        return True, message

    def _sync_vendor_catalog_from_enterprise(self):
        """Pull de los proveedores conocidos (derivados de TODOS los Documentos SAT recibidos
        en Enterprise) - se cuelga del MISMO toggle/intervalo/cron/botón que ya existe para el
        Catálogo de Materiales (`materials_catalog_sync_enabled`), no de uno nuevo: es el mismo
        concern ("mantener fresca mi copia de referencia SAT"), no vale la pena un segundo
        bloque de Ajustes para esto. Upsert directo por `origin_id` (el id del `res.partner` en
        Enterprise) - a diferencia del Catálogo de Materiales, no hay ningún `sync_from_enterprise()`
        que reutilizar aquí (este modelo nunca recibe una llamada RPC entrante, solo pull), así
        que el upsert se hace directo con search+write/create."""
        self.ensure_one()
        if not self.materials_catalog_sync_enabled:
            return True, self.env._('Sincronización de Proveedores no habilitada.')
        try:
            proveedores = fetch_vendor_catalog(
                self.materials_catalog_sync_url, self.materials_catalog_sync_db,
                self.materials_catalog_sync_login, self.materials_catalog_sync_api_key)
        except EnterpriseSyncError as exc:
            _logger.warning('Sincronización de Proveedores falló para %s: %s', self.name, exc)
            return False, str(exc)

        Vendor = self.env['construtec.materials.vendor.mirror'].sudo()
        for proveedor in proveedores:
            existente = Vendor.search([('origin_id', '=', proveedor['origin_id'])], limit=1)
            vals = {
                'origin_id': proveedor['origin_id'],
                'name': proveedor['name'],
                'nit': proveedor['nit'],
                'received_date': fields.Datetime.now(),
            }
            if existente:
                existente.write(vals)
            else:
                Vendor.create(vals)
        message = self.env._('%(count)s proveedores procesados.', count=len(proveedores))
        return True, message

    def action_sync_materials_catalog_now(self):
        self.ensure_one()
        ok_materiales, message_materiales = self._sync_materials_catalog_from_enterprise()
        ok_proveedores, message_proveedores = self._sync_vendor_catalog_from_enterprise()
        ok = ok_materiales and ok_proveedores
        message = self.env._(
            'Catálogo de Materiales: %(message_materiales)s\nProveedores: %(message_proveedores)s',
            message_materiales=message_materiales, message_proveedores=message_proveedores)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._('Sincronización del Catálogo de Materiales'),
                'message': message,
                'sticky': not ok,
                'type': 'success' if ok else 'danger',
            },
        }

    @api.model
    def _cron_sync_materials_catalog_from_enterprise(self):
        for company in self.search([('materials_catalog_sync_enabled', '=', True)]):
            company._sync_materials_catalog_from_enterprise()
            company._sync_vendor_catalog_from_enterprise()

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        companies._apply_materials_catalog_sync_interval_to_cron()
        return companies

    def write(self, vals):
        res = super().write(vals)
        if ('materials_catalog_sync_interval_number' in vals
                or 'materials_catalog_sync_interval_type' in vals):
            self._apply_materials_catalog_sync_interval_to_cron()
        return res
