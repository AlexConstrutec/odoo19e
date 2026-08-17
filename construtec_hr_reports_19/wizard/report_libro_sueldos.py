from odoo import fields, models

DEDUCCION_LEGAL_TEXT_1 = (
    'Libro de Salarios autorizado según Decreto 1441 del Congreso de la República, Código de Trabajo, '
    'Artículo 102, y Acuerdo Ministerial 124-2019 del Ministerio de Trabajo y Previsión Social.')
DEDUCCION_LEGAL_TEXT_2 = 'Guatemala, C.A.'

ROWS_PER_PAGE = 35
COLUMNS = [
    'Nombre', 'Edad', 'Género', 'Nacionalidad', 'Puesto', 'No. Afiliación IGSS', 'DPI',
    'Fecha Inicio Contrato', 'Fecha Fin Contrato', 'No. Pago', 'Del', 'Al',
    'Días Trabajados', 'Horas Ordinarias', 'Horas Extraordinarias',
    'Salario Ordinario', 'Salario Extraordinario', 'Otros Salarios', 'Séptimos y Asuetos', 'Vacaciones',
    'Salario Total', 'Cuota Laboral IGSS', 'Descuentos ISR', 'Otras Deducciones', 'Total Deducciones',
    'Bonificación Anual/Aguinaldo', 'Bonificación Incentivo Decreto 37-2001', 'Devoluciones ISR y Otras',
    'Salario Líquido', 'Firma/Voucher', 'Observaciones',
]


class WizardLibroSueldosSalarios(models.TransientModel):
    _name = 'wizard.libro.sueldos.salarios'
    _description = 'Wizard Libro de Sueldos y Salarios'
    _inherit = ['construtec.nomina.report.wizard.mixin']

    date_start = fields.Date(string='Del', required=True)
    date_end = fields.Date(string='Al', required=True)
    folio = fields.Integer(string='Folio Inicial', required=True, default=1)

    def _horas_extraordinarias(self, payslip):
        struct_name = payslip.struct_id.name or ''
        version = payslip.version_id
        if '100HE' in struct_name:
            vheb = sum(line.total for line in payslip.line_ids if line.code == 'VHEB')
            if version.x_horas_extra_valor > 0 and vheb > 0:
                return vheb / version.x_horas_extra_valor
            return 0.0
        if '100BH' in struct_name:
            horas = sum(
                wd.number_of_hours for wd in payslip.worked_days_line_ids
                if wd.work_entry_type_id.code == 'HORAEXTRA')
            return horas - 60 if horas > 60 else 0.0
        return 0.0

    def _payslip_row(self, payslip, numero_pago):
        employee = payslip.employee_id
        version = payslip.version_id
        codes = {}
        for line in payslip.line_ids:
            codes[line.code] = codes.get(line.code, 0.0) + line.total

        salario_base = codes.get('BASIC', 0.0)
        salario_extra = codes.get('VHEB', 0.0)
        vacaciones = codes.get('VACACPAG', 0.0)
        cuota_igss = codes.get('IGSSLABR', 0.0) + codes.get('CIGSSLAB', 0.0)
        isr = codes.get('ISRASA', 0.0)
        anticipos = codes.get('ANT1', 0.0) + codes.get('ANT2', 0.0) + codes.get('ANT3', 0.0)
        bono_aguinaldo = codes.get('AGUINALDOP', 0.0) + codes.get('BONO14P', 0.0)
        bono_incentivo = sum(codes.get(c, 0.0) for c in
                              ('BONIN', 'BOFIJ', 'BONPRO', 'OTREN', 'MDOA', 'MDOAS', 'BHE', 'MDOALIM'))
        devoluciones = codes.get('DEVISR', 0.0) + codes.get('INDEMP', 0.0)
        dias_trabajados = (payslip.date_to - payslip.date_from).days + 1

        return [
            employee.name,
            employee.edad,
            self.selection_label(employee, 'sex'),
            employee.country_of_birth.name or '',
            employee.job_title or '',
            employee.igss or '',
            employee.identification_id or '',
            version.contract_date_start or employee._get_first_contract_date() or '',
            version.contract_date_end or '',
            numero_pago,
            payslip.date_from.strftime('%d/%m/%Y'),
            payslip.date_to.strftime('%d/%m/%Y'),
            dias_trabajados,
            dias_trabajados * 8,
            self._horas_extraordinarias(payslip),
            salario_base,
            salario_extra,
            0.0,
            0.0,
            vacaciones,
            salario_base + salario_extra + vacaciones,
            cuota_igss,
            isr,
            anticipos,
            anticipos + cuota_igss + isr,
            bono_aguinaldo,
            bono_incentivo,
            devoluciones,
            codes.get('NET', 0.0),
            payslip.payment_ids[:1].memo or '',
            '',
        ]

    def print_xls_libro_sueldos_salarios(self):
        self.ensure_one()
        self.check_date()
        payslips = self.env['hr.payslip'].search([
            ('date_from', '>=', self.date_start), ('date_to', '<=', self.date_end),
            ('company_id', '=', self.company_id.id), ('state', 'in', ('validated', 'paid')),
        ], order='employee_id, date_from asc')

        buffer, workbook = self.new_workbook()
        sheet = workbook.add_worksheet('Libro de Sueldos y Salarios')
        sheet.set_landscape()
        sheet.set_paper(5)
        sheet.set_margins(left=0.7, right=0.7, top=0.7, bottom=0.7)
        bold = workbook.add_format({'bold': True})
        header_format = workbook.add_format({'bold': True, 'text_wrap': True, 'border': 1})
        money = workbook.add_format({'num_format': '#,##0.00'})

        folio = self.folio
        row = 0
        current_employee = None
        numero_pago = 0

        def write_page_header(row):
            sheet.merge_range(row, 0, row, len(COLUMNS) - 1, f'Folio No. {folio}', bold)
            row += 1
            sheet.merge_range(row, 0, row, len(COLUMNS) - 1, self.company_id.name, bold)
            row += 1
            sheet.merge_range(row, 0, row, len(COLUMNS) - 1, f'NIT: {self.company_id.vat or ""}')
            row += 1
            sheet.merge_range(row, 0, row, len(COLUMNS) - 1, DEDUCCION_LEGAL_TEXT_1)
            row += 1
            sheet.merge_range(row, 0, row, len(COLUMNS) - 1, DEDUCCION_LEGAL_TEXT_2)
            row += 1
            for col, header in enumerate(COLUMNS):
                sheet.write(row, col, header, header_format)
            return row + 1

        row = write_page_header(row)
        rows_on_page = 0

        for payslip in payslips:
            if payslip.employee_id != current_employee:
                current_employee = payslip.employee_id
                numero_pago = 0
            numero_pago += 1

            if rows_on_page >= ROWS_PER_PAGE:
                folio += 1
                row = write_page_header(row)
                rows_on_page = 0

            data_row = self._payslip_row(payslip, numero_pago)
            for col, value in enumerate(data_row):
                if isinstance(value, float):
                    sheet.write_number(row, col, value, money)
                else:
                    sheet.write(row, col, value)
            row += 1
            rows_on_page += 1

        return self.finalize_workbook(buffer, workbook, 'Libro_Sueldos_Salarios.xlsx')
