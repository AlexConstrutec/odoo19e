from odoo import fields, models


class ResPartnerBank(models.Model):
    _inherit = 'res.partner.bank'

    tipo_cuenta = fields.Selection(
        [('monetaria', 'Monetaria'), ('ahorro', 'Ahorro')], string='Tipo de Cuenta',
        help='Captúralo aquí, en la cuenta bancaria real del empleado (Enterprise) - '
             '`fetch_employees()` lo trae junto con el número de cuenta/banco hacia '
             '`hr.employee.tipo_cuenta_raw` (ver hr_employee.py), y de ahí se autocompleta '
             'en cada Solicitud de Viáticos/Materiales (`account.payment.order.tipo_cuenta`), '
             'sin que el jefe de técnicos/solicitante tenga que escribirlo cada vez.')
