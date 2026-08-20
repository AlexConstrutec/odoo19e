from odoo import fields, models


class AccountPaymentOrderEnterpriseAccount(models.Model):
    _name = 'account.payment.order.enterprise.account'
    _description = 'Cuenta Contable de la instalación Procesadora (Enterprise)'
    _order = 'code, name'

    name = fields.Char(required=True, readonly=True)
    code = fields.Char(readonly=True)
    enterprise_account_ref = fields.Char(
        string='Referencia en Enterprise', readonly=True, copy=False, index=True,
        help='Id real de esta cuenta contable en la instalación Procesadora - se reenvía tal '
             'cual (nunca por nombre) si esta cuenta llegara a viajar de vuelta hacia Enterprise, '
             'para resolverla contra la cuenta real. En una instalación Procesadora, este mismo '
             'campo guarda el id de la cuenta tal como existe en ESTA base (se refleja local, '
             'sin RPC - ver res_company.py:_sync_enterprise_accounts()), así que el campo '
             'funciona con el mismo criterio en ambos lados.')
