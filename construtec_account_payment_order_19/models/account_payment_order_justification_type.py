from odoo import api, fields, models


class AccountPaymentOrderJustificationType(models.Model):
    _name = 'account.payment.order.justification.type'
    _description = 'Tipo de Gasto de Solicitud de Pago'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    cuenta_contable_id = fields.Many2one(
        'account.payment.order.enterprise.account', string='Cuenta Contable de Gastos',
        help='Cuenta de gastos asociada a este Tipo de Gasto, para reducir digitación al '
             'contabilizar - por ahora solo se guarda aquí como configuración (no hay todavía '
             'ningún flujo automático de este módulo que la use; se digita a mano en cada '
             'factura de proveedor al momento de la Liquidación, como siempre). Apunta al '
             'catálogo espejo `account.payment.order.enterprise.account` (no a account.account '
             'directo) para que el mismo campo funcione igual en Community y en Enterprise: en '
             'Community ese espejo se llena por RPC desde la Compañía por Defecto ya elegida; '
             'en Enterprise se refleja local de las cuentas reales de esa misma base - ver '
             'res_company.py:_sync_enterprise_accounts().')

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
