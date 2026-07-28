from odoo import fields, models

OTRAS_BONIF_CODES = {'BOFIJ', 'MDOA', 'MDOAS', 'MDOP', 'BONPRO', 'MDOALIM', 'BHE', 'OTREN'}
COLUMNS = [
    'Código', 'NIT Empleado', 'Nombre Empleado', 'Puesto', 'Fecha de Ingreso', 'Fecha de Finalización',
    'Sumatoria total sueldo Base', 'Sumatoria total de Horas Extras', 'Sumatoria total de Bonificación Incentivo',
    'Sumatoria total de Otras Bonificaciones', 'Sumatoria total de Aguinaldo', 'Sumatoria total de Bono 14',
    'Sumatoria total de Gratificación', 'Sumatoria total de Indemnización', 'Sumatoria total de Vacaciones',
    'Sumatoria total de Cuota IGSS', 'Monto Ultima Retención Realizada',
]


class WizardReporteLiquidacionEmpleados(models.TransientModel):
    _name = 'wizard.reporte.liquidacion.empleados'
    _description = 'Wizard Reporte Liquidación Empleados'
    _inherit = ['construtec.nomina.report.wizard.mixin']

    date_start = fields.Date(string='Del', required=True)
    date_end = fields.Date(string='Al', required=True)
    employee_id = fields.Many2many(
        'hr.employee', string='Empleados', required=True,
        domain=[('version_id.estado_contrato.name', 'not in', ['Proveedores', 'Practicante'])],
        context={'active_test': False})

    def _employee_row(self, employee, payslips):
        ultimo_mes = max(payslips.mapped(lambda p: p.date_from.month), default=0)
        sueldo_base = horas_extras = bon_incentivo = otras_bonif = 0.0
        aguinaldo = bono14 = gratificacion = indemnizacion = vacaciones = cuota_igss = 0.0
        isr_asalariado = devolucion_isr = 0.0

        for payslip in payslips:
            for line in payslip.line_ids:
                if line.code == 'BASIC':
                    sueldo_base += line.total
                elif line.code == 'VHEB':
                    horas_extras += line.total
                elif line.code == 'BONIN':
                    bon_incentivo += line.total
                elif line.code in OTRAS_BONIF_CODES:
                    otras_bonif += line.total
                elif line.code == 'AGUINALDOP':
                    aguinaldo += line.total
                elif line.code == 'BONO14P':
                    bono14 += line.total
                elif line.code == 'OTRGRATIF':
                    gratificacion += line.total
                elif line.code == 'INDEMP':
                    indemnizacion += line.total
                elif line.code == 'VACACPAG':
                    vacaciones += line.total
                elif line.code == 'IGSSLABR':
                    cuota_igss += abs(line.total)
                elif line.code == 'ISRASA' and payslip.date_from.month == ultimo_mes:
                    isr_asalariado += abs(line.total)
                elif line.code == 'DEVISR' and payslip.date_from.month == ultimo_mes:
                    devolucion_isr += abs(line.total)

        version = employee.version_id
        return [
            employee.registration_number or '',
            employee.work_contact_id.vat or '',
            employee.name,
            employee.job_id.name or '',
            employee._get_first_contract_date() and employee._get_first_contract_date().strftime('%d-%m-%Y') or '',
            version.contract_date_end.strftime('%d-%m-%Y') if version.contract_date_end else '',
            abs(sueldo_base), abs(horas_extras), abs(bon_incentivo), abs(otras_bonif),
            abs(aguinaldo), abs(bono14), abs(gratificacion), abs(indemnizacion), abs(vacaciones),
            abs(cuota_igss), isr_asalariado - devolucion_isr,
        ]

    def print_xls_reporte_liquidacion_empleados(self):
        self.ensure_one()
        self.check_date()
        employees = self.env['hr.employee'].with_context(active_test=False).search(
            [('company_id', '=', self.company_id.id), ('id', 'in', self.employee_id.ids)])

        buffer, workbook = self.new_workbook()
        sheet = workbook.add_worksheet('Reporte Liquidación Empleados')
        bold = workbook.add_format({'bold': True})
        money = workbook.add_format({'num_format': '#,##0.00'})
        for col, header in enumerate(COLUMNS):
            sheet.write(0, col, header, bold)

        row = 1
        for employee in employees:
            payslips = self.env['hr.payslip'].search([
                ('date_to', '>=', self.date_start), ('date_to', '<=', self.date_end),
                ('company_id', '=', self.company_id.id), ('employee_id', '=', employee.id),
            ], order='date_from desc')
            if not payslips:
                continue
            for col, value in enumerate(self._employee_row(employee, payslips)):
                if isinstance(value, float):
                    sheet.write_number(row, col, value, money)
                else:
                    sheet.write(row, col, value)
            row += 1

        return self.finalize_workbook(buffer, workbook, 'Reporte_Liquidacion_Empleados.xlsx')
