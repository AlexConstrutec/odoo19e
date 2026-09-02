from odoo import fields, models

from ..tools.enterprise_sync_api import EnterpriseSyncError, check_connection


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    payment_order_role = fields.Selection(related='company_id.payment_order_role', readonly=False)
    payment_order_habilitar_anticipo = fields.Boolean(
        related='company_id.payment_order_habilitar_anticipo', readonly=False)
    payment_order_habilitar_anticipo_viaticos = fields.Boolean(
        related='company_id.payment_order_habilitar_anticipo_viaticos', readonly=False)
    payment_order_habilitar_pago_directo = fields.Boolean(
        related='company_id.payment_order_habilitar_pago_directo', readonly=False)
    payment_order_habilitar_anticipo_materiales = fields.Boolean(
        related='company_id.payment_order_habilitar_anticipo_materiales', readonly=False)
    payment_order_approval_threshold = fields.Monetary(
        related='company_id.payment_order_approval_threshold', readonly=False)
    payment_order_sync_enabled = fields.Boolean(
        related='company_id.payment_order_sync_enabled', readonly=False)
    payment_order_sync_url = fields.Char(related='company_id.payment_order_sync_url', readonly=False)
    payment_order_sync_db = fields.Char(related='company_id.payment_order_sync_db', readonly=False)
    payment_order_sync_login = fields.Char(related='company_id.payment_order_sync_login', readonly=False)
    payment_order_sync_api_key = fields.Char(
        related='company_id.payment_order_sync_api_key', readonly=False)
    payment_order_sync_log_ids = fields.One2many(
        related='company_id.payment_order_sync_log_ids',
        string='Registro de Sincronización de Solicitudes de Pago')
    employee_sync_interval_number = fields.Integer(
        related='company_id.employee_sync_interval_number', readonly=False)
    employee_sync_interval_type = fields.Selection(
        related='company_id.employee_sync_interval_type', readonly=False)
    payment_order_status_sync_interval_number = fields.Integer(
        related='company_id.payment_order_status_sync_interval_number', readonly=False)
    payment_order_status_sync_interval_type = fields.Selection(
        related='company_id.payment_order_status_sync_interval_type', readonly=False)
    payment_order_default_company_id = fields.Many2one(
        related='company_id.payment_order_default_company_id', readonly=False)
    materials_catalog_sync_enabled = fields.Boolean(
        related='company_id.materials_catalog_sync_enabled', readonly=False)
    materials_catalog_sync_interval_number = fields.Integer(
        related='company_id.materials_catalog_sync_interval_number', readonly=False)
    materials_catalog_sync_interval_type = fields.Selection(
        related='company_id.materials_catalog_sync_interval_type', readonly=False)
    anthropic_api_key = fields.Char(related='company_id.anthropic_api_key', readonly=False)

    def action_sync_employees_now(self):
        self.ensure_one()
        return self.company_id.action_sync_employees_now()

    def action_sync_materials_catalog_now(self):
        self.ensure_one()
        return self.company_id.action_sync_materials_catalog_now()

    def action_pull_payment_order_status_now(self):
        self.ensure_one()
        return self.company_id.action_pull_payment_order_status_now()

    def action_test_payment_order_sync_connection(self):
        self.ensure_one()
        try:
            uid, version_info = check_connection(
                self.payment_order_sync_url,
                self.payment_order_sync_db,
                self.payment_order_sync_login,
                self.payment_order_sync_api_key,
            )
            message = self.env._(
                'Conectado (%(server_version)s) como uid %(uid)s.',
                server_version=(version_info or {}).get('server_version', '?'),
                uid=uid,
            )
            notif_type = 'success'
            ok = True
        except EnterpriseSyncError as exc:
            message = str(exc)
            notif_type = 'danger'
            ok = False
        self.company_id._payment_order_sync_log(ok, message)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._('Sincronización de Solicitudes de Pago'),
                'message': message,
                'type': notif_type,
                'sticky': notif_type == 'danger',
            },
        }
