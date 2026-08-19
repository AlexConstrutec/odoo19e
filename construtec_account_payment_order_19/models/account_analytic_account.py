from odoo import fields, models


class AccountAnalyticAccount(models.Model):
    _inherit = 'account.analytic.account'

    enterprise_analytic_ref = fields.Char(
        string='Referencia de Cuenta Analítica en Enterprise', readonly=True, copy=False,
        index=True,
        help='Id de la cuenta analítica en la instalación Enterprise de origen. Uso técnico '
             'interno para no duplicar el registro en cada sincronización - las cuentas '
             'analíticas de esta instalación siempre se crean en Enterprise, nunca aquí.')
