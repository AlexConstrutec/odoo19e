import calendar
from datetime import date

from odoo import fields, models

from .wizard_mixin import MESES

ROWS_PER_PAGE = 47
JOURNAL_APERTURA = 'Partida de Apertura'
JOURNAL_CIERRE = 'Partida de Cierre'


class WizardReporteDiario(models.TransientModel):
    _name = 'wizard.reporte.diario'
    _description = 'Wizard Libro Diario'
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

    def _dummy_move_ids(self, date_from, date_to):
        """Asientos de cuadre: 2 líneas, misma cuenta, debe == haber (no son movimiento real)."""
        moves = self.env['account.move'].search([
            ('company_id', '=', self.company_id.id), ('state', '=', 'posted'),
            ('date', '>=', date_from), ('date', '<=', date_to),
        ])
        dummy = moves.filtered(
            lambda m: len(m.line_ids) == 2 and len(m.line_ids.account_id) == 1
            and sum(m.line_ids.mapped('debit')) == sum(m.line_ids.mapped('credit')))
        return dummy.ids

    def _get_lines(self, date_from, date_to, journal_filter, dummy_ids):
        domain = [
            ('move_id.company_id', '=', self.company_id.id), ('move_id.state', '=', 'posted'),
            ('date', '>=', date_from), ('date', '<=', date_to), ('move_id', 'not in', dummy_ids),
        ]
        if journal_filter == 'apertura':
            domain.append(('journal_id.name', '=', JOURNAL_APERTURA))
        elif journal_filter == 'cierre':
            domain.append(('journal_id.name', '=', JOURNAL_CIERRE))
        else:
            domain.append(('journal_id.name', 'not in', (JOURNAL_APERTURA, JOURNAL_CIERRE)))
        return self.env['account.move.line']._read_group(
            domain, ['date:day', 'move_id', 'account_id'], ['debit:sum', 'credit:sum'],
            order='date:day, move_id')

    def print_xls_libro_diario(self):
        self.ensure_one()
        date_from, date_to = self._date_range()
        dummy_ids = self._dummy_move_ids(date_from, date_to)

        buffer, workbook = self.new_workbook()
        sheet = workbook.add_worksheet('Libro Diario')
        sheet.set_column('A:A', 7)
        sheet.set_column('B:B', 50)
        sheet.set_column('C:D', 15)
        bold = workbook.add_format({'bold': True})
        center = workbook.add_format({'bold': True, 'align': 'center'})
        money = workbook.add_format({'num_format': '#,##0.00'})
        subtotal = workbook.add_format({'bold': True, 'top': 1})
        gray = workbook.add_format({'bg_color': '#DDDDDD', 'bold': True})

        state = {'row': 0, 'folio': self.folio, 'debe': 0.0, 'haber': 0.0}

        def write_page_header():
            sheet.write(state['row'], 3, f'Folio: {state["folio"]}', bold)
            state['row'] += 1
            sheet.merge_range(state['row'], 0, state['row'], 3, self.company_id.name, center)
            state['row'] += 1
            sheet.merge_range(state['row'], 0, state['row'], 3, f'NIT: {self.company_id.vat or ""}', center)
            state['row'] += 1
            sheet.merge_range(state['row'], 0, state['row'], 3, 'Libro Diario', center)
            state['row'] += 1
            caption = (f'Del 01 de {dict(MESES)[self.mes_de]} de {self.anio} '
                       f'Al {date_to.day} de {dict(MESES)[self.mes_a]} de {self.anio}')
            sheet.merge_range(state['row'], 0, state['row'], 3, caption, center)
            state['row'] += 1
            sheet.merge_range(state['row'], 0, state['row'], 3, '(EXPRESADO EN QUETZALES)', center)
            state['row'] += 1
            sheet.write_row(state['row'], 0, ['PDA', 'Cuenta', 'Debe', 'Haber'], bold)
            state['row'] += 1

        def check_page_break():
            if state['row'] - 0 >= ROWS_PER_PAGE and state['row'] % ROWS_PER_PAGE == 0:
                sheet.write_row(state['row'], 0, ['', 'VIENEN', state['debe'], state['haber']], gray)
                state['row'] += 1
                state['folio'] += 1
                write_page_header()
                sheet.write_row(state['row'], 0, ['', 'VAN', state['debe'], state['haber']], gray)
                state['row'] += 1

        write_page_header()

        for block, closing_label in (('apertura', 'V/Movimientos Partida de Apertura'),
                                      ('normal', 'V/Movimientos del dia'),
                                      ('cierre', 'V/Movimientos Partida de Cierre')):
            lines = self._get_lines(date_from, date_to, block, dummy_ids)
            current_move = None
            block_debe = block_haber = 0.0
            for line_date, move, account, debit, credit in lines:
                if move != current_move:
                    if current_move is not None:
                        sheet.write_row(state['row'], 0, ['', closing_label, block_debe, block_haber], subtotal)
                        state['row'] += 1
                        check_page_break()
                        block_debe = block_haber = 0.0
                    sheet.write(state['row'], 0, move.partida_contable or move.id)
                    sheet.write(state['row'], 1, line_date.strftime('%d-%m-%Y'))
                    state['row'] += 1
                    current_move = move
                sheet.write(state['row'], 1, f'{account.code} {account.name}')
                sheet.write_number(state['row'], 2, debit, money)
                sheet.write_number(state['row'], 3, credit, money)
                state['row'] += 1
                state['debe'] += debit
                state['haber'] += credit
                block_debe += debit
                block_haber += credit
                check_page_break()
            if current_move is not None:
                sheet.write_row(state['row'], 0, ['', closing_label, block_debe, block_haber], subtotal)
                state['row'] += 1
                check_page_break()

        return self.finalize_workbook(buffer, workbook, 'Libro_Diario.xlsx')
