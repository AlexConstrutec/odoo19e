from datetime import timedelta

from odoo import fields, models
from odoo.exceptions import ValidationError

from ..models.account_classification import compute_resultado_ejercicio

COLUMNS = ['Concepto', 'Saldo Inicial', 'Aumentos', 'Disminuciones', 'Saldo Final']


class WizardCambioPatrimonio(models.TransientModel):
    _name = 'wizard.cambio.patrimonio'
    _description = 'Wizard Estado de Cambios en el Patrimonio'
    _inherit = ['construtec.financial.report.wizard.mixin']

    date_start = fields.Date(string='Del', required=True)
    date_end = fields.Date(string='Al', required=True)

    def check_date(self):
        for wizard in self:
            if wizard.date_end < wizard.date_start:
                raise ValidationError(self.env._('La fecha final debe ser posterior o igual a la fecha inicial.'))

    def _component_accounts(self):
        """Cuentas de patrimonio agrupadas por componente. Usa el nombre del account.group del
        cliente (si existe) para separar Capital/Reservas en vez de prefijos de código
        hardcodeados; lo que no calce en ningún grupo nombrado cae en 'Otras Cuentas de Capital'."""
        equity_accounts = self.env['account.account'].search([('account_type', '=', 'equity')])
        capital = equity_accounts.filtered(lambda a: a.group_id and 'capital' in (a.group_id.name or '').lower())
        reservas = equity_accounts.filtered(lambda a: a.group_id and 'reserva' in (a.group_id.name or '').lower())
        otras = equity_accounts - capital - reservas
        unaffected = self.env['account.account'].search([('account_type', '=', 'equity_unaffected')])
        return [
            ('Capital Social', capital),
            ('Reservas', reservas),
            ('Otras Cuentas de Capital', otras),
            ('Resultados de Ejercicios Anteriores', unaffected),
        ]

    def _balance(self, accounts, date_to):
        if not accounts:
            return 0.0
        lines = self.env['account.move.line'].search([
            ('account_id', 'in', accounts.ids), ('company_id', '=', self.company_id.id),
            ('date', '<=', date_to), ('parent_state', '=', 'posted'),
        ])
        return -(sum(lines.mapped('debit')) - sum(lines.mapped('credit')))

    def _movimiento(self, accounts):
        if not accounts:
            return 0.0, 0.0
        lines = self.env['account.move.line'].search([
            ('account_id', 'in', accounts.ids), ('company_id', '=', self.company_id.id),
            ('date', '>=', self.date_start), ('date', '<=', self.date_end), ('parent_state', '=', 'posted'),
        ])
        return sum(lines.mapped('credit')), sum(lines.mapped('debit'))

    def print_xls_cambio_patrimonio(self):
        self.ensure_one()
        self.check_date()
        date_before = self.date_start - timedelta(days=1)

        buffer, workbook = self.new_workbook()
        sheet = workbook.add_worksheet('Cambios en el Patrimonio')
        sheet.set_column('A:A', 40)
        sheet.set_column('B:E', 18)
        bold = workbook.add_format({'bold': True})
        title_fmt = workbook.add_format({'bold': True, 'align': 'center', 'font_size': 12})
        money = workbook.add_format({'num_format': '#,##0.00'})
        total_fmt = workbook.add_format({'bold': True, 'top': 1, 'num_format': '#,##0.00'})

        row = 0
        sheet.merge_range(row, 0, row, 4, self.company_id.name, title_fmt)
        row += 1
        sheet.merge_range(row, 0, row, 4, 'Estado de Cambios en el Patrimonio', title_fmt)
        row += 1
        sheet.merge_range(row, 0, row, 4,
                           f'Del {self.date_start.strftime("%d/%m/%Y")} al {self.date_end.strftime("%d/%m/%Y")}', title_fmt)
        row += 2
        sheet.write_row(row, 0, COLUMNS, bold)
        row += 1

        totals = [0.0, 0.0, 0.0, 0.0]
        for label, accounts in self._component_accounts():
            saldo_inicial = self._balance(accounts, date_before)
            aumentos, disminuciones = self._movimiento(accounts)
            saldo_final = self._balance(accounts, self.date_end)
            values = [saldo_inicial, aumentos, disminuciones, saldo_final]
            sheet.write(row, 0, label)
            for col, value in enumerate(values):
                sheet.write_number(row, 1 + col, value, money)
                totals[col] += value
            row += 1

        resultado_ejercicio = compute_resultado_ejercicio(self.env, self.company_id.id, self.date_start, self.date_end)
        sheet.write(row, 0, 'Resultado del Ejercicio')
        sheet.write_number(row, 1, 0.0, money)
        sheet.write_number(row, 2, resultado_ejercicio if resultado_ejercicio > 0 else 0.0, money)
        sheet.write_number(row, 3, -resultado_ejercicio if resultado_ejercicio < 0 else 0.0, money)
        sheet.write_number(row, 4, resultado_ejercicio, money)
        totals[1] += 0.0
        totals[3] += resultado_ejercicio
        row += 1

        sheet.write(row, 0, 'TOTAL PATRIMONIO', bold)
        for col, value in enumerate(totals):
            sheet.write_number(row, 1 + col, value, total_fmt)

        return self.finalize_workbook(buffer, workbook, 'Cambios_en_el_Patrimonio.xlsx')
