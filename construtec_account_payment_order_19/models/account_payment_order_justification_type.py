from odoo import api, fields, models


class AccountPaymentOrderJustificationType(models.Model):
    _name = 'account.payment.order.justification.type'
    _description = 'Tipo de Justificación de Solicitud de Pago'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    @api.model
    def _find_or_create_by_name(self, name):
        """Resuelve un tipo de justificación por nombre (nunca por id - ver
        account_payment_order_request.py: solo el nombre viaja entre Community y Enterprise,
        cada instalación tiene sus propios ids). sudo() porque esto corre tanto al recibir un
        registro sincronizado (usuario de integración, sin permiso de escritura en este
        catálogo) como al elegir un tipo nuevo desde el formulario."""
        if not name:
            return self.browse()
        record = self.sudo().search([('name', '=', name)], limit=1)
        return record or self.sudo().create({'name': name})
