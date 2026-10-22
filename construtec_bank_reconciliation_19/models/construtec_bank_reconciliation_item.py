from odoo import fields, models


class ConstrutecBankReconciliationItem(models.Model):
    """Partida pendiente de una conciliación (foto que se congela al cerrar el mes)."""
    _name = 'construtec.bank.reconciliation.item'
    _description = 'Partida pendiente de conciliación bancaria'
    _order = 'item_type, date, id'

    reconciliation_id = fields.Many2one(
        'construtec.bank.reconciliation', required=True, ondelete='cascade', index=True)
    currency_id = fields.Many2one(related='reconciliation_id.currency_id')
    item_type = fields.Selection([
        ('outstanding_payment', 'Cheques y pagos en circulación'),
        ('outstanding_deposit', 'Depósitos en tránsito'),
        ('bank_debit', 'Débitos del banco no registrados'),
        ('bank_credit', 'Créditos del banco no registrados'),
    ], string='Tipo', required=True)
    date = fields.Date(string='Fecha')
    reference = fields.Char(string='Documento / No. cheque')
    partner_name = fields.Char(string='A nombre de')
    name = fields.Char(string='Descripción')
    amount = fields.Monetary(string='Cantidad', currency_field='currency_id',
                             help='Siempre positivo; el tipo indica si suma o resta.')
    age_days = fields.Integer(string='Días')
    alert = fields.Boolean(string='Alerta de antigüedad')
    move_line_id = fields.Many2one('account.move.line', string='Registro en Odoo')
    payment_id = fields.Many2one('account.payment', string='Pago')
    statement_line_id = fields.Many2one('construtec.bank.statement.line',
                                        string='Línea del estado de cuenta')
