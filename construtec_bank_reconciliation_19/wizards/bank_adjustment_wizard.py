from odoo import api, fields, models
from odoo.exceptions import UserError


class ConstrutecBankAdjustmentWizard(models.TransientModel):
    """Registra en libros una nota del banco (comisión, interés) y la deja empatada."""
    _name = 'construtec.bank.adjustment.wizard'
    _description = 'Ajuste por nota del banco (Construtec)'

    statement_line_id = fields.Many2one('construtec.bank.statement.line', required=True,
                                        readonly=True)
    company_id = fields.Many2one(related='statement_line_id.company_id')
    currency_id = fields.Many2one(related='statement_line_id.currency_id')
    amount = fields.Monetary(related='statement_line_id.amount', currency_field='currency_id')
    date = fields.Date(related='statement_line_id.date')
    adjustment_type = fields.Selection([
        ('commission', 'Comisión bancaria'),
        ('interest_income', 'Interés ganado'),
        ('interest_expense', 'Interés debitado'),
        ('other', 'Otra nota del banco'),
    ], string='Tipo', required=True, default='commission')
    account_id = fields.Many2one(
        'account.account', string='Cuenta contrapartida', required=True,
        compute='_compute_account_id', store=True, readonly=False, precompute=True,
        check_company=True)
    label = fields.Char(string='Descripción', compute='_compute_label', store=True, readonly=False,
                        precompute=True)

    @api.depends('adjustment_type', 'statement_line_id')
    def _compute_account_id(self):
        for wizard in self:
            company = wizard.statement_line_id.company_id
            wizard.account_id = {
                'commission': company.bank_rec_commission_account_id,
                'interest_income': company.bank_rec_interest_income_account_id,
                'interest_expense': company.bank_rec_interest_expense_account_id,
            }.get(wizard.adjustment_type) or wizard.account_id

    @api.depends('adjustment_type', 'statement_line_id')
    def _compute_label(self):
        labels = dict(self._fields['adjustment_type'].selection)
        for wizard in self:
            line = wizard.statement_line_id
            wizard.label = ' - '.join(filter(None, [labels.get(wizard.adjustment_type),
                                                    line.name or line.ref]))

    def action_confirm(self):
        self.ensure_one()
        line = self.statement_line_id
        line._check_reconciliation_draft()
        if line.move_line_ids:
            raise UserError('La línea ya está empatada.')
        rec = line.reconciliation_id
        journal = rec.journal_id
        amount = line.amount
        if rec.currency_id.is_zero(amount):
            raise UserError('La línea no tiene monto.')
        foreign = rec.currency_id != rec.company_id.currency_id
        amount_company = rec.currency_id._convert(amount, rec.company_id.currency_id,
                                                  rec.company_id, line.date) if foreign else amount

        def line_vals(account, balance, amount_currency):
            vals = {
                'name': self.label,
                'account_id': account.id,
                'debit': balance if balance > 0 else 0.0,
                'credit': -balance if balance < 0 else 0.0,
            }
            if foreign:
                vals.update({'currency_id': rec.currency_id.id, 'amount_currency': amount_currency})
            return vals

        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': line.date,
            'ref': 'Conciliación %s - %s' % (rec.name, line.ref or line.name or ''),
            'line_ids': [
                (0, 0, line_vals(journal.default_account_id, amount_company, amount)),
                (0, 0, line_vals(self.account_id, -amount_company, -amount)),
            ],
        })
        move.action_post()
        bank_aml = move.line_ids.filtered(lambda l: l.account_id == journal.default_account_id)
        line._match_with(bank_aml, 'adjustment')
        line.write({'adjustment_move_id': move.id, 'adjustment_type': self.adjustment_type})
        rec.action_refresh()
        rec.message_post(body='Ajuste %s registrado: %s por %s.' % (
            move.name, self.label, rec.currency_id.format(amount)))
        return {'type': 'ir.actions.act_window_close'}
