import re

from odoo import api, fields, models
from odoo.exceptions import UserError


class ConstrutecBankStatementLine(models.Model):
    """Movimiento del estado de cuenta del banco.

    A diferencia de account.bank.statement.line de Odoo, NO genera asiento contable: solo se
    empata (vínculo de control) contra los apuntes que ya existen en la cuenta de banco.
    """
    _name = 'construtec.bank.statement.line'
    _description = 'Movimiento del estado de cuenta (Construtec)'
    _order = 'date, sequence, id'

    reconciliation_id = fields.Many2one(
        'construtec.bank.reconciliation', string='Conciliación', required=True,
        ondelete='cascade', index=True)
    journal_id = fields.Many2one(related='reconciliation_id.journal_id', store=True, index=True)
    company_id = fields.Many2one(related='reconciliation_id.company_id', store=True, index=True)
    currency_id = fields.Many2one(related='reconciliation_id.currency_id')
    sequence = fields.Integer(default=10)
    date = fields.Date(string='Fecha', required=True)
    ref = fields.Char(string='Documento / No. cheque')
    name = fields.Char(string='Descripción')
    debit = fields.Monetary(string='Débito (retiro)', currency_field='currency_id')
    credit = fields.Monetary(string='Crédito (depósito)', currency_field='currency_id')
    amount = fields.Monetary(
        string='Monto', compute='_compute_amount', store=True, currency_field='currency_id',
        help='Positivo = entra dinero al banco; negativo = sale.')
    bank_balance = fields.Monetary(string='Saldo según banco', currency_field='currency_id')

    move_line_ids = fields.Many2many(
        'account.move.line', 'construtec_bank_line_aml_rel', 'statement_line_id', 'move_line_id',
        string='Registros en Odoo', copy=False,
        domain="[('account_id', '=', account_id), ('parent_state', '=', 'posted')]")
    account_id = fields.Many2one(related='reconciliation_id.account_id')
    match_state = fields.Selection([
        ('unmatched', 'Sin empatar'),
        ('matched', 'Empatado'),
        ('adjustment', 'Ajuste registrado'),
    ], string='Estado', compute='_compute_match_state', store=True)
    match_method = fields.Selection([
        ('check', 'Automático: No. de cheque'),
        ('ref', 'Automático: referencia'),
        ('amount', 'Automático: monto y fecha'),
        ('manual', 'Manual'),
        ('adjustment', 'Ajuste'),
    ], string='Forma de empate', copy=False)
    adjustment_move_id = fields.Many2one('account.move', string='Asiento de ajuste', copy=False,
                                         readonly=True)
    adjustment_type = fields.Selection([
        ('commission', 'Comisión bancaria'),
        ('interest_income', 'Interés ganado'),
        ('interest_expense', 'Interés debitado'),
        ('other', 'Otra nota del banco'),
    ], string='Tipo de ajuste', copy=False, readonly=True)
    matched_amount = fields.Monetary(
        string='Monto empatado', compute='_compute_match_state', store=True,
        currency_field='currency_id')
    partner_names = fields.Char(string='Contacto(s)', compute='_compute_partner_names')

    @api.depends('debit', 'credit')
    def _compute_amount(self):
        for line in self:
            line.amount = (line.credit or 0.0) - (line.debit or 0.0)

    @api.depends('move_line_ids', 'move_line_ids.balance', 'move_line_ids.amount_currency',
                 'adjustment_move_id')
    def _compute_match_state(self):
        for line in self:
            line.matched_amount = sum(line.move_line_ids.mapped(line._aml_amount_field()))
            if not line.move_line_ids:
                line.match_state = 'unmatched'
            elif line.adjustment_move_id:
                line.match_state = 'adjustment'
            else:
                line.match_state = 'matched'

    def _compute_partner_names(self):
        for line in self:
            line.partner_names = ', '.join(sorted(set(line.move_line_ids.partner_id.mapped('name'))))

    def _aml_amount_field(self):
        """Monto del apunte expresado en la moneda del diario."""
        journal = self.reconciliation_id.journal_id
        if journal.currency_id and journal.currency_id != journal.company_id.currency_id:
            return 'amount_currency'
        return 'balance'

    # ------------------------------------------------------------------
    # Protección: un mes cerrado no se toca
    # ------------------------------------------------------------------
    def _check_reconciliation_draft(self):
        if self.reconciliation_id.filtered(lambda r: r.state != 'draft'):
            raise UserError('La conciliación ya está cerrada. Para cambiar sus movimientos, '
                            'primero hay que reabrirla.')

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._check_reconciliation_draft()
        return lines

    def write(self, vals):
        self._check_reconciliation_draft()
        return super().write(vals)

    def unlink(self):
        self._check_reconciliation_draft()
        if self.adjustment_move_id:
            raise UserError('Primero deshaga el ajuste de las líneas que tienen asiento de ajuste.')
        return super().unlink()

    # ------------------------------------------------------------------
    # Empate
    # ------------------------------------------------------------------
    def _match_with(self, move_lines, method):
        """Vincula esta(s) línea(s) del banco con apuntes de la cuenta de banco."""
        if not self or not move_lines:
            return
        rec = self.reconciliation_id
        rec.ensure_one()
        if move_lines.construtec_bank_line_ids - self:
            raise UserError('Alguno de los registros seleccionados ya está empatado con otra '
                            'línea del estado de cuenta.')
        wrong_account = move_lines.filtered(lambda l: l.account_id != rec.account_id)
        if wrong_account:
            raise UserError('Solo se pueden empatar registros de la cuenta de banco %s.'
                            % rec.account_id.display_name)
        field = self._aml_amount_field()
        total_bank = sum(self.mapped('amount'))
        total_odoo = sum(move_lines.mapped(field))
        if rec.currency_id.compare_amounts(total_bank, total_odoo) != 0:
            raise UserError(
                'Los montos no cuadran: el banco suma %s y los registros de Odoo suman %s.'
                % (rec.currency_id.format(total_bank), rec.currency_id.format(total_odoo)))
        self.write({'move_line_ids': [(6, 0, move_lines.ids)], 'match_method': method})

    def action_unmatch(self):
        self._check_reconciliation_draft()
        for line in self:
            move = line.adjustment_move_id
            line.write({'move_line_ids': [(5, 0, 0)], 'match_method': False,
                        'adjustment_move_id': False, 'adjustment_type': False})
            if move:
                move.button_draft()
                move.with_context(force_delete=True).unlink()
        self.reconciliation_id.action_refresh()

    def action_open_match_wizard(self):
        self._check_reconciliation_draft()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Empatar con registros de Odoo',
            'res_model': 'construtec.bank.match.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_reconciliation_id': self.reconciliation_id[:1].id,
                'default_statement_line_ids': self.ids,
            },
        }

    def action_open_adjustment_wizard(self):
        self.ensure_one()
        self._check_reconciliation_draft()
        if self.move_line_ids:
            raise UserError('La línea ya está empatada.')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Registrar ajuste',
            'res_model': 'construtec.bank.adjustment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_statement_line_id': self.id},
        }

    @staticmethod
    def _normalize_number(value):
        digits = re.sub(r'\D', '', value or '')
        return digits.lstrip('0')

    def _auto_match(self):
        """Empate automático. Reglas, en orden:

        1. No. de cheque del pago = documento del banco (sin ceros a la izquierda) y mismo monto.
        2. La referencia del banco aparece en el pago/asiento y mismo monto.
        3. Monto único dentro de +/- N días (configurable por empresa).
        Una línea solo se empata si la regla encuentra exactamente un candidato.
        """
        matched = self.browse()
        for line in self.filtered(lambda l: not l.move_line_ids):
            rec = line.reconciliation_id
            journal = rec.journal_id
            field = line._aml_amount_field()
            days = rec.company_id.bank_rec_match_days or 0
            domain = journal._bank_rec_move_line_domain() + [
                ('construtec_bank_line_ids', '=', False),
                (field, '=', line.amount),
            ]
            candidates = self.env['account.move.line'].search(domain)
            candidates = candidates.filtered(
                lambda l: rec.currency_id.compare_amounts(l[field], line.amount) == 0)
            if not candidates:
                continue
            chosen, method = self.env['account.move.line'], False
            number = self._normalize_number(line.ref)
            if number:
                by_check = candidates.filtered(
                    lambda l: l.payment_id.check_number
                    and self._normalize_number(l.payment_id.check_number) == number)
                if len(by_check) == 1:
                    chosen, method = by_check, 'check'
            if not chosen and line.ref and len(line.ref.strip()) >= 4:
                ref = line.ref.strip().lower()
                by_ref = candidates.filtered(lambda l: any(
                    ref in (txt or '').lower() for txt in (
                        l.name, l.ref, l.move_id.name, l.move_id.ref,
                        l.payment_id.memo, l.payment_id.payment_reference)))
                if len(by_ref) == 1:
                    chosen, method = by_ref, 'ref'
            if not chosen:
                near = candidates.filtered(lambda l: abs((l.date - line.date).days) <= days)
                if len(near) == 1:
                    chosen, method = near, 'amount'
            if chosen:
                line._match_with(chosen, method)
                matched |= line
        return matched
