from odoo import fields, models


class AccountPaymentOrderEnterpriseJournal(models.Model):
    _name = 'account.payment.order.enterprise.journal'
    _description = 'Diario Contable de la instalación Procesadora (Enterprise)'
    _order = 'code, name'

    name = fields.Char(required=True, readonly=True)
    code = fields.Char(readonly=True)
    enterprise_journal_ref = fields.Char(
        string='Referencia en Enterprise', readonly=True, copy=False, index=True,
        help='Mismo criterio que account.payment.order.enterprise.account.enterprise_account_ref '
             '- ver ese modelo.')
