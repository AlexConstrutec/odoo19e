from odoo import fields, models

CERTIFICATE_CODE = {
    'other': '1', 'graduate': '7', 'bachelor': '10', 'master': '12', 'doctor': '13',
}
MARITAL_CODE = {'single': '1', 'divorced': '1', 'widower': '1', 'married': '2', 'cohabitant': '3'}
SEX_CODE = {'male': '1', 'female': '2'}

COLUMNS = [
    'Número de empleado', 'Primer nombre', 'Segundo nombre', 'Tercer nombre', 'Primer apellido',
    'Segundo apellido', 'Apellido de Casada', 'Nacionalidad', 'Tipo de discapacidad', 'Estado civil',
    'Documento identificación (DPI, Pasaporte u otro)', 'Número de documento', 'País de origen',
    'Número de expediente del permiso de extranjero', 'Lugar de nacimiento (municipio)',
    'Número de Identificación Tributaria (NIT)', 'Número de afiliación al IGSS', 'Sexo', 'Fecha de nacimiento',
    'Nivel académico más alto alcanzado', 'Titulo o diploma (profesión)', 'Pueblo de pertenencia',
    'Comunidad Lingüística', 'Cantidad de hijos', 'Temporalidad del contrato', 'Tipo de contrato',
    'Fecha de inicio de labores', 'Fecha de reinicio de labores', 'Fecha de finalización de labores',
    'Ocupación (Puesto)', 'Jornada de Trabajo', 'Días laborados en el año', 'Salario mensual nominal',
    'Salario mensual nominal interno', 'Salario anual nominal', 'Bonificación Decreto 78-89 (Q.250.00)',
    'Total horas extras anuales', 'Valor de la hora extra', 'Monto Aguinaldo Decreto 76-78',
    'Monto Bono 14 Decreto 42-92', 'Retribución por comisiones', 'Viáticos', 'Bonificaciones adicionales',
    'Retribución por vacaciones', 'Retribución por indemnización (Artículo 82 Código de Trabajo)', 'Sucursal',
    'Del', 'Hasta',
]
BONIFICACION_ADICIONAL_CODES = {
    'MDOA', 'BHE', 'BONIN', 'BOFIJ', 'BONPRO', 'MDOP', 'MDOAS', 'MDOALIM', 'OTREN', 'OTRGRATIF'}


