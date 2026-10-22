from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    bank_rec_start_date = fields.Date(
        string='Inicio de conciliación Construtec',
        help='Los movimientos de la cuenta de banco anteriores a esta fecha se consideran ya '
             'conciliados, salvo los marcados abajo como partidas en circulación al arranque.')
    bank_rec_opening_line_ids = fields.Many2many(
        'account.move.line', 'construtec_bank_journal_opening_aml_rel', 'journal_id', 'move_line_id',
        string='Partidas en circulación al arranque',
        help='Cheques, pagos o depósitos registrados antes de la fecha de inicio que el banco '
             'todavía no había aplicado a esa fecha.')
    bank_rec_count = fields.Integer(compute='_compute_bank_rec_count')

    def _compute_bank_rec_count(self):
        data = self.env['construtec.bank.reconciliation']._read_group(
            [('journal_id', 'in', self.ids)], ['journal_id'], ['__count'])
        counts = {journal.id: count for journal, count in data}
        for journal in self:
            journal.bank_rec_count = counts.get(journal.id, 0)

    @api.constrains('bank_rec_opening_line_ids', 'bank_rec_start_date')
    def _check_bank_rec_opening_lines(self):
        for journal in self:
            wrong = journal.bank_rec_opening_line_ids.filtered(
                lambda l: l.account_id != journal.default_account_id
                or (journal.bank_rec_start_date and l.date >= journal.bank_rec_start_date))
            if wrong:
                raise ValidationError(
                    'Las partidas en circulación al arranque deben ser de la cuenta de banco del '
                    'diario y anteriores a la fecha de inicio de conciliación.')

    def _bank_rec_move_line_domain(self, date_to=None):
        """Movimientos contables de la cuenta de banco que participan en la conciliación."""
        self.ensure_one()
        domain = [
            ('account_id', '=', self.default_account_id.id),
            ('parent_state', '=', 'posted'),
            ('company_id', '=', self.company_id.id),
        ]
        if date_to:
            domain.append(('date', '<=', date_to))
        if self.bank_rec_start_date:
            domain += ['|', ('date', '>=', self.bank_rec_start_date),
                       ('id', 'in', self.bank_rec_opening_line_ids.ids)]
        return domain

    def action_open_bank_reconciliations(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id(
            'construtec_bank_reconciliation_19.action_construtec_bank_reconciliation')
        action['domain'] = [('journal_id', '=', self.id)]
        action['context'] = {'default_journal_id': self.id}
        return action
