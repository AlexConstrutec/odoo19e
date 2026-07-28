from odoo import fields, models

from ..models.account_classification import BALANCE_SHEET_TYPES, build_report_tree, compute_resultado_ejercicio


class WizardBalanceGeneral(models.TransientModel):
    _name = 'wizard.balance.general'
    _description = 'Wizard Balance General'
    _inherit = ['construtec.financial.report.wizard.mixin']

    date_end = fields.Date(string='Al', required=True)

    def print_xls_balance_general(self):
        self.ensure_one()
        fiscal_year_start = self.company_id.compute_fiscalyear_dates(self.date_end)['date_from']
        tree = build_report_tree(self.env, self.company_id.id, self.date_end, account_types=BALANCE_SHEET_TYPES)
        resultado_ejercicio = compute_resultado_ejercicio(self.env, self.company_id.id, fiscal_year_start, self.date_end)

        buffer, workbook = self.new_workbook()
        sheet = workbook.add_worksheet('Balance General')
        sheet.set_column('A:A', 45)
        sheet.set_column('B:C', 18)
        bold = workbook.add_format({'bold': True})
        title_fmt = workbook.add_format({'bold': True, 'align': 'center', 'font_size': 12})
        nivel1_fmt = workbook.add_format({'bold': True, 'bg_color': '#DDEBF7'})
        nivel2_fmt = workbook.add_format({'bold': True, 'italic': True})
        money = workbook.add_format({'num_format': '#,##0.00'})
        subtotal_fmt = workbook.add_format({'bold': True, 'top': 1, 'num_format': '#,##0.00'})
        total_fmt = workbook.add_format({'bold': True, 'top': 1, 'bottom': 6, 'num_format': '#,##0.00'})

        row = 0
        sheet.merge_range(row, 0, row, 2, self.company_id.name, title_fmt)
        row += 1
        sheet.merge_range(row, 0, row, 2, 'Balance General', title_fmt)
        row += 1
        sheet.merge_range(row, 0, row, 2, f'Al {self.date_end.strftime("%d/%m/%Y")}', title_fmt)
        row += 2

        totals_nivel0 = {'activo': 0.0, 'pasivo': 0.0, 'patrimonio': 0.0}

        def nivel0_of(nivel1_label):
            if nivel1_label.startswith('ACTIVO'):
                return 'activo'
            if nivel1_label.startswith('PASIVO'):
                return 'pasivo'
            return 'patrimonio'

        for nivel1_label, grupos in tree.items():
            sheet.write(row, 0, nivel1_label, nivel1_fmt)
            row += 1
            nivel1_total = 0.0
            for nivel2_label, cuentas in grupos.items():
                sheet.write(row, 0, nivel2_label, nivel2_fmt)
                row += 1
                nivel2_total = 0.0
                for account, balance in sorted(cuentas, key=lambda c: c[0].code or ''):
                    sheet.write(row, 0, f'  {account.code} {account.name}')
                    sheet.write_number(row, 1, balance, money)
                    row += 1
                    nivel2_total += balance
                sheet.write(row, 0, f'Total {nivel2_label}')
                sheet.write_number(row, 1, nivel2_total, subtotal_fmt)
                row += 1
                nivel1_total += nivel2_total

            if nivel1_label == 'PATRIMONIO':
                sheet.write(row, 0, 'Resultado del Ejercicio')
                sheet.write_number(row, 1, resultado_ejercicio, money)
                row += 1
                nivel1_total += resultado_ejercicio

            sheet.write(row, 0, f'Total {nivel1_label}', bold)
            sheet.write_number(row, 2, nivel1_total, subtotal_fmt)
            row += 2
            totals_nivel0[nivel0_of(nivel1_label)] += nivel1_total

        sheet.write(row, 0, 'TOTAL ACTIVO', bold)
        sheet.write_number(row, 2, totals_nivel0['activo'], total_fmt)
        row += 1
        sheet.write(row, 0, 'TOTAL PASIVO + PATRIMONIO', bold)
        sheet.write_number(row, 2, totals_nivel0['pasivo'] + totals_nivel0['patrimonio'], total_fmt)

        return self.finalize_workbook(buffer, workbook, 'Balance_General.xlsx')
