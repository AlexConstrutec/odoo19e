from collections import defaultdict

from odoo import fields, models

COLUMNS = [
    'Inicio de contrato', 'Fin de contrato', 'No. Afiliación', 'Nombres y Apellidos', 'Salario Base',
    'Horas Extras', 'Vacaciones', 'Total', 'IGSS Laboral', 'Complemento IGSS Laboral', 'IGSS Patronal',
    'Complemento IGSS Patronal', 'IRTRA', 'INTECAP', 'Departamento', 'Área', 'Puesto', 'Tiempo de Contrato',
    'Cantidad de Días laborados en el mes', 'Cantidad horas laborados del mes',
]


class WizardReportePlanillaIGSS(models.TransientModel):
    _name = 'wizard.reporte.planilla.igss'
    _description = 'Wizard Reporte Planilla IGSS'
    _inherit = ['construtec.nomina.report.wizard.mixin']

    date_start = fields.Date(string='Del', required=True)
    date_end = fields.Date(string='Al', required=True)

    def print_xls_reporte_planilla_igss(self):
        self.ensure_one()
        self.check_date()
        payslips = self.env['hr.payslip'].search([
            ('date_from', '>=', self.date_start), ('date_to', '<=', self.date_end),
            ('company_id', '=', self.company_id.id),
        ])
        payslips = payslips.filtered(lambda p: 'PRESTACIONES' not in (p.struct_id.name or '').upper())
        by_employee = defaultdict(lambda: self.env['hr.payslip'])
        for payslip in payslips:
            by_employee[payslip.employee_id] |= payslip

        buffer, workbook = self.new_workbook()
        sheet = workbook.add_worksheet('Planilla IGSS')
        bold = workbook.add_format({'bold': True})
        money = workbook.add_format({'num_format': '#,##0.00'})
        sheet.merge_range(0, 0, 0, len(COLUMNS) - 1, 'Planilla IGSS', bold)
        sheet.merge_range(1, 0, 1, len(COLUMNS) - 1, self.company_id.name, bold)
        sheet.merge_range(2, 0, 2, len(COLUMNS) - 1,
                           f'Del {self.date_start.strftime("%d/%m/%Y")} al {self.date_end.strftime("%d/%m/%Y")}')
        for col, header in enumerate(COLUMNS):
            sheet.write(3, col, header, bold)

        row = 4
        for employee in sorted(by_employee, key=lambda e: e.name):
            slips = by_employee[employee]
            horas_extras = vacaciones = igss_lab = c_igss_lab = igss_pat = c_igss_pat = irtra = intecap = 0.0
            salario_base = 0.0
            dias = 0
            tiempo_contrato = ''
            for payslip in slips:
                for line in payslip.line_ids:
                    if line.code == 'VHEB':
                        horas_extras += line.total
                    elif line.code == 'VACACPAG':
                        vacaciones += line.total
                    elif line.code == 'IGSSLABR':
                        igss_lab += line.total
                    elif line.code == 'CIGSSLAB':
                        c_igss_lab += line.total
                    elif line.code == 'IGSS PAT':
                        igss_pat += line.total
                    elif line.code == 'CIGSSPAT':
                        c_igss_pat += line.total
                    elif line.code == 'IRTRA':
                        irtra += line.total
                    elif line.code == 'INTECAP':
                        intecap += line.total
                salario_base += payslip.basic_wage
                dias += (payslip.date_to - payslip.date_from).days + 1
                tiempo_contrato = self.selection_label(payslip.version_id, 'tiempo_contrato')

            version = slips[:1].version_id
            data_row = [
                version.contract_date_start or '',
                version.contract_date_end or '',
                employee.igss or '',
                employee.name,
                salario_base,
                horas_extras,
                vacaciones,
                salario_base + horas_extras + vacaciones,
                abs(igss_lab), abs(c_igss_lab), abs(igss_pat), abs(c_igss_pat), abs(irtra), abs(intecap),
                version.department_id.parent_id.name or '',
                employee.department_id.name or '',
                employee.job_id.name or '',
                tiempo_contrato,
                dias,
                dias * 8,
            ]
            for col, value in enumerate(data_row):
                if isinstance(value, float):
                    sheet.write_number(row, col, value, money)
                else:
                    sheet.write(row, col, value)
            row += 1

        return self.finalize_workbook(buffer, workbook, 'Reporte_Planilla_IGSS.xlsx')
