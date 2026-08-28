# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import fields, models


class ConstructecWhatsAppTemplate(models.Model):
    _name = 'construtec.whatsapp.template'
    _description = ('Referencia en Odoo a una plantilla de mensaje YA aprobada en Meta Business '
                     'Manager - este registro no crea ni aprueba nada en Meta, solo guarda el '
                     'nombre/idioma exactos para poder usarla al enviar.')

    name = fields.Char(
        string='Nombre interno', required=True,
        help='Solo para identificarla dentro de Odoo (ej. "Orden de Pago Enviada") - no se '
             'manda a Meta, es libre.')
    meta_template_name = fields.Char(
        string='Nombre exacto en Meta', required=True,
        help='Debe coincidir EXACTAMENTE con el nombre de la plantilla ya aprobada en Meta '
             'Business Manager (WhatsApp Manager > Cuentas > Plantillas de Mensajes). Si no '
             'coincide exacto, la API la rechaza.')
    meta_template_language = fields.Char(
        string='Código de idioma', required=True, default='es',
        help='El código de idioma con el que se aprobó la plantilla en Meta (ej. "es", '
             '"es_MX", "en_US") - debe coincidir exacto, es parte de cómo Meta identifica la '
             'plantilla junto con el nombre.')
    param_help = fields.Text(
        string='Recordatorio de variables',
        help='Texto libre, solo de referencia para quien configure esto: qué representa cada '
             '{{1}}, {{2}}... de esta plantilla, en el orden en que hay que mandarlos al enviar.')
    active = fields.Boolean(default=True)
