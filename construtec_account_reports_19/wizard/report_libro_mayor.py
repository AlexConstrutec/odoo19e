import calendar
from datetime import date

from odoo import fields, models

from .wizard_mixin import MESES

ROWS_PER_PAGE = 35


class WizardReporteMayor(models.TransientModel):
    _name = 'wizard.reporte.mayor'
    _description = 'Wizard Libro Mayor'
    _inherit = ['construtec.financial.report.wizard.mixin']

    anio = fields.Integer(string='Año', required=True, default=lambda self: fields.Date.today().year)
    mes_de = fields.Selection(MESES, string='Mes Del', required=True)
    mes_a = fields.Selection(MESES, string='Mes Al', required=True)
    folio = fields.Integer(string='Folio Inicial', required=True, default=1)

    def _date_range(self):
        mes_de, mes_a = int(self.mes_de), int(self.mes_a)
        date_from = date(self.anio, mes_de, 1)
        date_to = date(self.anio, mes_a, calendar.monthrange(self.anio, mes_a)[1])
        return date_from, date_to

    def _opening_balance(self, account, date_from):
        """Saldo de apertura calculado vía ORM (suma de movimientos previos a date_from),
        sin depender de funciones SQL externas al esquema estándar de Odoo."""
        lines = self.env['account.move.line'].search([
            ('account_id', '=', account.id), ('company_id', '=', self.company_id.id),
            ('date', '<', date_from), ('parent_state', '=', 'posted'),
        ])
        balance = sum(lines.mapped('debit')) - sum(lines.mapped('credit'))
        return (balance, 0.0) if balance >= 0 else (0.0, -balance)

    def print_xls_libro_mayor(self):
        self.ensure_one()
        date_from, date_to = self._date_range()

        move_lines = self.env['account.move.line'].search([
            ('company_id', '=', self.company_id.id), ('parent_state', '=', 'posted'),
            ('date', '>=', date_from), ('date', '<=', date_to),
        ], order='account_id, date')
        accounts = move_lines.account_id.sorted('code')

        buffer, workbook = self.new_workbook()
        sheet = workbook.add_worksheet('Libro Mayor')
        sheet.set_landscape()
        for col, width in enumerate([12, 15, 15, 15, 12, 15, 15, 15]):
            sheet.set_column(col, col, width)
        bold = workbook.add_format({'bold': True})
        center = workbook.add_format({'bold': True, 'align': 'center'})
        money = workbook.add_format({'num_format': '#,##0.00'})
        totales_fmt = workbook.add_format({'bold': True, 'top': 1})
        gray = workbook.add_format({'bg_color': '#DDDDDD', 'bold': True})

        state = {'row': 0, 'folio': self.folio}

        def write_page_header():
            sheet.merge_range(state['row'], 0, state['row'], 7, f'{self.company_id.name} — Libro Mayor', bold)
            state['row'] += 1
            caption = (f'Del 01 de {dict(MESES)[self.mes_de]} de {self.anio} '
                       f'Al {date_to.day} de {dict(MESES)[self.mes_a]} de {self.anio} — Folio: {state["folio"]}')
            sheet.merge_range(state['row'], 0, state['row'], 7, caption, center)
            state['row'] += 1

        write_page_header()

        for account in accounts:
            lines = move_lines.filtered(lambda l, a=account: l.account_id == a)
            saldo_debe, saldo_haber = self._opening_balance(account, date_from)

            sheet.merge_range(state['row'], 0, state['row'], 1, 'DEBE', center)
            sheet.merge_range(state['row'], 2, state['row'], 5, f'{account.code} {account.name}', center)
            sheet.merge_range(state['row'], 6, state['row'], 7, 'HABER', center)
            state['row'] += 1
            sheet.write(state['row'], 1, 'Saldo inicial', bold)
            sheet.write_number(state['row'], 3, saldo_debe, money)
            sheet.write_number(state['row'], 7, saldo_haber, money)
            state['row'] += 1

            debit_lines = lines.filtered(lambda l: l.debit > 0).sorted('date')
            credit_lines = lines.filtered(lambda l: l.credit > 0).sorted('date')
            total_debe = total_haber = 0.0
            for i in range(max(len(debit_lines), len(credit_lines))):
                if state['row'] % ROWS_PER_PAGE == 0:
                    state['folio'] += 1
                    write_page_header()
                if i < len(debit_lines):
                    dl = debit_lines[i]
                    saldo_debe += dl.debit
                    total_debe += dl.debit
                    sheet.write(state['row'], 0, dl.move_id.partida_contable or dl.move_id.id)
                    sheet.write(state['row'], 1, dl.date.strftime('%d-%m-%Y'))
                    sheet.write_number(state['row'], 2, dl.debit, money)
                    sheet.write_number(state['row'], 3, saldo_debe, money)
                if i < len(credit_lines):
                    cl = credit_lines[i]
                    saldo_haber += cl.credit
                    total_haber += cl.credit
                    sheet.write(state['row'], 4, cl.move_id.partida_contable or cl.move_id.id)
                    sheet.write(state['row'], 5, cl.date.strftime('%d-%m-%Y'))
                    sheet.write_number(state['row'], 6, cl.credit, money)
                    sheet.write_number(state['row'], 7, saldo_haber, money)
                state['row'] += 1

            sheet.merge_range(state['row'], 0, state['row'], 1, 'TOTALES', totales_fmt)
            sheet.write_number(state['row'], 2, total_debe, totales_fmt)
            sheet.write_number(state['row'], 3, saldo_debe, totales_fmt)
            sheet.merge_range(state['row'], 4, state['row'], 5, 'TOTALES', totales_fmt)
            sheet.write_number(state['row'], 6, total_haber, totales_fmt)
            sheet.write_number(state['row'], 7, saldo_haber, totales_fmt)
            state['row'] += 1

        return self.finalize_workbook(buffer, workbook, 'Libro_Mayor.xlsx')
