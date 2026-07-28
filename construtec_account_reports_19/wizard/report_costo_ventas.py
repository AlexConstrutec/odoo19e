from odoo import fields, models
from odoo.exceptions import ValidationError


class WizardCostoReporteMixin(models.AbstractModel):
    """Base para Costo de Ventas / Costo de Producción: ambos son un desglose de cuentas de
    account_type='expense_direct_cost'. El módulo original los distinguía por prefijo de
    account.group específico de un plan de cuentas; aquí se usa opcionalmente el nombre del
    account.group (si el plan de cuentas del cliente los separa) en vez de códigos hardcodeados —
    si no hay grupos que coincidan con el filtro, se muestran todas las cuentas de costo directo."""
    _name = 'construtec.costo.reporte.mixin'
    _description = 'Mixin Reportes de Costo'

    date_start = fields.Date(string='Del', required=True)
    date_end = fields.Date(string='Al', required=True)

    def check_date(self):
        for wizard in self:
            if wizard.date_end < wizard.date_start:
                raise ValidationError(self.env._('La fecha final debe ser posterior o igual a la fecha inicial.'))

    def _group_name_filter(self):
        return None

    def _print_costo(self, titulo, filename):
        self.ensure_one()
        self.check_date()
        domain = [
            ('company_id', '=', self.company_id.id), ('date', '>=', self.date_start),
            ('date', '<=', self.date_end), ('parent_state', '=', 'posted'),
            ('account_id.account_type', '=', 'expense_direct_cost'),
        ]
        name_filter = self._group_name_filter()
        if name_filter:
            matching_group_ids = self.env['account.group'].search(
                [('name', 'ilike', name_filter)]).ids
            if matching_group_ids:
                domain.append(('account_id.group_id', 'in', matching_group_ids))

        grouped = self.env['account.move.line']._read_group(domain, ['account_id'], ['balance:sum'])

        buffer, workbook = self.new_workbook()
        sheet = workbook.add_worksheet(titulo[:31])
        sheet.set_column('A:A', 45)
        sheet.set_column('B:B', 18)
        bold = workbook.add_format({'bold': True})
        title_fmt = workbook.add_format({'bold': True, 'align': 'center', 'font_size': 12})
        money = workbook.add_format({'num_format': '#,##0.00'})
        total_fmt = workbook.add_format({'bold': True, 'top': 1, 'num_format': '#,##0.00'})

        row = 0
        sheet.merge_range(row, 0, row, 1, self.company_id.name, title_fmt)
        row += 1
        sheet.merge_range(row, 0, row, 1, titulo, title_fmt)
        row += 1
        sheet.merge_range(row, 0, row, 1,
                           f'Del {self.date_start.strftime("%d/%m/%Y")} al {self.date_end.strftime("%d/%m/%Y")}', title_fmt)
        row += 2

        total = 0.0
        for account, balance in sorted(grouped, key=lambda g: g[0].code or ''):
            if not balance:
                continue
            sheet.write(row, 0, f'{account.code} {account.name}')
            sheet.write_number(row, 1, balance, money)
            row += 1
            total += balance

        sheet.write(row, 0, f'Total {titulo}', bold)
        sheet.write_number(row, 1, total, total_fmt)

        return self.finalize_workbook(buffer, workbook, filename)


class WizardCostoVentas(models.TransientModel):
    _name = 'wizard.costo.ventas'
    _description = 'Wizard Costo de Ventas'
    _inherit = ['construtec.financial.report.wizard.mixin', 'construtec.costo.reporte.mixin']

    def print_xls_costo_ventas(self):
        return self._print_costo('Costo de Ventas', 'Costo_de_Ventas.xlsx')
