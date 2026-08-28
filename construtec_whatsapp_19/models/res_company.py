# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import logging

from odoo import fields, models

from ..tools.whatsapp_api import DEFAULT_API_VERSION, WhatsAppApiError, check_phone_number, \
    send_whatsapp_template

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = 'res.company'

    whatsapp_enabled = fields.Boolean(string='WhatsApp Habilitado')
    whatsapp_phone_number_id = fields.Char(string='Phone Number ID')
    whatsapp_access_token = fields.Char(
        string='Access Token',
        help='Usa un token PERMANENTE (System User con permiso whatsapp_business_messaging) '
             'para cualquier envío automático - el token temporal de 24h del panel de pruebas '
             'de Meta expira y el envío empezaría a fallar sin aviso.')
    whatsapp_api_version = fields.Char(string='Versión de la API', default=DEFAULT_API_VERSION)
    whatsapp_business_account_id = fields.Char(
        string='WhatsApp Business Account ID (WABA)',
        help='Solo de referencia - las plantillas se crean y aprueban en Meta Business Manager, '
             'no desde aquí. Sirve para no perder de vista a cuál WABA pertenece esta '
             'configuración, especialmente si más adelante se cambia a la cuenta oficial de la '
             'empresa.')
    whatsapp_log_ids = fields.One2many(
        'construtec.whatsapp.log', 'company_id', string='Registro de WhatsApp')

    payment_order_whatsapp_enabled = fields.Boolean(
        string='Notificar Órdenes de Pago por WhatsApp',
        help='Interruptor general - si está apagado, ninguna notificación de Orden de Pago se '
             'manda, sin importar qué eventos estén configurados en WhatsApp > Notificaciones '
             'de Órdenes de Pago (`construtec.whatsapp.payment.order.notification`).')

    def _whatsapp_log(self, success, message, to_number=False, template=False):
        self.ensure_one()
        self.env['construtec.whatsapp.log'].sudo().create({
            'company_id': self.id,
            'success': success,
            'message': message,
            'to_number': to_number,
            'template_id': template and template.id,
        })

    def _send_whatsapp_template(self, template, to_number, params=None, button_param=None):
        """Envía UNA plantilla pre-aprobada a UN número. Quien llame a esto (ej.
        account.payment.order) resuelve la lista de destinatarios y llama esto una vez por cada
        uno - un "grupo" en este módulo es una lista de contactos en Odoo, no un grupo real de
        WhatsApp (la API oficial de Meta no soporta enviar a grupos).

        `button_param`: la parte dinámica de un botón "Sitio web" configurado en la plantilla
        (ver `send_whatsapp_template()` en tools/whatsapp_api.py) - opcional, solo aplica si la
        plantilla tiene ese tipo de botón.

        Nunca lanza - mismo criterio que el resto de integraciones externas de este proyecto
        (ej. _sync_to_enterprise() en construtec_account_payment_order_19): un fallo de WhatsApp
        no debe romper el flujo de negocio que lo dispara, solo queda registrado en el log."""
        self.ensure_one()
        if not self.whatsapp_enabled:
            return False, self.env._('Envío de WhatsApp deshabilitado para esta compañía.')
        try:
            send_whatsapp_template(
                self.whatsapp_phone_number_id, self.whatsapp_access_token,
                self.whatsapp_api_version, to_number,
                template.meta_template_name, template.meta_template_language, params,
                button_param)
        except WhatsAppApiError as exc:
            _logger.warning('Envío de WhatsApp a %s falló: %s', to_number, exc)
            self._whatsapp_log(False, str(exc), to_number, template)
            return False, str(exc)
        message = self.env._('Mensaje enviado.')
        self._whatsapp_log(True, message, to_number, template)
        return True, message

    def action_test_whatsapp_connection(self):
        self.ensure_one()
        ok, result = check_phone_number(
            self.whatsapp_phone_number_id, self.whatsapp_access_token, self.whatsapp_api_version)
        if ok:
            message = self.env._(
                'Conectado: %(nombre)s (%(numero)s) - calidad: %(calidad)s',
                nombre=result.get('verified_name', '?'),
                numero=result.get('display_phone_number', '?'),
                calidad=result.get('quality_rating', '?'))
        else:
            message = result
        self._whatsapp_log(ok, message)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._('Conexión WhatsApp'),
                'message': message,
                'type': 'success' if ok else 'danger',
                'sticky': not ok,
            },
        }
