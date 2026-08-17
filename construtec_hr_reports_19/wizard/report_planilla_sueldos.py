from odoo import fields, models

COLUMNS = [
    'Mes', 'Código de Planilla', 'Departamento', 'Área', 'Nombre del empleado', 'Cod. de empleado',
    'Fecha de ingreso', 'Fecha fin Contrato', 'Puesto', 'Días', 'Salario base', 'Bonificación Incentivo',
    'Bonificación Fija', 'Bonificación por ajuste', 'Bonificación por asueto', 'Bonificación por productividad',
    'Alimentación', 'Horas Extras', 'Bonificación por Horas', 'Bonificaciones Extras', 'Salario devengado',
    'Cuota Laboral IGSS', 'Complemento Cuota Laboral IGSS', 'ISR Asalariados', 'Anticipo 1', 'Anticipo 2',
    'Anticipo 3', 'Total deducciones', 'Salario líquido', 'Cuota Patronal', 'Complemento Cuota Patronal',
    'Irtra', 'Intecap', 'Bono anual Reserva', 'Aguinaldo Reserva', 'Indemnización Reserva', 'Vacaciones Reserva',
    'Total Reserva Para Prestaciones', 'Gratificación', 'Devolución de ISR', 'Bono Anual Pago', 'Aguinaldo Pago',
    'Indemnización Pago', 'Vacaciones Pago', 'Líquido a recibir', 'Banco a depositar', 'Cuenta a Depositar',
    'Observaciones', 'Centro de Costo', 'Tipo Facturación',
    'Fecha desde Nómina', 'Fecha hasta Nómina',
]


class WizardPlanillaSueldos(models.TransientModel):
    _name = 'wizard.planilla.sueldos'
    _description = 'Wizard Planilla de Sueldos'
    _inherit = ['construtec.nomina.report.wizard.mixin']

    planillas = fields.Many2many('hr.payslip.run', string='Lotes de Nómina', required=True)

    def _payslip_row(self, payslip):
        employee = payslip.employee_id
        version = payslip.version_id
        codes = {}
        for line in payslip.line_ids:
            codes[line.code] = codes.get(line.code, 0.0) + line.total

        bon_productividad = codes.get('MDOP', 0.0) + codes.get('BONPRO', 0.0)
        reserva_bono14 = codes.get('BONO14', 0.0)
        reserva_aguinaldo = codes.get('AGUINALDO', 0.0)
        reserva_indemnizacion = codes.get('INDM', 0.0)
        reserva_vacaciones = codes.get('VACAC', 0.0)
        reserva_total = reserva_bono14 + reserva_aguinaldo + reserva_indemnizacion + reserva_vacaciones

        analytic = self.analytic_account(version.analytic_distribution)
        centro_costo = f'[{analytic.code}] {analytic.name}' if analytic and analytic.code and analytic.name else ''
        plan_name = analytic.plan_id.name if analytic else ''
        tipo_facturacion = '' if plan_name == 'Default' else plan_name

        bank_account = employee.primary_bank_account_id

        return [
            payslip.date_from.strftime('%B'),
            payslip.payslip_run_id.name or '',
            version.department_id.parent_id.name or '',
            employee.department_id.name or '',
            employee.name,
            employee.codigo_empleado or '',
            version.contract_date_start or employee._get_first_contract_date() or '',
            version.contract_date_end or '',
            employee.job_id.name or '',
            (payslip.date_to - payslip.date_from).days + 1,
            codes.get('BASIC', 0.0),
            codes.get('BONIN', 0.0),
            codes.get('BOFIJ', 0.0),
            codes.get('MDOA', 0.0),
            codes.get('MDOAS', 0.0),
            bon_productividad,
            codes.get('MDOALIM', 0.0),
            codes.get('VHEB', 0.0),
            codes.get('BHE', 0.0),
            codes.get('OTREN', 0.0),
            codes.get('GROSS', 0.0),
            codes.get('IGSSLABR', 0.0),
            codes.get('CIGSSLAB', 0.0),
            codes.get('ISRASA', 0.0),
            codes.get('ANT1', 0.0),
            codes.get('ANT2', 0.0),
            codes.get('ANT3', 0.0),
            codes.get('DEDU', 0.0),
            codes.get('NET', 0.0),
            codes.get('IGSS PAT', 0.0),
            codes.get('CIGSSPAT', 0.0),
            codes.get('IRTRA', 0.0),
            codes.get('INTECAP', 0.0),
            reserva_bono14,
            reserva_aguinaldo,
            reserva_indemnizacion,
            reserva_vacaciones,
            reserva_total,
            codes.get('OTRGRATIF', 0.0),
            codes.get('DEVISR', 0.0),
            codes.get('BONO14P', 0.0),
            codes.get('AGUINALDOP', 0.0),
            codes.get('INDEMP', 0.0),
            codes.get('VACACPAG', 0.0),
            codes.get('NET', 0.0),
            bank_account.bank_id.name or '' if bank_account else '',
            bank_account.acc_number or '' if bank_account else '',
            '',
            centro_costo,
            tipo_facturacion,
            payslip.date_from.strftime('%d/%m/%Y'),
            payslip.date_to.strftime('%d/%m/%Y'),
        ]

    def print_xls_planilla_sueldos(self):
        self.ensure_one()
        runs = self.env['hr.payslip.run'].search([
            ('id', 'in', self.planillas.ids), ('company_id', '=', self.company_id.id)])
        payslips = runs.mapped('slip_ids')

        buffer, workbook = self.new_workbook()
        sheet = workbook.add_worksheet('Planilla de Sueldos')
        bold = workbook.add_format({'bold': True})
        money = workbook.add_format({'num_format': '#,##0.00'})
        for col, header in enumerate(COLUMNS):
            sheet.write(0, col, header, bold)

        row = 1
        for payslip in payslips:
            for col, value in enumerate(self._payslip_row(payslip)):
                if isinstance(value, float):
                    sheet.write_number(row, col, value, money)
                else:
                    sheet.write(row, col, value)
            row += 1

        return self.finalize_workbook(buffer, workbook, 'Planilla_Sueldos.xlsx')
