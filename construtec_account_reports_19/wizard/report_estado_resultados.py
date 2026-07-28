from odoo import fields, models
from odoo.exceptions import ValidationError

from ..models.account_classification import INCOME_STATEMENT_TYPES, build_report_tree


class WizardEstadoResultados(models.TransientModel):
    _name = 'wizard.estado.resultados'
    _description = 'Wizard Estado de Resultados'
    _inherit = ['construtec.financial.report.wizard.mixin']

    date_start = fields.Date(string='Del', required=True)
    date_end = fields.Date(string='Al', required=True)

    def check_date(self):
        for wizard in self:
            if wizard.date_end < wizard.date_start:
                raise ValidationError(self.env._('La fecha final debe ser posterior o igual a la fecha inicial.'))

    def print_xls_estado_resultados(self):
        self.ensure_one()
        self.check_date()
        tree = build_report_tree(self.env, self.company_id.id, self.date_end, self.date_start,
                                  account_types=INCOME_STATEMENT_TYPES)

        buffer, workbook = self.new_workbook()
        sheet = workbook.add_worksheet('Estado de Resultados')
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
        sheet.merge_range(row, 0, row, 2, 'Estado de Resultados', title_fmt)
        row += 1
        sheet.merge_range(row, 0, row, 2,
                           f'Del {self.date_start.strftime("%d/%m/%Y")} al {self.date_end.strftime("%d/%m/%Y")}', title_fmt)
        row += 2

        nivel1_totals = {}
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
            sheet.write(row, 0, f'Total {nivel1_label}', bold)
            sheet.write_number(row, 2, nivel1_total, subtotal_fmt)
            row += 2
            nivel1_totals[nivel1_label] = nivel1_total

        ingresos = nivel1_totals.get('INGRESOS', 0.0)
        costos = nivel1_totals.get('COSTOS', 0.0)
        gastos = nivel1_totals.get('GASTOS', 0.0)
        utilidad_bruta = ingresos - costos

        sheet.write(row, 0, 'UTILIDAD BRUTA', bold)
        sheet.write_number(row, 2, utilidad_bruta, subtotal_fmt)
        row += 2
        sheet.write(row, 0, 'UTILIDAD (PÉRDIDA) DEL EJERCICIO', bold)
        sheet.write_number(row, 2, utilidad_bruta - gastos, total_fmt)

        return self.finalize_workbook(buffer, workbook, 'Estado_de_Resultados.xlsx')
