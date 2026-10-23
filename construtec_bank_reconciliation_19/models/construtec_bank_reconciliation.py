from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

MESES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto',
         'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']


def _default_date_from(records=None):
    return date.today().replace(day=1) - relativedelta(months=1)


def _default_date_to(records=None):
    return date.today().replace(day=1) - relativedelta(days=1)


class ConstrutecBankReconciliation(models.Model):
    """Conciliación bancaria mensual de un diario de banco (formato Diamante).

    Saldo en libros = saldo según banco - cheques/pagos en circulación + depósitos en tránsito
                      + débitos del banco no registrados - créditos del banco no registrados
    Los totales y las partidas pendientes se recalculan mientras está en Borrador y quedan
    congelados al marcarla Hecha, para que cambios posteriores no alteren un mes cerrado.
    """
    _name = 'construtec.bank.reconciliation'
    _description = 'Conciliación bancaria (Construtec)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_to desc, journal_id'
    _check_company_auto = True

    name = fields.Char(string='Nombre', compute='_compute_name', store=True)
    company_id = fields.Many2one('res.company', string='Empresa', required=True,
                                 default=lambda self: self.env.company, readonly=True)
    journal_id = fields.Many2one(
        'account.journal', string='Diario de banco', required=True, tracking=True,
        check_company=True, domain="[('type', '=', 'bank')]")
    account_id = fields.Many2one(related='journal_id.default_account_id', string='Cuenta contable')
    currency_id = fields.Many2one('res.currency', compute='_compute_currency_id')
    date_from = fields.Date(string='Desde', required=True, default=_default_date_from, tracking=True)
    date_to = fields.Date(string='Hasta', required=True, default=_default_date_to, tracking=True)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('done', 'Hecho'),
        ('reviewed', 'Revisado'),
        ('approved', 'Autorizado'),
    ], string='Estado', default='draft', required=True, tracking=True, copy=False)

    previous_id = fields.Many2one('construtec.bank.reconciliation', string='Conciliación anterior',
                                  compute='_compute_previous_id')
    balance_start = fields.Monetary(
        string='Saldo inicial según banco', compute='_compute_balance_start', store=True,
        readonly=False, tracking=True, currency_field='currency_id',
        help='Por defecto, el saldo final de la conciliación anterior del mismo diario.')
    balance_end_real = fields.Monetary(
        string='Saldo final según estado de cuenta', tracking=True, currency_field='currency_id')
    balance_end_note = fields.Char(
        string='Justificación de saldo manual',
        help='Obligatoria si el saldo final no cuadra con saldo inicial + movimientos importados.')
    statement_line_ids = fields.One2many('construtec.bank.statement.line', 'reconciliation_id',
                                         string='Movimientos del estado de cuenta')
    balance_end_computed = fields.Monetary(
        string='Saldo inicial + movimientos', compute='_compute_statement_totals',
        currency_field='currency_id')
    statement_difference = fields.Monetary(
        string='Diferencia en el estado de cuenta', compute='_compute_statement_totals',
        currency_field='currency_id')
    unmatched_count = fields.Integer(string='Líneas sin empatar', compute='_compute_statement_totals')
    statement_attachment = fields.Binary(string='Estado de cuenta (PDF)', attachment=True, copy=False)
    statement_attachment_name = fields.Char(copy=False)

    # Totales (se recalculan con "Recalcular" mientras está en Borrador; congelados después)
    book_balance = fields.Monetary(string='Saldo según libros', readonly=True, copy=False,
                                   currency_field='currency_id')
    outstanding_payments = fields.Monetary(string='Cheques y pagos en circulación', readonly=True,
                                           copy=False, currency_field='currency_id')
    outstanding_deposits = fields.Monetary(string='Depósitos en tránsito', readonly=True,
                                           copy=False, currency_field='currency_id')
    unrecorded_debits = fields.Monetary(string='Débitos del banco no registrados', readonly=True,
                                        copy=False, currency_field='currency_id')
    unrecorded_credits = fields.Monetary(string='Créditos del banco no registrados', readonly=True,
                                         copy=False, currency_field='currency_id')
    conciliated_balance = fields.Monetary(string='Saldo conciliado', readonly=True, copy=False,
                                          currency_field='currency_id')
    difference = fields.Monetary(string='Diferencia', readonly=True, copy=False,
                                 currency_field='currency_id')
    last_refresh = fields.Datetime(string='Última actualización', readonly=True, copy=False)
    item_ids = fields.One2many('construtec.bank.reconciliation.item', 'reconciliation_id',
                               string='Partidas pendientes', readonly=True, copy=False)
    outstanding_payment_item_ids = fields.One2many(
        'construtec.bank.reconciliation.item', 'reconciliation_id',
        domain=[('item_type', '=', 'outstanding_payment')], readonly=True)
    outstanding_deposit_item_ids = fields.One2many(
        'construtec.bank.reconciliation.item', 'reconciliation_id',
        domain=[('item_type', '=', 'outstanding_deposit')], readonly=True)
    unrecorded_item_ids = fields.One2many(
        'construtec.bank.reconciliation.item', 'reconciliation_id',
        domain=[('item_type', 'in', ('bank_debit', 'bank_credit'))], readonly=True)
    alert_count = fields.Integer(string='Partidas con alerta', compute='_compute_alert_count')

    done_user_id = fields.Many2one('res.users', string='Hecho por', readonly=True, copy=False)
    done_date = fields.Datetime(string='Fecha hecho', readonly=True, copy=False)
    reviewed_user_id = fields.Many2one('res.users', string='Revisado por', readonly=True, copy=False)
    reviewed_date = fields.Datetime(string='Fecha revisado', readonly=True, copy=False)
    approved_user_id = fields.Many2one('res.users', string='Autorizado por', readonly=True, copy=False)
    approved_date = fields.Datetime(string='Fecha autorizado', readonly=True, copy=False)

    _journal_period_uniq = models.Constraint(
        'unique(journal_id, date_from)',
        'Ya existe una conciliación de este diario para ese periodo.',
    )

    @api.depends('journal_id', 'date_to')
    def _compute_name(self):
        for rec in self:
            if rec.journal_id and rec.date_to:
                rec.name = '%s - %s %s' % (rec.journal_id.name, MESES[rec.date_to.month - 1],
                                           rec.date_to.year)
            else:
                rec.name = 'Nueva conciliación'

    @api.depends('journal_id')
    def _compute_currency_id(self):
        for rec in self:
            rec.currency_id = rec.journal_id.currency_id or rec.company_id.currency_id

    @api.depends('journal_id', 'date_from')
    def _compute_previous_id(self):
        for rec in self:
            rec.previous_id = rec._find_previous()

    def _find_previous(self):
        self.ensure_one()
        if not self.journal_id or not self.date_from:
            return self.browse()
        return self.search([
            ('journal_id', '=', self.journal_id.id),
            ('date_to', '<', self.date_from),
            ('id', '!=', self._origin.id or 0),
        ], order='date_to desc', limit=1)

    @api.depends('journal_id', 'date_from')
    def _compute_balance_start(self):
        for rec in self:
            previous = rec._find_previous() if rec.state == 'draft' else False
            rec.balance_start = previous.balance_end_real if previous else rec.balance_start

    @api.depends('balance_start', 'balance_end_real', 'statement_line_ids.amount',
                 'statement_line_ids.match_state')
    def _compute_statement_totals(self):
        for rec in self:
            rec.balance_end_computed = rec.balance_start + sum(rec.statement_line_ids.mapped('amount'))
            rec.statement_difference = rec.balance_end_real - rec.balance_end_computed
            rec.unmatched_count = len(rec.statement_line_ids.filtered(
                lambda l: l.match_state == 'unmatched'))

    @api.depends('item_ids.alert')
    def _compute_alert_count(self):
        for rec in self:
            rec.alert_count = len(rec.item_ids.filtered('alert'))

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from > rec.date_to:
                raise ValidationError('La fecha inicial no puede ser mayor que la final.')

    @api.constrains('journal_id')
    def _check_journal(self):
        for rec in self:
            if rec.journal_id.type != 'bank':
                raise ValidationError('Solo se concilian diarios de tipo Banco.')
            if not rec.journal_id.default_account_id:
                raise ValidationError('El diario %s no tiene cuenta bancaria configurada.'
                                      % rec.journal_id.name)

    def write(self, vals):
        protected = set(vals) & {'journal_id', 'date_from', 'date_to', 'balance_start',
                                 'balance_end_real', 'statement_line_ids'}
        if protected and self.filtered(lambda r: r.state != 'draft'):
            raise UserError('La conciliación ya está cerrada; reábrala para modificarla.')
        res = super().write(vals)
        if protected:
            self.action_refresh()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.action_refresh()
        return records

    def unlink(self):
        if self.filtered(lambda r: r.state != 'draft'):
            raise UserError('Solo se pueden eliminar conciliaciones en Borrador.')
        if self.statement_line_ids.adjustment_move_id:
            raise UserError('Deshaga primero los ajustes registrados desde esta conciliación.')
        return super().unlink()

    # ------------------------------------------------------------------
    # Cálculo
    # ------------------------------------------------------------------
    def _amount_field(self):
        self.ensure_one()
        if self.currency_id != self.company_id.currency_id:
            return 'amount_currency'
        return 'balance'

    def _compute_pending(self):
        """Devuelve (book_balance, items_vals) calculados a la fecha de corte."""
        self.ensure_one()
        journal = self.journal_id
        date_to = self.date_to
        field = self._amount_field()
        AML = self.env['account.move.line']

        all_lines = AML.search([
            ('account_id', '=', journal.default_account_id.id),
            ('parent_state', '=', 'posted'),
            ('company_id', '=', self.company_id.id),
            ('date', '<=', date_to),
        ])
        book_balance = sum(all_lines.mapped(field))

        alert_days = (self.company_id.bank_rec_alert_months or 0) * 30
        items = []
        candidates = AML.search(journal._bank_rec_move_line_domain(date_to))
        for aml in candidates:
            if any(s.date <= date_to for s in aml.construtec_bank_line_ids):
                continue
            amount = aml[field]
            if self.currency_id.is_zero(amount):
                continue
            age = (date_to - aml.date).days
            payment = aml.payment_id
            items.append({
                'item_type': 'outstanding_payment' if amount < 0 else 'outstanding_deposit',
                'date': aml.date,
                'reference': payment.check_number or payment.memo or aml.move_id.ref or aml.move_id.name,
                'partner_name': aml.partner_id.name or '',
                'name': aml.name or aml.move_id.ref or aml.move_id.name,
                'amount': abs(amount),
                'age_days': age,
                'alert': bool(alert_days) and age > alert_days,
                'move_line_id': aml.id,
                'payment_id': payment.id,
            })

        bank_lines = self.env['construtec.bank.statement.line'].search([
            ('journal_id', '=', journal.id),
            ('date', '<=', date_to),
        ])
        for line in bank_lines:
            if line.move_line_ids and all(a.date <= date_to for a in line.move_line_ids):
                continue
            if self.currency_id.is_zero(line.amount):
                continue
            items.append({
                'item_type': 'bank_credit' if line.amount > 0 else 'bank_debit',
                'date': line.date,
                'reference': line.ref,
                'name': line.name,
                'amount': abs(line.amount),
                'age_days': (date_to - line.date).days,
                'statement_line_id': line.id,
            })
        return book_balance, items

    def action_refresh(self):
        for rec in self.filtered(lambda r: r.state == 'draft'):
            book_balance, items = rec._compute_pending()
            totals = dict.fromkeys(
                ('outstanding_payment', 'outstanding_deposit', 'bank_debit', 'bank_credit'), 0.0)
            for item in items:
                totals[item['item_type']] += item['amount']
            conciliated = (rec.balance_end_real - totals['outstanding_payment']
                           + totals['outstanding_deposit'] + totals['bank_debit']
                           - totals['bank_credit'])
            rec.item_ids.unlink()
            # super().write: los totales se escriben aunque write() bloquee campos de un mes cerrado
            super(ConstrutecBankReconciliation, rec).write({
                'book_balance': book_balance,
                'outstanding_payments': totals['outstanding_payment'],
                'outstanding_deposits': totals['outstanding_deposit'],
                'unrecorded_debits': totals['bank_debit'],
                'unrecorded_credits': totals['bank_credit'],
                'conciliated_balance': conciliated,
                'difference': book_balance - conciliated,
                'last_refresh': fields.Datetime.now(),
                'item_ids': [(0, 0, vals) for vals in items],
            })
        return True

    def action_auto_match(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError('La conciliación ya está cerrada.')
        matched = self.statement_line_ids._auto_match()
        self.action_refresh()
        self.message_post(body='Empate automático: %s línea(s) empatadas, %s sin empatar.'
                               % (len(matched), self.unmatched_count))
        return True

    # ------------------------------------------------------------------
    # Estados y firmas
    # ------------------------------------------------------------------
    def action_done(self):
        for rec in self:
            if rec.state != 'draft':
                continue
            older_open = self.search([('journal_id', '=', rec.journal_id.id),
                                      ('date_to', '<', rec.date_from), ('state', '=', 'draft')],
                                     limit=1)
            if older_open:
                raise UserError('Primero cierre la conciliación anterior: %s.' % older_open.name)
            if not rec.statement_line_ids:
                raise UserError('Importe primero el estado de cuenta del mes.')
            if not rec.currency_id.is_zero(rec.statement_difference) and not rec.balance_end_note:
                raise UserError(
                    'El saldo final del estado de cuenta (%s) no cuadra con saldo inicial + '
                    'movimientos (%s). Revise que se importaron todas las líneas o escriba la '
                    'justificación.' % (rec.currency_id.format(rec.balance_end_real),
                                        rec.currency_id.format(rec.balance_end_computed)))
            rec.action_refresh()
            # Las notas del banco del mes (comisiones, intereses) se registran antes de cerrar,
            # aunque la fórmula ya las cuadre: el objetivo es que los libros reflejen al banco.
            notes = rec.unrecorded_item_ids.filtered(
                lambda i: i.date and rec.date_from <= i.date <= rec.date_to)
            if notes:
                raise UserError(
                    'Hay %s nota(s) del banco de este mes sin registrar en Odoo (comisiones, '
                    'intereses u otras). Empátelas o registre su ajuste antes de marcar Hecho.'
                    % len(notes))
            if not rec.currency_id.is_zero(rec.difference):
                raise UserError(
                    'La conciliación tiene una diferencia de %s. Empate o registre los ajustes '
                    'pendientes antes de marcarla como Hecha.' % rec.currency_id.format(rec.difference))
            rec.write({'state': 'done', 'done_user_id': self.env.uid,
                       'done_date': fields.Datetime.now()})
        return True

    def _check_manager(self):
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError('Solo un Administrador de Contabilidad puede revisar, autorizar o '
                            'reabrir conciliaciones.')

    def action_review(self):
        self._check_manager()
        for rec in self.filtered(lambda r: r.state == 'done'):
            rec.write({'state': 'reviewed', 'reviewed_user_id': self.env.uid,
                       'reviewed_date': fields.Datetime.now()})
        return True

    def action_approve(self):
        self._check_manager()
        for rec in self.filtered(lambda r: r.state == 'reviewed'):
            rec.write({'state': 'approved', 'approved_user_id': self.env.uid,
                       'approved_date': fields.Datetime.now()})
        return True

    def action_reopen(self):
        self._check_manager()
        for rec in self.filtered(lambda r: r.state != 'draft'):
            newer_closed = self.search([('journal_id', '=', rec.journal_id.id),
                                        ('date_from', '>', rec.date_to), ('state', '!=', 'draft')],
                                       limit=1)
            if newer_closed:
                raise UserError('Primero reabra la conciliación posterior: %s.' % newer_closed.name)
            rec.write({'state': 'draft', 'done_user_id': False, 'done_date': False,
                       'reviewed_user_id': False, 'reviewed_date': False,
                       'approved_user_id': False, 'approved_date': False})
            rec.message_post(body='Conciliación reabierta.')
        return True

    # ------------------------------------------------------------------
    # Botones
    # ------------------------------------------------------------------
    def action_open_import_wizard(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError('La conciliación ya está cerrada.')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Importar estado de cuenta',
            'res_model': 'construtec.bank.statement.import.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_reconciliation_id': self.id},
        }

    def action_open_match_wizard(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError('La conciliación ya está cerrada.')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Empatar manualmente',
            'res_model': 'construtec.bank.match.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_reconciliation_id': self.id},
        }

    def action_print(self):
        return self.env.ref(
            'construtec_bank_reconciliation_19.action_report_construtec_bank_reconciliation'
        ).report_action(self)

    def action_print_account_movement(self):
        return self.env.ref(
            'construtec_bank_reconciliation_19.action_report_construtec_bank_account_movement'
        ).report_action(self)

    # ------------------------------------------------------------------
    # Datos para el reporte "Movimiento de Cuenta"
    # ------------------------------------------------------------------
    def _get_account_movement(self):
        self.ensure_one()
        field = self._amount_field()
        AML = self.env['account.move.line']
        base = [('account_id', '=', self.account_id.id), ('parent_state', '=', 'posted'),
                ('company_id', '=', self.company_id.id)]
        opening = sum(AML.search(base + [('date', '<', self.date_from)]).mapped(field))
        lines = AML.search(base + [('date', '>=', self.date_from), ('date', '<=', self.date_to)],
                           order='date, move_name, id')
        rows, balance = [], opening
        for aml in lines:
            amount = aml[field]
            balance += amount
            rows.append({
                'date': aml.date,
                'move': aml.move_id.name,
                'name': ' / '.join(filter(None, [aml.partner_id.name,
                                                  aml.name or aml.move_id.ref])),
                'debit': amount if amount > 0 else 0.0,
                'credit': -amount if amount < 0 else 0.0,
                'balance': balance,
            })
        return {
            'opening': opening,
            'rows': rows,
            'total_debit': sum(r['debit'] for r in rows),
            'total_credit': sum(r['credit'] for r in rows),
            'closing': balance,
        }

    def _period_label(self):
        self.ensure_one()
        return 'Periodo del %s al %s' % (self.date_from.strftime('%d/%m/%Y'),
                                          self.date_to.strftime('%d/%m/%Y'))
