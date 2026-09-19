from odoo import fields, models


class AccountAnalyticAccount(models.Model):
    _inherit = 'account.analytic.account'

    enterprise_analytic_ref = fields.Char(
        string='Referencia de Cuenta Analítica en Enterprise', readonly=True, copy=False,
        index=True,
        help='Id de la cuenta analítica en la instalación Enterprise de origen. Uso técnico '
             'interno para no duplicar el registro en cada sincronización - las cuentas '
             'analíticas de esta instalación siempre se crean en Enterprise, nunca aquí.')
    disponible_tickets = fields.Boolean(
        string='Disponible para Tickets', default=False,
        help='Si está marcado, esta Cuenta Analítica aparece como opción de "Ubicación" al '
             'crear un Ticket en Community (construtec_helpdesk_field_service) - un filtro '
             'para que el operador solo vea las cuentas que de verdad representan una '
             'ubicación de servicio, no cualquier cuenta analítica del catálogo (proyectos '
             'internos, cuentas de otro uso, etc.). Viaja hacia Community igual que el resto '
             'de esta sincronización (ver _sync_analytic_accounts_from_enterprise() en '
             'res_company.py) - se edita aquí, nunca en Community.')
