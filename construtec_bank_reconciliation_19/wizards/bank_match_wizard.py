from odoo import api, fields, models
from odoo.exceptions import UserError


class ConstrutecBankMatchWizard(models.TransientModel):
    _name = 'construtec.bank.match.wizard'
    _description = 'Empate manual de estado de cuenta (Construtec)'

    reconciliation_id = fields.Many2one('construtec.bank.reconciliation', string='Conciliación', required=True,
                                        readonly=True)
    currency_id = fields.Many2one(related='reconciliation_id.currency_id')
    statement_line_ids = fields.Many2many(
        'construtec.bank.statement.line', string='Líneas del banco',
        domain="[('reconciliation_id', '=', reconciliation_id), ('match_state', '=', 'unmatched')]")
    candidate_move_line_ids = fields.Many2many(
        'account.move.line', compute='_compute_candidate_move_line_ids')
    move_line_ids = fields.Many2many(
        'account.move.line', string='Registros en Odoo',
        domain="[('id', 'in', candidate_move_line_ids)]")
    bank_total = fields.Monetary(compute='_compute_totals', currency_field='currency_id',
                                 string='Total banco')
    odoo_total = fields.Monetary(compute='_compute_totals', currency_field='currency_id',
                                 string='Total Odoo')
    difference = fields.Monetary(compute='_compute_totals', currency_field='currency_id',
                                 string='Diferencia')

    @api.depends('reconciliation_id')
    def _compute_candidate_move_line_ids(self):
        for wizard in self:
            journal = wizard.reconciliation_id.journal_id
            if not journal:
                wizard.candidate_move_line_ids = False
                continue
            wizard.candidate_move_line_ids = self.env['account.move.line'].search(
                journal._bank_rec_move_line_domain() + [('construtec_bank_line_ids', '=', False)])

    @api.depends('statement_line_ids', 'move_line_ids')
    def _compute_totals(self):
        for wizard in self:
            field = wizard.reconciliation_id._amount_field() if wizard.reconciliation_id else 'balance'
            wizard.bank_total = sum(wizard.statement_line_ids.mapped('amount'))
            wizard.odoo_total = sum(wizard.move_line_ids.mapped(field))
            wizard.difference = wizard.bank_total - wizard.odoo_total

    def action_confirm(self):
        self.ensure_one()
        if not self.statement_line_ids or not self.move_line_ids:
            raise UserError('Seleccione al menos una línea del banco y un registro de Odoo.')
        self.statement_line_ids._match_with(self.move_line_ids, 'manual')
        self.reconciliation_id.action_refresh()
        return {'type': 'ir.actions.act_window_close'}
