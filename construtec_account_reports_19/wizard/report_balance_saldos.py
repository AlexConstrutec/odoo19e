from odoo import fields, models
from odoo.exceptions import ValidationError

COLUMNS = ['Código', 'Cuenta', 'Saldo Inicial Debe', 'Saldo Inicial Haber', 'Movimiento Debe', 'Movimiento Haber',
           'Saldo Final Debe', 'Saldo Final Haber']


class WizardBalanceSaldos(models.TransientModel):
    _name = 'wizard.balance.saldos'
    _description = 'Wizard Balance de Saldos'
    _inherit = ['construtec.financial.report.wizard.mixin']

    date_start = fields.Date(string='Del', required=True)
    date_end = fields.Date(string='Al', required=True)

    def check_date(self):
        for wizard in self:
            if wizard.date_end < wizard.date_start:
                raise ValidationError(self.env._('La fecha final debe ser posterior o igual a la fecha inicial.'))

    def print_xls_balance_saldos(self):
        self.ensure_one()
        self.check_date()

        opening_lines = self.env['account.move.line'].search([
            ('company_id', '=', self.company_id.id), ('parent_state', '=', 'posted'),
            ('date', '<', self.date_start),
        ])
        period_lines = self.env['account.move.line'].search([
            ('company_id', '=', self.company_id.id), ('parent_state', '=', 'posted'),
            ('date', '>=', self.date_start), ('date', '<=', self.date_end),
        ])
        accounts = (opening_lines | period_lines).account_id.sorted('code')

        buffer, workbook = self.new_workbook()
        sheet = workbook.add_worksheet('Balance de Saldos')
        sheet.set_landscape()
        bold = workbook.add_format({'bold': True})
        money = workbook.add_format({'num_format': '#,##0.00'})
        totales_fmt = workbook.add_format({'bold': True, 'top': 1, 'num_format': '#,##0.00'})
        sheet.write_row(0, 0, COLUMNS, bold)

        row = 1
        totals = [0.0] * 6
        for account in accounts:
            op = opening_lines.filtered(lambda l, a=account: l.account_id == a)
            pe = period_lines.filtered(lambda l, a=account: l.account_id == a)
            op_balance = sum(op.mapped('debit')) - sum(op.mapped('credit'))
            si_debe, si_haber = (op_balance, 0.0) if op_balance >= 0 else (0.0, -op_balance)
            mov_debe, mov_haber = sum(pe.mapped('debit')), sum(pe.mapped('credit'))
            sf_balance = op_balance + mov_debe - mov_haber
            sf_debe, sf_haber = (sf_balance, 0.0) if sf_balance >= 0 else (0.0, -sf_balance)

            values = [si_debe, si_haber, mov_debe, mov_haber, sf_debe, sf_haber]
            if not any(values):
                continue
            sheet.write(row, 0, account.code)
            sheet.write(row, 1, account.name)
            for col, value in enumerate(values):
                sheet.write_number(row, 2 + col, value, money)
                totals[col] += value
            row += 1

        sheet.write(row, 1, 'TOTALES', bold)
        for col, value in enumerate(totals):
            sheet.write_number(row, 2 + col, value, totales_fmt)

        return self.finalize_workbook(buffer, workbook, 'Balance_de_Saldos.xlsx')
