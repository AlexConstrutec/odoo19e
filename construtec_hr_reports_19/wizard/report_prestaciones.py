from odoo import fields, models

COLUMNS = [
    'Mes', 'Fecha Del', 'Fecha Al', 'Referencia de Nómina', 'Nombre de empleado', 'Departamento', 'Area',
    'Fecha de contrato', 'Puesto', 'Bono Anual', 'Aguinaldo', 'Indemnización', 'Vacaciones',
    'Total de Prestaciones',
]


def net_prestaciones(payslip):
    """Reserva neta de prestaciones de una nómina: devengado del período menos lo ya pagado."""
    codes = {}
    for line in payslip.line_ids:
        codes[line.code] = codes.get(line.code, 0.0) + line.total
    bono14 = codes.get('BONO14', 0.0) - codes.get('BONO14P', 0.0)
    aguinaldo = codes.get('AGUINALDO', 0.0) - codes.get('AGUINALDOP', 0.0)
    indemnizacion = codes.get('INDM', 0.0) - codes.get('INDEMP', 0.0)
    vacaciones = codes.get('VACAC', 0.0) - codes.get('VACACPAG', 0.0)
    return bono14, aguinaldo, indemnizacion, vacaciones


def prestaciones_row(payslip):
    employee = payslip.employee_id
    version = payslip.version_id
    bono14, aguinaldo, indemnizacion, vacaciones = net_prestaciones(payslip)
    return [
        payslip.date_from.strftime('%B'),
        payslip.date_from.strftime('%d/%m/%Y'),
        payslip.date_to.strftime('%d/%m/%Y'),
        payslip.payslip_run_id.name or '',
        employee.name,
        version.department_id.parent_id.name or '',
        employee.department_id.name or '',
        version.contract_date_start or employee._get_first_contract_date() or '',
        employee.job_id.name or '',
        bono14,
        aguinaldo,
        indemnizacion,
        vacaciones,
        bono14 + aguinaldo + indemnizacion + vacaciones,
    ]


def write_rows(sheet, money, start_row, rows):
    row = start_row
    for data_row in rows:
        for col, value in enumerate(data_row):
            if isinstance(value, float):
                sheet.write_number(row, col, value, money)
            else:
                sheet.write(row, col, value)
        row += 1
    return row


class WizardReportePrestacionesLaborales(models.TransientModel):
    _name = 'wizard.reporte.prestaciones.laborales'
    _description = 'Wizard Reporte de Prestaciones Laborales'
    _inherit = ['construtec.nomina.report.wizard.mixin']

    date_start = fields.Date(string='Del', required=True)
    date_end = fields.Date(string='Al', required=True)
    employee_id = fields.Many2many('hr.employee', string='Empleados', required=True)

    def print_xls_reporte_prestaciones_laborales(self):
        self.ensure_one()
        self.check_date()
        payslips = self.env['hr.payslip'].search([
            ('date_from', '>=', self.date_start), ('date_to', '<=', self.date_end),
            ('company_id', '=', self.company_id.id), ('employee_id', 'in', self.employee_id.ids),
            ('state', 'in', ('validated', 'paid')),
        ])
        buffer, workbook = self.new_workbook()
        sheet = workbook.add_worksheet('Prestaciones Laborales')
        bold = workbook.add_format({'bold': True})
        money = workbook.add_format({'num_format': '#,##0.00'})
        for col, header in enumerate(COLUMNS):
            sheet.write(0, col, header, bold)
        write_rows(sheet, money, 1, (prestaciones_row(p) for p in payslips))
        return self.finalize_workbook(buffer, workbook, 'Reporte_Prestaciones_Laborales.xlsx')


class WizardPasivoLaboralConsolidado(models.TransientModel):
    _name = 'wizard.pasivo.laboral.consolidado'
    _description = 'Wizard Pasivo Laboral Consolidado'
    _inherit = ['construtec.nomina.report.wizard.mixin']

    date_start = fields.Date(string='Del', required=True)
    date_end = fields.Date(string='Al', required=True)

    def print_xls_pasivo_laboral_consolidado(self):
        self.ensure_one()
        self.check_date()
        payslips = self.env['hr.payslip'].search([
            ('date_from', '>=', self.date_start), ('date_to', '<=', self.date_end),
            ('company_id', '=', self.company_id.id),
        ])
        buffer, workbook = self.new_workbook()
        sheet = workbook.add_worksheet('Pasivo Laboral Consolidado')
        bold = workbook.add_format({'bold': True})
        money = workbook.add_format({'num_format': '#,##0.00'})
        for col, header in enumerate(COLUMNS):
            sheet.write(0, col, header, bold)
        write_rows(sheet, money, 1, (prestaciones_row(p) for p in payslips))
        return self.finalize_workbook(buffer, workbook, 'Pasivo_Laboral_Consolidado.xlsx')


class WizardPasivoLaboralEmpleado(models.TransientModel):
    _name = 'wizard.pasivo.laboral.empleado'
    _description = 'Wizard Pasivo Laboral Empleado'
    _inherit = ['construtec.nomina.report.wizard.mixin']

    date_start = fields.Date(string='Del', required=True)
    date_end = fields.Date(string='Al', required=True)
    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True)

    def print_xls_pasivo_laboral_empleado(self):
        self.ensure_one()
        self.check_date()
        payslips = self.env['hr.payslip'].search([
            ('date_from', '>=', self.date_start), ('date_to', '<=', self.date_end),
            ('company_id', '=', self.company_id.id), ('employee_id', '=', self.employee_id.id),
        ])
        buffer, workbook = self.new_workbook()
        sheet = workbook.add_worksheet('Pasivo Laboral Empleado')
        bold = workbook.add_format({'bold': True})
        money = workbook.add_format({'num_format': '#,##0.00'})
        for col, header in enumerate(COLUMNS):
            sheet.write(0, col, header, bold)

        totals = [0.0, 0.0, 0.0, 0.0]
        row = 1
        for payslip in payslips:
            data_row = prestaciones_row(payslip)
            for col, value in enumerate(data_row):
                if isinstance(value, float):
                    sheet.write_number(row, col, value, money)
                else:
                    sheet.write(row, col, value)
            for i, key in enumerate(data_row[9:13]):
                totals[i] += key
            row += 1

        sheet.write(row, 4, self.employee_id.name, bold)
        for i, total in enumerate(totals):
            sheet.write_number(row, 9 + i, total, workbook.add_format({'bold': True, 'num_format': '#,##0.00'}))
        sheet.write_number(row, 13, sum(totals), workbook.add_format({'bold': True, 'num_format': '#,##0.00'}))

        return self.finalize_workbook(buffer, workbook, 'Pasivo_Laboral_Empleado.xlsx')
