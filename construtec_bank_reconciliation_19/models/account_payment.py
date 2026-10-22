from odoo import api, fields, models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    # El "Pagado" nativo de Odoo se marca al confirmar cuando el método registra directo a la
    # cuenta de banco; este estado dice si el BANCO ya lo aplicó (empate con el estado de cuenta).
    construtec_bank_state = fields.Selection([
        ('na', 'No aplica'),
        ('circulation', 'En circulación'),
        ('paid', 'Pagado en banco'),
    ], string='Estado bancario', compute='_compute_construtec_bank_state', store=True)
    construtec_bank_date = fields.Date(
        string='Fecha de cobro en banco', compute='_compute_construtec_bank_state', store=True)

    @api.depends('state', 'move_id.line_ids.account_id', 'move_id.line_ids.construtec_bank_line_ids',
                 'move_id.line_ids.construtec_bank_line_ids.date', 'journal_id.default_account_id',
                 'journal_id.bank_rec_start_date', 'journal_id.bank_rec_opening_line_ids')
    def _compute_construtec_bank_state(self):
        for pay in self:
            journal = pay.journal_id
            bank_lines = pay.move_id.line_ids.filtered(
                lambda l: l.account_id == journal.default_account_id)
            before_start = journal.bank_rec_start_date and bank_lines and all(
                l.date < journal.bank_rec_start_date and l not in journal.bank_rec_opening_line_ids
                for l in bank_lines)
            if pay.state in ('draft', 'canceled', 'rejected') or not bank_lines \
                    or journal.type != 'bank' or not journal.bank_rec_start_date or before_start:
                # Sin apunte en la cuenta de banco (p. ej. cuenta puente), diario sin conciliación
                # configurada o pago anterior al arranque: no se controla.
                pay.construtec_bank_state = 'na'
                pay.construtec_bank_date = False
                continue
            statement_lines = bank_lines.construtec_bank_line_ids
            if statement_lines:
                pay.construtec_bank_state = 'paid'
                pay.construtec_bank_date = max(statement_lines.mapped('date'))
            else:
                pay.construtec_bank_state = 'circulation'
                pay.construtec_bank_date = False
