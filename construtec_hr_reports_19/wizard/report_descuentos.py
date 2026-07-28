from odoo import fields, models

COLUMNS = ['Empleado', 'Empresa', 'Area', 'Departamento', 'Fecha', 'Tipo de anticipo', 'Concepto', 'Monto',
           'Ingreso', 'Comentario']


class WizardReporteDescuentos(models.TransientModel):
    _name = 'wizard.reporte.descuentos'
    _description = 'Wizard Reporte de Descuentos'
    _inherit = ['construtec.nomina.report.wizard.mixin']

    date_start = fields.Date(string='Del', required=True)
    date_end = fields.Date(string='Al', required=True)

    def print_xls_reporte_descuentos(self):
        self.ensure_one()
        self.check_date()
        employees = self.env['hr.employee'].with_context(active_test=False).search(
            [('company_id', '=', self.company_id.id)])

        buffer, workbook = self.new_workbook()
        sheet = workbook.add_worksheet('Reporte de Descuentos')
        bold = workbook.add_format({'bold': True})
        money = workbook.add_format({'num_format': '#,##0.00'})
        sheet.merge_range(0, 0, 0, len(COLUMNS) - 1, 'Reporte de Descuentos', bold)
        for col, header in enumerate(COLUMNS):
            sheet.write(1, col, header, bold)

        row = 2
        for employee in employees:
            version = employee.version_id
            departamento = version.department_id.parent_id.name or ''
            for advance in employee.descuentos.filtered(
                    lambda a: self.date_start <= a.date <= self.date_end):
                data_row = [
                    employee.name, employee.company_id.name, employee.department_id.name or '', departamento,
                    advance.date, advance.tipo_anticipo.name or '', advance.concepto.name or '',
                    abs(advance.advance), advance.create_uid.name, advance.reason or '',
                ]
                for col, value in enumerate(data_row):
                    if isinstance(value, float):
                        sheet.write_number(row, col, value, money)
                    else:
                        sheet.write(row, col, value)
                row += 1

            loan_lines = employee.prestamos.mapped('loan_lines').filtered(
                lambda line: self.date_start <= line.date <= self.date_end)
            for line in loan_lines:
                data_row = [
                    employee.name, employee.company_id.name, employee.department_id.name or '', departamento,
                    line.date, 'Anticipo 3', line.loan_id.concepto.name or '', abs(line.amount),
                    line.create_uid.name, 'Prestamo',
                ]
                for col, value in enumerate(data_row):
                    if isinstance(value, float):
                        sheet.write_number(row, col, value, money)
                    else:
                        sheet.write(row, col, value)
                row += 1

        return self.finalize_workbook(buffer, workbook, 'Reporte_Descuentos.xlsx')
