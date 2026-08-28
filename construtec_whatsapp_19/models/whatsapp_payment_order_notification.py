# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import fields, models

# Mismos valores de account.payment.order.state que ya disparan un evento real en el ciclo de
# vida de un Anticipo/Anticipo Viáticos/Pago Directo - agregar un evento nuevo (ej. 'rechazado')
# significa agregar el valor aquí Y el trigger correspondiente en account_payment_order.py.
NOTIFICATION_STATES = [
    ('enviado', 'Enviado'),
    ('aprobado', 'Aprobado'),
    ('aplicado', 'Aplicado'),
    ('liquidado', 'Liquidado'),
]


class ConstructecWhatsAppPaymentOrderNotification(models.Model):
    _name = 'construtec.whatsapp.payment.order.notification'
    _description = ('Qué plantilla de WhatsApp (y a quién) se manda cuando una Orden de Pago '
                     'llega a un estado dado - un mapeo por evento en vez de un solo par '
                     'plantilla/grupo fijo, para poder agregar Aprobado/Aplicado/Liquidado (y '
                     'eventos futuros) como filas nuevas en esta lista, sin tocar código ni '
                     'agregar más campos a res.company cada vez.')
    _rec_name = 'state'

    state = fields.Selection(
        NOTIFICATION_STATES, string='Evento (estado de la Orden)', required=True,
        help='A qué transición de estado de la Orden de Pago dispara esta notificación - ver '
             'ANTICIPO_TIPOS/action_submit()/action_approve()/action_aplicar()/action_conciliar() '
             'en construtec_account_payment_order_19.')
    template_id = fields.Many2one(
        'construtec.whatsapp.template', string='Plantilla', required=True,
        help='Debe estar YA aprobada en Meta Business Manager con el número de variables que '
             'espera `_send_whatsapp_payment_order_notification()` en account_payment_order.py '
             '(hoy: nombre de la Orden, contacto, monto, link - verificar el contenido EXACTO '
             'de la plantilla en Meta antes de activar, un desajuste de cantidad de variables '
             'hace que Meta rechace el envío).')
    recipient_group_id = fields.Many2one(
        'construtec.whatsapp.recipient.group', string='Grupo de destinatarios',
        help='Opcional - se puede dejar vacío si esta notificación solo debe llegarle al '
             'interesado (ver el campo siguiente), sin avisar a ningún grupo fijo.')
    notify_interesado = fields.Boolean(
        string='Notificar también al interesado', default=True,
        help='Además del grupo de destinatarios (si hay uno), manda la misma plantilla al '
             'propio contacto/empleado de la Orden (`partner_id`/`telefono`) - útil para que el '
             'jefe de técnicos o el empleado se entere directamente de que su solicitud fue '
             'aprobada/aplicada/liquidada, no solo el equipo de Administración. Si el número '
             'coincide con uno ya presente en el grupo de destinatarios, no se duplica el envío.')
    active = fields.Boolean(default=True)
