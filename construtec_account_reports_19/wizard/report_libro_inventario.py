from odoo import fields, models

from ..models.account_classification import BALANCE_SHEET_TYPES, build_report_tree, compute_resultado_ejercicio

ROWS_PER_PAGE = 40


class WizardLibroInventario(models.TransientModel):
    _name = 'wizard.libro.inventario'
    _description = 'Wizard Libro de Inventario y Balances'
    _inherit = ['construtec.financial.report.wizard.mixin']

    date_end = fields.Date(string='Al', required=True)
    folio = fields.Integer(string='Folio Inicial', required=True, default=1)

    def print_xls_libro_inventario(self):
        self.ensure_one()
        fiscal_year_start = self.company_id.compute_fiscalyear_dates(self.date_end)['date_from']
        tree = build_report_tree(self.env, self.company_id.id, self.date_end, account_types=BALANCE_SHEET_TYPES)
        resultado_ejercicio = compute_resultado_ejercicio(self.env, self.company_id.id, fiscal_year_start, self.date_end)

        buffer, workbook = self.new_workbook()
        sheet = workbook.add_worksheet('Libro de Inventario')
        sheet.set_column('A:A', 12)
        sheet.set_column('B:B', 45)
        sheet.set_column('C:C', 18)
        bold = workbook.add_format({'bold': True})
        center = workbook.add_format({'bold': True, 'align': 'center'})
        nivel1_fmt = workbook.add_format({'bold': True, 'bg_color': '#DDEBF7'})
        nivel2_fmt = workbook.add_format({'bold': True, 'italic': True})
        money = workbook.add_format({'num_format': '#,##0.00'})
        subtotal_fmt = workbook.add_format({'bold': True, 'top': 1, 'num_format': '#,##0.00'})

        state = {'row': 0, 'folio': self.folio}

        def write_page_header():
            sheet.write(state['row'], 2, f'Folio: {state["folio"]}', bold)
            state['row'] += 1
            sheet.merge_range(state['row'], 0, state['row'], 2, self.company_id.name, center)
            state['row'] += 1
            sheet.merge_range(state['row'], 0, state['row'], 2, f'NIT: {self.company_id.vat or ""}', center)
            state['row'] += 1
            sheet.merge_range(state['row'], 0, state['row'], 2, 'Libro de Inventario y Balances', center)
            state['row'] += 1
            sheet.merge_range(state['row'], 0, state['row'], 2, f'Al {self.date_end.strftime("%d/%m/%Y")}', center)
            state['row'] += 1
            sheet.write_row(state['row'], 0, ['Código', 'Cuenta', 'Saldo'], bold)
            state['row'] += 1

        def check_page_break():
            if state['row'] % ROWS_PER_PAGE == 0:
                state['folio'] += 1
                write_page_header()

        write_page_header()

        totals_nivel0 = {'activo': 0.0, 'pasivo': 0.0, 'patrimonio': 0.0}
        nivel0_of = lambda label: 'activo' if label.startswith('ACTIVO') else ('pasivo' if label.startswith('PASIVO') else 'patrimonio')

        for nivel1_label, grupos in tree.items():
            check_page_break()
            sheet.merge_range(state['row'], 0, state['row'], 2, nivel1_label, nivel1_fmt)
            state['row'] += 1
            nivel1_total = 0.0
            for nivel2_label, cuentas in grupos.items():
                check_page_break()
                sheet.merge_range(state['row'], 0, state['row'], 2, nivel2_label, nivel2_fmt)
                state['row'] += 1
                nivel2_total = 0.0
                for account, balance in sorted(cuentas, key=lambda c: c[0].code or ''):
                    check_page_break()
                    sheet.write(state['row'], 0, account.code)
                    sheet.write(state['row'], 1, account.name)
                    sheet.write_number(state['row'], 2, balance, money)
                    state['row'] += 1
                    nivel2_total += balance
                check_page_break()
                sheet.write(state['row'], 1, f'Total {nivel2_label}')
                sheet.write_number(state['row'], 2, nivel2_total, subtotal_fmt)
                state['row'] += 1
                nivel1_total += nivel2_total

            if nivel1_label == 'PATRIMONIO':
                check_page_break()
                sheet.write(state['row'], 1, 'Resultado del Ejercicio')
                sheet.write_number(state['row'], 2, resultado_ejercicio, money)
                state['row'] += 1
                nivel1_total += resultado_ejercicio

            check_page_break()
            sheet.write(state['row'], 1, f'Total {nivel1_label}', bold)
            sheet.write_number(state['row'], 2, nivel1_total, subtotal_fmt)
            state['row'] += 1
            totals_nivel0[nivel0_of(nivel1_label)] += nivel1_total

        check_page_break()
        sheet.write(state['row'], 1, 'TOTAL ACTIVO', bold)
        sheet.write_number(state['row'], 2, totals_nivel0['activo'], subtotal_fmt)
        state['row'] += 1
        check_page_break()
        sheet.write(state['row'], 1, 'TOTAL PASIVO + PATRIMONIO', bold)
        sheet.write_number(state['row'], 2, totals_nivel0['pasivo'] + totals_nivel0['patrimonio'], subtotal_fmt)

        return self.finalize_workbook(buffer, workbook, 'Libro_de_Inventario.xlsx')
