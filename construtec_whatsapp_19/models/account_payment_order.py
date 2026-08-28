# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import logging

from markupsafe import Markup

from odoo import models

_logger = logging.getLogger(__name__)


class AccountPaymentOrder(models.Model):
    _inherit = 'account.payment.order'

    def action_submit(self):
        res = super().action_submit()
        self._send_whatsapp_payment_order_notification('enviado')
        return res

    def action_approve(self):
        res = super().action_approve()
        self._send_whatsapp_payment_order_notification('aprobado')
        return res

    def action_aplicar(self):
        res = super().action_aplicar()
        self._send_whatsapp_payment_order_notification('aplicado')
        return res

    def action_conciliar(self):
        res = super().action_conciliar()
        self._send_whatsapp_payment_order_notification('liquidado')
        return res

    def _whatsapp_payment_order_params(self):
        """Variables {{1}}..{{4}} para CUALQUIER evento (Enviado/Aprobado/Aplicado/Liquidado) -
        mismo shape para los 4 a propósito (nombre de la Orden, contacto, monto, link), ya que
        las plantillas de Aprobado/Aplicado/Liquidado todavía no existen/no están aprobadas en
        Meta al momento de escribir esto. Si una plantilla futura necesita variables distintas
        para un evento en particular, este método puede partirse por evento entonces - no antes,
        para no adivinar una estructura que Meta podría rechazar de todas formas."""
        self.ensure_one()
        link = (f'{self.get_base_url()}/web#id={self.id}'
                f'&model=account.payment.order&view_type=form')
        return [
            self.name, self.partner_id.name or '',
            str(self.total_acreditar or self.monto or 0.0),
            link,
        ]

    def _send_whatsapp_payment_order_notification(self, state):
        """Notifica por WhatsApp cuando esta Orden llega al evento `state` (enviado/aprobado/
        aplicado/liquidado) - configuración 100% en WhatsApp > Notificaciones de Órdenes de Pago
        (`construtec.whatsapp.payment.order.notification`, un mapeo evento -> plantilla -> grupo
        de destinatarios, editable sin tocar código) + el interruptor general
        `company.payment_order_whatsapp_enabled`.

        Dos vías de destinatarios, no excluyentes (`notify_interesado` en la propia
        configuración): el grupo de destinatarios fijo de esa notificación (ej. Administración),
        y/o el propio contacto de la Orden (`partner_id`/`telefono` - el jefe de técnicos o
        empleado que la originó), deduplicados por número para no mandar el mismo mensaje dos
        veces si alguien está en ambos.

        Nunca bloquea la acción que la dispara: un fallo de configuración o de red en WhatsApp
        no debe impedir que la Orden avance de estado - mismo criterio que _sync_to_enterprise()
        en el módulo del que este depende.

        Deja SIEMPRE un rastro en el chatter de la propia Orden (pedido explícito del usuario)
        además del registro global (`construtec.whatsapp.log`, en Ajustes)."""
        for rec in self:
            company = rec.company_id
            if not company.payment_order_whatsapp_enabled:
                continue
            notif = self.env['construtec.whatsapp.payment.order.notification'].search([
                ('state', '=', state),
            ], limit=1)
            if not notif:
                continue
            template = notif.template_id
            if not template:
                _logger.info(
                    'Notificación de WhatsApp para el evento "%s" habilitada en %s pero sin '
                    'plantilla configurada - se omite.', state, company.name)
                continue

            destinatarios = []  # [(nombre, telefono), ...]
            if notif.recipient_group_id:
                for partner in notif.recipient_group_id.partner_ids.filtered('phone'):
                    destinatarios.append((partner.name, partner.phone))
            if notif.notify_interesado and rec.telefono:
                destinatarios.append((rec.partner_id.name or rec.env._('Interesado'), rec.telefono))
            # Dedupe por número normalizado - el interesado puede ya estar en el grupo fijo.
            vistos = set()
            unicos = []
            for nombre, telefono in destinatarios:
                clave = ''.join(ch for ch in telefono if ch.isdigit())
                if clave and clave not in vistos:
                    vistos.add(clave)
                    unicos.append((nombre, telefono))
            destinatarios = unicos

            if not destinatarios:
                rec.message_post(body=Markup(
                    '📱 <b>WhatsApp</b>: no se envió nada para el evento "%s" - sin grupo de '
                    'destinatarios con teléfono ni interesado con teléfono configurado.')
                    % dict(notif._fields['state'].selection).get(state, state))
                continue

            params = rec._whatsapp_payment_order_params()
            lineas = []
            for nombre, telefono in destinatarios:
                ok, mensaje = company._send_whatsapp_template(template, telefono, params)
                icono = '✅' if ok else '❌'
                linea = Markup('%s %s (%s)') % (icono, nombre, telefono)
                if not ok:
                    linea += Markup(' — %s') % mensaje
                lineas.append(linea)
            evento_label = dict(notif._fields['state'].selection).get(state, state)
            cuerpo = Markup('📱 <b>WhatsApp "%s"</b> (plantilla "%s"):<br/>') % (
                evento_label, template.name)
            cuerpo += Markup('<br/>').join(lineas)
            rec.message_post(body=cuerpo)
