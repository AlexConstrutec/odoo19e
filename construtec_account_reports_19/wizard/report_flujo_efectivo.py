from datetime import timedelta

from odoo import fields, models
from odoo.exceptions import ValidationError

TAG_XMLIDS = [
    ('construtec_account_reports_19.tag_flujo_operacion', 'Actividades de Operación'),
    ('construtec_account_reports_19.tag_flujo_inversion', 'Actividades de Inversión'),
    ('construtec_account_reports_19.tag_flujo_financiamiento', 'Actividades de Financiamiento'),
]


class WizardFlujoEfectivo(models.TransientModel):
    _name = 'wizard.flujo.efectivo'
    _description = 'Wizard Estado de Flujo de Efectivo'
    _inherit = ['construtec.financial.report.wizard.mixin']

    date_start = fields.Date(string='Del', required=True)
    date_end = fields.Date(string='Al', required=True)

    def check_date(self):
        for wizard in self:
            if wizard.date_end < wizard.date_start:
                raise ValidationError(self.env._('La fecha final debe ser posterior o igual a la fecha inicial.'))

    def _cash_balance(self, date_to):
        lines = self.env['account.move.line'].search([
            ('company_id', '=', self.company_id.id), ('date', '<=', date_to), ('parent_state', '=', 'posted'),
            ('account_id.account_type', '=', 'asset_cash'),
        ])
        return sum(lines.mapped('debit')) - sum(lines.mapped('credit'))

    def _flujo_por_tag(self, tag_xmlid):
        tag = self.env.ref(tag_xmlid, raise_if_not_found=False)
        if not tag:
            return 0.0
        lines = self.env['account.move.line'].search([
            ('company_id', '=', self.company_id.id), ('date', '>=', self.date_start), ('date', '<=', self.date_end),
            ('parent_state', '=', 'posted'), ('account_id.tag_ids', 'in', tag.id),
            ('account_id.account_type', '!=', 'asset_cash'),
        ])
        # Contrapartida en cuentas de caja: el impacto en efectivo es -(cambio en la cuenta relacionada)
        return sum(lines.mapped('credit')) - sum(lines.mapped('debit'))

    def print_xls_flujo_efectivo(self):
        self.ensure_one()
        self.check_date()
        saldo_inicial = self._cash_balance(self.date_start - timedelta(days=1))
        saldo_final_real = self._cash_balance(self.date_end)

        buffer, workbook = self.new_workbook()
        sheet = workbook.add_worksheet('Flujo de Efectivo')
        sheet.set_column('A:A', 45)
        sheet.set_column('B:B', 18)
        bold = workbook.add_format({'bold': True})
        title_fmt = workbook.add_format({'bold': True, 'align': 'center', 'font_size': 12})
        money = workbook.add_format({'num_format': '#,##0.00'})
        total_fmt = workbook.add_format({'bold': True, 'top': 1, 'num_format': '#,##0.00'})

        row = 0
        sheet.merge_range(row, 0, row, 1, self.company_id.name, title_fmt)
        row += 1
        sheet.merge_range(row, 0, row, 1, 'Estado de Flujo de Efectivo', title_fmt)
        row += 1
        sheet.merge_range(row, 0, row, 1,
                           f'Del {self.date_start.strftime("%d/%m/%Y")} al {self.date_end.strftime("%d/%m/%Y")}', title_fmt)
        row += 2

        sheet.write(row, 0, 'Saldo Inicial de Efectivo')
        sheet.write_number(row, 1, saldo_inicial, money)
        row += 2

        flujo_neto = 0.0
        for tag_xmlid, label in TAG_XMLIDS:
            monto = self._flujo_por_tag(tag_xmlid)
            sheet.write(row, 0, label)
            sheet.write_number(row, 1, monto, money)
            row += 1
            flujo_neto += monto
        row += 1

        sheet.write(row, 0, 'Cambio Neto en Efectivo', bold)
        sheet.write_number(row, 1, flujo_neto, total_fmt)
        row += 2

        sheet.write(row, 0, 'Saldo Final de Efectivo (calculado)')
        sheet.write_number(row, 1, saldo_inicial + flujo_neto, money)
        row += 1
        sheet.write(row, 0, 'Saldo Final de Efectivo (según libros)')
        sheet.write_number(row, 1, saldo_final_real, money)
        row += 1
        sheet.write(row, 0, 'Diferencia (cuentas sin clasificar por actividad)')
        sheet.write_number(row, 1, saldo_final_real - (saldo_inicial + flujo_neto), money)

        return self.finalize_workbook(buffer, workbook, 'Flujo_de_Efectivo.xlsx')
