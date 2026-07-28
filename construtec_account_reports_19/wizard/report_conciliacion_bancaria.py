import calendar
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import fields, models

from .wizard_mixin import MESES

ROWS_PER_PAGE = 49


class WizardConciliacionBancaria(models.TransientModel):
    _name = 'wizard.conciliacion.bancaria'
    _description = 'Wizard Conciliación Bancaria'
    _inherit = ['construtec.financial.report.wizard.mixin']

    journal_id = fields.Many2one('account.journal', string='Diario de Banco', required=True,
                                  domain="[('company_id', '=', company_id), ('type', '=', 'bank')]")
    anio = fields.Integer(string='Año', required=True, default=lambda self: fields.Date.today().year)
    mes = fields.Selection(MESES, string='Mes', required=True)
    folio = fields.Integer(string='Folio Inicial', required=True, default=1)
    saldo_inicial = fields.Float(string='Saldo Inicial', required=True)

    def _date_range(self):
        mes = int(self.mes)
        date_from = date(self.anio, mes, 1)
        date_to = date(self.anio, mes, calendar.monthrange(self.anio, mes)[1])
        return date_from, date_to

    def _conciliados(self, date_from, date_to, sign):
        """sign=-1: cheques/pagos emitidos ya reflejados en el estado de cuenta.
        sign=1: depósitos/créditos ya reflejados en el estado de cuenta."""
        stmt_lines = self.env['account.bank.statement.line'].search([
            ('journal_id', '=', self.journal_id.id), ('date', '>=', date_from), ('date', '<=', date_to),
            ('amount', sign < 0 and '<' or '>', 0),
        ])
        payments = self.env['account.payment'].search([
            ('state', 'not in', ('cancel', 'draft')),
            ('reconciled_statement_line_ids', 'in', stmt_lines.ids),
        ]).sorted('date')
        return payments, stmt_lines

    def _no_conciliados(self, payment_type, date_from, date_to, excluded_ids):
        payments = self.env['account.payment'].search([
            ('journal_id', '=', self.journal_id.id), ('payment_type', '=', payment_type),
            ('date', '>=', date_from - relativedelta(months=5)), ('date', '<=', date_to),
            ('state', 'not in', ('cancel', 'draft')), ('id', 'not in', excluded_ids),
        ])
        result = self.env['account.payment']
        for payment in payments:
            lines = payment.reconciled_statement_line_ids
            if not lines or all(line.date < date_from or line.date > date_to for line in lines):
                result |= payment
        return result.sorted('date')

    def print_xls_conciliacion_bancaria(self):
        self.ensure_one()
        date_from, date_to = self._date_range()

        outbound_conc, stmt_out = self._conciliados(date_from, date_to, -1)
        inbound_conc, stmt_in = self._conciliados(date_from, date_to, 1)
        outbound_nc = self._no_conciliados('outbound', date_from, date_to, outbound_conc.ids)
        inbound_nc = self._no_conciliados('inbound', date_from, date_to, inbound_conc.ids)

        saldo_outbound = sum(outbound_conc.mapped('amount'))
        saldo_inbound = sum(inbound_conc.mapped('amount'))
        saldo_outbound_v = sum(outbound_nc.mapped('amount'))
        saldo_inbound_v = sum(inbound_nc.mapped('amount'))
        saldo_estado_cuenta = self.saldo_inicial + saldo_inbound - saldo_outbound
        saldo_contable = (saldo_estado_cuenta - saldo_outbound_v) + saldo_inbound_v

        buffer, workbook = self.new_workbook()
        sheet = workbook.add_worksheet('Conciliación Bancaria')
        sheet.set_landscape()
        for col, width in enumerate([16, 12, 10, 30, 14, 14, 14]):
            sheet.set_column(col, col, width)
        bold = workbook.add_format({'bold': True})
        center = workbook.add_format({'bold': True, 'align': 'center'})
        money = workbook.add_format({'num_format': '#,##0.00'})
        totales_fmt = workbook.add_format({'bold': True, 'top': 1})

        state = {'row': 0, 'folio': self.folio}

        def write_page_header():
            sheet.merge_range(state['row'], 0, state['row'], 6, 'CONCILIACIÓN BANCARIA', bold)
            state['row'] += 1
            caption = f'{self.journal_id.name} — {dict(MESES)[self.mes]} de {self.anio} — Folio: {state["folio"]}'
            sheet.merge_range(state['row'], 0, state['row'], 6, caption, center)
            state['row'] += 1
            sheet.merge_range(state['row'], 0, state['row'], 6, '(EXPRESADO EN QUETZALES)', center)
            state['row'] += 1
            sheet.write_row(state['row'], 0, ['Forma de Pago', 'Fecha', 'Circular', 'Nombre', 'Debe', 'Haber', 'Saldo'], bold)
            state['row'] += 1

        def check_page_break():
            if state['row'] % ROWS_PER_PAGE == 0:
                state['folio'] += 1
                write_page_header()

        write_page_header()
        sheet.write(state['row'], 0, 'Saldo Inicial', bold)
        sheet.write_number(state['row'], 6, self.saldo_inicial, money)
        state['row'] += 1

        def write_section(title, payments, sign, running):
            sheet.write(state['row'], 0, title, bold)
            state['row'] += 1
            total = 0.0
            for payment in payments:
                check_page_break()
                sheet.write(state['row'], 0, payment.payment_method_line_id.name or '')
                sheet.write(state['row'], 1, payment.date.strftime('%d-%m-%Y'))
                sheet.write(state['row'], 3, payment.partner_id.name or '')
                col = 4 if sign > 0 else 5
                sheet.write_number(state['row'], col, abs(payment.amount), money)
                running[0] += sign * payment.amount
                sheet.write_number(state['row'], 6, running[0], money)
                total += payment.amount
                state['row'] += 1
            sheet.write(state['row'], 0, f'Total {title}', totales_fmt)
            sheet.write_number(state['row'], 4 if sign > 0 else 5, total, totales_fmt)
            state['row'] += 1
            return total

        running = [self.saldo_inicial]
        write_section('Cheques y Pagos Conciliados', outbound_conc, -1, running)
        write_section('Depósitos y Créditos Conciliados', inbound_conc, 1, running)
        sheet.write(state['row'], 0, 'Saldo Según Estado de Cuenta', bold)
        sheet.write_number(state['row'], 6, saldo_estado_cuenta, money)
        state['row'] += 1
        write_section('Cheques en Circulación (no conciliados)', outbound_nc, -1, running)
        write_section('Depósitos en Circulación (no conciliados)', inbound_nc, 1, running)

        state['row'] += 1
        sheet.write(state['row'], 0, 'RESUMEN', bold)
        state['row'] += 1
        resumen_rows = [
            ('Saldo Inicial', self.saldo_inicial),
            ('Cheques y Pagos', -saldo_outbound),
            ('Depósitos y Otros Créditos', saldo_inbound),
            ('Saldo Según Estado de Cuenta', saldo_estado_cuenta),
            ('Cheques en Circulación', -saldo_outbound_v),
            ('Depósitos y Otros Créditos en Circulación', saldo_inbound_v),
            ('Saldo Contable', saldo_contable),
        ]
        for label, amount in resumen_rows:
            sheet.write(state['row'], 0, label)
            sheet.write_number(state['row'], 6, amount, money)
            state['row'] += 1

        state['row'] += 4
        sheet.write(state['row'], 0, 'Hecho por')
        sheet.write(state['row'], 4, 'Revisado por')

        return self.finalize_workbook(buffer, workbook, 'Conciliacion_Bancaria.xlsx')