class WizardInformeEmpleador(models.TransientModel):
    _name = 'wizard.informe.empleador'
    _description = 'Wizard Informe del Empleador'
    _inherit = ['construtec.nomina.report.wizard.mixin']

    date_start = fields.Date(string='Del', required=True)
    date_end = fields.Date(string='Al', required=True)

    def _fechas_inspeccion(self, employee):
        """Determina fecha de inicio, reinicio y fin de labores registradas ante la Inspección de Trabajo,
        a partir de las versiones (ex-contratos) del empleado marcadas con registrar_fecha_inspeccion."""
        versions = self.env['hr.version'].search([
            ('employee_id', '=', employee.id), ('company_id', '=', self.company_id.id),
        ], order='date_version desc').filtered('contract_date_start')

        primera = segunda = tercera = ''

        for version in versions:
            if version.registrar_fecha_inspeccion and version.contract_date_start.year <= self.date_start.year:
                primera = version.contract_date_start.strftime('%d-%m-%Y')
                break

        if primera:
            for version in versions:
                if (version.registrar_fecha_inspeccion and version.contract_date_start.year <= self.date_start.year
                        and version.contract_date_start.strftime('%d-%m-%Y') != primera):
                    segunda, primera = primera, version.contract_date_start.strftime('%d-%m-%Y')
                    break

        for version in versions:
            if version.contract_date_end and version.contract_date_end.year <= self.date_end.year:
                tercera = version.contract_date_end.strftime('%d-%m-%Y')
                break
            if not version.contract_date_end and version.contract_date_start.year <= self.date_end.year:
                tercera = ''
                break

        if segunda:
            for version in versions:
                if not version.contract_date_end and version.contract_date_start.year <= self.date_end.year:
                    continue
                if version.contract_date_end and version.contract_date_end.year <= self.date_end.year:
                    tercera = version.contract_date_end.strftime('%d-%m-%Y')
                    break

        return primera, segunda, tercera

    def _employee_row(self, employee):
        version = employee.version_id
        primera, segunda, tercera = self._fechas_inspeccion(employee)

        payslips = self.env['hr.payslip'].search([
            ('employee_id', '=', employee.id), ('date_to', '>=', self.date_start),
            ('date_to', '<=', self.date_end), ('company_id', '=', self.company_id.id),
        ])
        salario_base = horas_extras = aguinaldo = bono14 = bonif_adicional = vacaciones = indemnizacion = 0.0
        for payslip in payslips:
            salario_base += payslip.basic_wage
            for line in payslip.line_ids:
                if line.code == 'VHEB':
                    horas_extras += line.total
                elif line.code == 'AGUINALDOP':
                    aguinaldo += line.total
                elif line.code == 'BONO14P':
                    bono14 += line.total
                elif line.code in BONIFICACION_ADICIONAL_CODES:
                    bonif_adicional += line.total
                elif line.code == 'VACACPAG':
                    vacaciones += line.total
                elif line.code == 'INDEMP':
                    indemnizacion += line.total

        dias_laborados = self.env['hr.dias.laborados.mes'].get_dias_laborados(
            version.contract_date_start, version.contract_date_end)
        pais = 'GTM'

        return [
            employee.registration_number or '',
            employee.primer_nombre or '', employee.segundo_nombre or '', employee.tercer_nombre or '',
            employee.primer_apellido or '', employee.segundo_apellido or '', employee.apellido_casada or '',
            pais,
            employee.discapacidad or '1',
            MARITAL_CODE.get(employee.marital, '1'),
            '1' if employee.identification_id else '2',
            employee.identification_id or '',
            pais,
            '',
            employee.municipio_id.code or '',
            employee.nit or '',
            employee.igss or '',
            SEX_CODE.get(employee.sex, '1'),
            employee.birthday.strftime('%d-%m-%Y') if employee.birthday else '',
            CERTIFICATE_CODE.get(employee.certificate, employee.certificate or ''),
            employee.study_field or '',
            1,
            10,
            employee.children or 0,
            version.contract_type_id.id or '',
            2,
            primera,
            segunda,
            tercera,
            employee.ocupacion_puesto_id.code or '',
            employee.jornada_trabajo or '',
            dias_laborados,
            version.wage or '',
            version.wage or '',
            abs(salario_base),
            0,
            abs(horas_extras),
            version.horas_extra_valor or '',
            abs(aguinaldo),
            abs(bono14),
            0,
            0,
            abs(bonif_adicional),
            abs(vacaciones),
            abs(indemnizacion),
            1,
            self.date_start.strftime('%d-%m-%Y'),
            self.date_end.strftime('%d-%m-%Y'),
        ]

    def print_xls_informe_empleador(self):
        self.ensure_one()
        self.check_date()
        employees = self.env['hr.employee'].with_context(active_test=False).search(
            [('company_id', '=', self.company_id.id)])

        buffer, workbook = self.new_workbook()
        sheet = workbook.add_worksheet('Informe del Empleador')
        header_format = workbook.add_format({
            'bold': True, 'align': 'center', 'valign': 'vcenter', 'font_size': 10, 'border': 1,
            'bg_color': '#DDEBF7', 'text_wrap': True})
        for col, header in enumerate(COLUMNS):
            sheet.write(0, col, header, header_format)
            sheet.set_column(col, col, 12)

        row = 1
        for employee in employees:
            for col, value in enumerate(self._employee_row(employee)):
                sheet.write(row, col, value)
            row += 1

        return self.finalize_workbook(buffer, workbook, 'Informe_del_Empleador.xlsx')
