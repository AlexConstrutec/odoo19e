from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    # Relación escrita solo desde construtec.bank.statement.line.move_line_ids: así nunca se
    # escribe sobre apuntes publicados, solo se agrega/quita una fila en la tabla de relación.
    construtec_bank_line_ids = fields.Many2many(
        'construtec.bank.statement.line', 'construtec_bank_line_aml_rel',
        'move_line_id', 'statement_line_id',
        string='Líneas del estado de cuenta', copy=False, readonly=True)
    construtec_bank_matched = fields.Boolean(
        string='Empatado con el banco', compute='_compute_construtec_bank_matched',
        search='_search_construtec_bank_matched')

    def _compute_construtec_bank_matched(self):
        for line in self:
            line.construtec_bank_matched = bool(line.construtec_bank_line_ids)

    def _search_construtec_bank_matched(self, operator, value):
        if operator not in ('=', '!=') or not isinstance(value, bool):
            return NotImplemented
        positive = (operator == '=') == value
        return [('construtec_bank_line_ids', '!=' if positive else '=', False)]
