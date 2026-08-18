from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    payment_order_role = fields.Selection([
        ('solicitante', 'Solicitante'),
        ('procesador', 'Procesador'),
    ], string='Rol de Solicitudes de Pago', default='procesador', required=True,
        help='Solicitante: esta instalación captura y aprueba Solicitudes de Pago (ej. Odoo '
             'Community, donde un jefe de técnicos pide viáticos) y las sincroniza hacia la '
             'instalación Procesadora. Procesador: esta instalación recibe Solicitudes ya '
             'aprobadas y las convierte en Órdenes de Pago reales (ej. Odoo Enterprise, donde '
             'Contabilidad revisa y aplica el Anticipo). El valor por defecto (Procesador) deja '
             'el comportamiento actual sin cambios.')

    payment_order_sync_enabled = fields.Boolean(string='Sincronización de Solicitudes de Pago Habilitada')
    payment_order_sync_url = fields.Char(
        string='URL de la instalación Procesadora',
        help='URL base de la instalación Odoo que procesa las Solicitudes de Pago, '
             'p. ej. https://enterprise.miempresa.com. Use HTTPS en producción.')
    payment_order_sync_db = fields.Char(string='Base de Datos de la instalación Procesadora')
    payment_order_sync_login = fields.Char(
        string='Usuario de Integración en la instalación Procesadora',
        help='Use un usuario de servicio dedicado con permisos mínimos (solo crear Solicitudes '
             'de Pago) en la instalación Procesadora, no un administrador.')
    payment_order_sync_api_key = fields.Char(
        string='API Key de la instalación Procesadora',
        help='API Key generada en la instalación Procesadora para el usuario de integración '
             '(Ajustes > Mi Perfil > Seguridad de la cuenta > Nueva clave API). '
             'No usar la contraseña del usuario.')
    payment_order_sync_log_ids = fields.One2many(
        comodel_name='account.payment.order.sync.log',
        inverse_name='company_id',
        string='Registro de Sincronización de Solicitudes de Pago')

    def _payment_order_sync_log(self, success, message):
        self.ensure_one()
        self.env['account.payment.order.sync.log'].sudo().create(
            {'company_id': self.id, 'success': success, 'message': message})
