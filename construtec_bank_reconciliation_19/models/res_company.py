from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    # Odoo no trae cuentas nativas para intereses (solo el modelo "Bank Fees" para comisiones),
    # así que el módulo guarda las tres por empresa (decisión 2026-10-22, ver CLAUDE.md).
    bank_rec_commission_account_id = fields.Many2one(
        'account.account', string='Cuenta de comisiones bancarias',
        domain="[('account_type', 'in', ('expense', 'expense_other'))]",
        check_company=True)
    bank_rec_interest_income_account_id = fields.Many2one(
        'account.account', string='Cuenta de intereses ganados',
        domain="[('account_type', 'in', ('income', 'income_other'))]",
        check_company=True)
    bank_rec_interest_expense_account_id = fields.Many2one(
        'account.account', string='Cuenta de intereses debitados',
        domain="[('account_type', 'in', ('expense', 'expense_other'))]",
        check_company=True)
    bank_rec_match_days = fields.Integer(
        string='Días de tolerancia para empate automático', default=15,
        help='Diferencia máxima en días entre la fecha del banco y la fecha del registro en Odoo '
             'para empatar por monto cuando no hay número de cheque ni referencia.')
    bank_rec_alert_months = fields.Integer(
        string='Meses para alertar partidas en circulación', default=5,
        help='Mismo plazo que usaba el reporte de Odoo 16, pero aquí solo alerta: '
             'la partida sigue apareciendo en la conciliación.')
