import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)

# Verificado 2026-09-18 contra "Formato_Informe Empleados.xlsx" (el archivo real descargado de
# MITRAB), hoja "Nivel_Educativo" (13 códigos: 1=Ninguno...13=Doctorado). `certificate` en
# `construtec_hr_employee_19` (Enterprise) y en `construtec_account_payment_order_19`
# (Community) YA está sobrescrito con esos 13 niveles exactos (`NIVEL_ACADEMICO`,
# `hr_employee_selections.py`), reutilizando a propósito las claves nativas de Odoo
# ('other'/'graduate'/'bachelor'/'master'/'doctor') donde coinciden con un nivel MITRAB y usando
# el código MITRAB tal cual como clave para los niveles que Odoo no tenía (ej. '3' = Primaria
# Completa = código MITRAB 3). Por eso este diccionario solo necesita traducir las 5 claves
# nativas reutilizadas - cualquier otro valor de `certificate` (ej. '3', '8', '11') YA ES el
# código MITRAB, se manda tal cual (ver el `.get(employee.certificate, employee.certificate or '')`
# en `_employee_row()`).
CERTIFICATE_CODE = {
    'other': '1', 'graduate': '7', 'bachelor': '10', 'master': '12', 'doctor': '13',
}
MARITAL_CODE = {'single': '1', 'divorced': '1', 'widower': '1', 'married': '2', 'cohabitant': '3'}
SEX_CODE = {'male': '1', 'female': '2'}

# Catálogo "Nacionalidad_país" real de MITRAB (verificado 2026-09-18 contra
# "Formato_Informe Empleados.xlsx"): son códigos ISO 3166-1 alpha-3 estándar (AFG, ALB, DEU...),
# confirmando que el enfoque ya usado aquí (alpha-3) era correcto - lo que faltaba era cobertura
# completa (antes solo ~20 países). `res.country` no tiene un campo alpha-3 nativo en este Odoo
# (solo el `code` ISO alpha-2) - esta es la tabla ISO 3166-1 alpha-2→alpha-3 completa, no
# depende de traducciones de nombre de país. Un código no listado aquí (territorio/entidad rara
# que Odoo sí tenga pero no esté en este estándar) cae a su `code` alpha-2 tal cual.
COUNTRY_ALPHA3 = {
    'AD': 'AND', 'AE': 'ARE', 'AF': 'AFG', 'AG': 'ATG', 'AI': 'AIA', 'AL': 'ALB', 'AM': 'ARM',
    'AO': 'AGO', 'AQ': 'ATA', 'AR': 'ARG', 'AS': 'ASM', 'AT': 'AUT', 'AU': 'AUS', 'AW': 'ABW',
    'AX': 'ALA', 'AZ': 'AZE', 'BA': 'BIH', 'BB': 'BRB', 'BD': 'BGD', 'BE': 'BEL', 'BF': 'BFA',
    'BG': 'BGR', 'BH': 'BHR', 'BI': 'BDI', 'BJ': 'BEN', 'BL': 'BLM', 'BM': 'BMU', 'BN': 'BRN',
    'BO': 'BOL', 'BQ': 'BES', 'BR': 'BRA', 'BS': 'BHS', 'BT': 'BTN', 'BV': 'BVT', 'BW': 'BWA',
    'BY': 'BLR', 'BZ': 'BLZ', 'CA': 'CAN', 'CC': 'CCK', 'CD': 'COD', 'CF': 'CAF', 'CG': 'COG',
    'CH': 'CHE', 'CI': 'CIV', 'CK': 'COK', 'CL': 'CHL', 'CM': 'CMR', 'CN': 'CHN', 'CO': 'COL',
    'CR': 'CRI', 'CU': 'CUB', 'CV': 'CPV', 'CW': 'CUW', 'CX': 'CXR', 'CY': 'CYP', 'CZ': 'CZE',
    'DE': 'DEU', 'DJ': 'DJI', 'DK': 'DNK', 'DM': 'DMA', 'DO': 'DOM', 'DZ': 'DZA', 'EC': 'ECU',
    'EE': 'EST', 'EG': 'EGY', 'EH': 'ESH', 'ER': 'ERI', 'ES': 'ESP', 'ET': 'ETH', 'FI': 'FIN',
    'FJ': 'FJI', 'FK': 'FLK', 'FM': 'FSM', 'FO': 'FRO', 'FR': 'FRA', 'GA': 'GAB', 'GB': 'GBR',
    'GD': 'GRD', 'GE': 'GEO', 'GF': 'GUF', 'GG': 'GGY', 'GH': 'GHA', 'GI': 'GIB', 'GL': 'GRL',
    'GM': 'GMB', 'GN': 'GIN', 'GP': 'GLP', 'GQ': 'GNQ', 'GR': 'GRC', 'GS': 'SGS', 'GT': 'GTM',
    'GU': 'GUM', 'GW': 'GNB', 'GY': 'GUY', 'HK': 'HKG', 'HM': 'HMD', 'HN': 'HND', 'HR': 'HRV',
    'HT': 'HTI', 'HU': 'HUN', 'ID': 'IDN', 'IE': 'IRL', 'IL': 'ISR', 'IM': 'IMN', 'IN': 'IND',
    'IO': 'IOT', 'IQ': 'IRQ', 'IR': 'IRN', 'IS': 'ISL', 'IT': 'ITA', 'JE': 'JEY', 'JM': 'JAM',
    'JO': 'JOR', 'JP': 'JPN', 'KE': 'KEN', 'KG': 'KGZ', 'KH': 'KHM', 'KI': 'KIR', 'KM': 'COM',
    'KN': 'KNA', 'KP': 'PRK', 'KR': 'KOR', 'KW': 'KWT', 'KY': 'CYM', 'KZ': 'KAZ', 'LA': 'LAO',
    'LB': 'LBN', 'LC': 'LCA', 'LI': 'LIE', 'LK': 'LKA', 'LR': 'LBR', 'LS': 'LSO', 'LT': 'LTU',
    'LU': 'LUX', 'LV': 'LVA', 'LY': 'LBY', 'MA': 'MAR', 'MC': 'MCO', 'MD': 'MDA', 'ME': 'MNE',
    'MF': 'MAF', 'MG': 'MDG', 'MH': 'MHL', 'MK': 'MKD', 'ML': 'MLI', 'MM': 'MMR', 'MN': 'MNG',
    'MO': 'MAC', 'MP': 'MNP', 'MQ': 'MTQ', 'MR': 'MRT', 'MS': 'MSR', 'MT': 'MLT', 'MU': 'MUS',
    'MV': 'MDV', 'MW': 'MWI', 'MX': 'MEX', 'MY': 'MYS', 'MZ': 'MOZ', 'NA': 'NAM', 'NC': 'NCL',
    'NE': 'NER', 'NF': 'NFK', 'NG': 'NGA', 'NI': 'NIC', 'NL': 'NLD', 'NO': 'NOR', 'NP': 'NPL',
    'NR': 'NRU', 'NU': 'NIU', 'NZ': 'NZL', 'OM': 'OMN', 'PA': 'PAN', 'PE': 'PER', 'PF': 'PYF',
    'PG': 'PNG', 'PH': 'PHL', 'PK': 'PAK', 'PL': 'POL', 'PM': 'SPM', 'PN': 'PCN', 'PR': 'PRI',
    'PS': 'PSE', 'PT': 'PRT', 'PW': 'PLW', 'PY': 'PRY', 'QA': 'QAT', 'RE': 'REU',
    # 'ROM', no 'ROU': el catálogo de MITRAB usa el código alpha-3 viejo (pre-2002) para Rumania,
    # no el estándar ISO 3166-1 actual - confirmado contra la hoja "Nacionalidad_país" real.
    'RO': 'ROM',
    'RS': 'SRB', 'RU': 'RUS', 'RW': 'RWA', 'SA': 'SAU', 'SB': 'SLB', 'SC': 'SYC', 'SD': 'SDN',
    'SE': 'SWE', 'SG': 'SGP', 'SH': 'SHN', 'SI': 'SVN', 'SJ': 'SJM', 'SK': 'SVK', 'SL': 'SLE',
    'SM': 'SMR', 'SN': 'SEN', 'SO': 'SOM', 'SR': 'SUR', 'SS': 'SSD', 'ST': 'STP', 'SV': 'SLV',
    'SX': 'SXM', 'SY': 'SYR', 'SZ': 'SWZ', 'TC': 'TCA', 'TD': 'TCD', 'TF': 'ATF', 'TG': 'TGO',
    'TH': 'THA', 'TJ': 'TJK', 'TK': 'TKL', 'TL': 'TLS', 'TM': 'TKM', 'TN': 'TUN', 'TO': 'TON',
    'TR': 'TUR', 'TT': 'TTO', 'TV': 'TUV', 'TW': 'TWN', 'TZ': 'TZA', 'UA': 'UKR', 'UG': 'UGA',
    'UM': 'UMI', 'US': 'USA', 'UY': 'URY', 'UZ': 'UZB', 'VA': 'VAT', 'VC': 'VCT', 'VE': 'VEN',
    'VG': 'VGB', 'VI': 'VIR', 'VN': 'VNM', 'VU': 'VUT', 'WF': 'WLF', 'WS': 'WSM', 'YE': 'YEM',
    'YT': 'MYT', 'ZA': 'ZAF', 'ZM': 'ZMB', 'ZW': 'ZWE',
}


def _country_code_3(country):
    if not country:
        return 'GTM'
    return COUNTRY_ALPHA3.get(country.code, country.code or 'GTM')


# Catálogo real "Doc_identificación" del formato de MITRAB: 1=DPI, 2=Certificado de
# Nacimiento, 3=Pasaporte. Antes de esta pasada, el wizard nunca mandaba el código 3
# (Pasaporte) - solo distinguía DPI presente (1) vs ausente (2, "Certificado de
# Nacimiento" a secas, aunque el empleado tuviera pasaporte). `passport_id` es un
# campo nativo de `hr.version` (delegado a `hr.employee`) - se usa aquí como segunda
# opción antes de caer al último recurso.
def _doc_identificacion_code(employee):
    if employee.identification_id:
        return '1'
    if employee.passport_id:
        return '3'
    return '2'


# Catálogo real "Temporalidad_contrato" de MITRAB: 1=Indefinido, 2=Definido, 3=Por obra
# determinada, 4=Aprendiz (tiempo indefinido), 5=Aprendiz (tiempo definido). Antes de esta
# pasada, el wizard mandaba `contract_type_id.id` - el ID interno de base de datos del
# registro `hr.contract.type` de Odoo, no un código MITRAB (ver CLAUDE.md, "Bugs reales sin
# corregir" del 2026-09-17). Mapeo por NOMBRE (`hr.contract.type.name`), no por id - el
# nombre de este catálogo no participa en ninguna condición de Odoo para esta empresa (las
# únicas localizaciones stock que leen `contract_type_id.name`/`.code` son l10n_ch/l10n_mx,
# ninguna instalada aquí), así que es seguro priorizar que el código refleje lo que MITRAB
# espera. Cubre los nombres de catálogo estándar de Odoo (de fábrica, en inglés) y sus
# equivalentes en español, por si la empresa los tradujo/renombró - un nombre que no
# aparezca aquí cae a '1' (Indefinido, el caso más común en Guatemala) y queda registrado
# en el log para revisión manual, en vez de adivinar en silencio.
CONTRACT_TEMPORALIDAD_APRENDIZ_KEYWORDS = ('aprendiz', 'apprentice')
CONTRACT_TEMPORALIDAD_CODE = {
    'permanent': '1', 'indefinido': '1', 'fijo': '1',
    'temporary': '2', 'temporal': '2', 'definido': '2',
    'interim': '3', 'seasonal': '3', 'eventual': '3',
    'por obra determinada': '3', 'obra determinada': '3', 'determinado': '3',
}


def _temporalidad_contrato_code(version):
    contract_type = version.contract_type_id
    if not contract_type:
        return '1'
    name = (contract_type.name or '').strip().lower()
    if any(keyword in name for keyword in CONTRACT_TEMPORALIDAD_APRENDIZ_KEYWORDS):
        return '5' if version.contract_date_end else '4'
    code = CONTRACT_TEMPORALIDAD_CODE.get(name)
    if code:
        return code
    _logger.warning(
        "Informe del Empleador: el tipo de contrato %r no tiene mapeo a un código MITRAB "
        "de Temporalidad del contrato - se usó '1' (Indefinido) por default. Agregarlo a "
        "CONTRACT_TEMPORALIDAD_CODE en report_informe_empleador.py.", contract_type.name)
    return '1'

COLUMNS = [
    'Número de empleado', 'Primer nombre', 'Segundo nombre', 'Tercer nombre', 'Primer apellido',
    'Segundo apellido', 'Apellido de Casada', 'Nacionalidad', 'Tipo de discapacidad', 'Estado civil',
    'Documento identificación (DPI, Pasaporte u otro)', 'Número de documento', 'País de origen',
    'Número de expediente del permiso de extranjero', 'Lugar de nacimiento (municipio)',
    'Número de Identificación Tributaria (NIT)', 'Número de afiliación al IGSS', 'Sexo', 'Fecha de nacimiento',
    'Nivel académico más alto alcanzado', 'Titulo o diploma (profesión)', 'Pueblo de pertenencia',
    'Comunidad Lingüística', 'Cantidad de hijos', 'Temporalidad del contrato', 'Tipo de contrato',
    'Fecha de inicio de labores', 'Fecha de reinicio de labores', 'Fecha de finalización de labores',
    'Jornada de Trabajo', 'Días laborados en el año', 'Salario mensual nominal',
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

        return [
            employee.registration_number or '',
            employee.primer_nombre or '', employee.segundo_nombre or '', employee.tercer_nombre or '',
            employee.primer_apellido or '', employee.segundo_apellido or '', employee.apellido_casada or '',
            _country_code_3(employee.country_id),
            employee.discapacidad or '1',
            MARITAL_CODE.get(employee.marital, '1'),
            _doc_identificacion_code(employee),
            employee.identification_id or '',
            _country_code_3(employee.country_of_birth),
            employee.permit_no or '',
            employee.municipio_id.code or '',
            employee.nit or '',
            employee.igss or '',
            SEX_CODE.get(employee.sex, '1'),
            employee.birthday.strftime('%d-%m-%Y') if employee.birthday else '',
            CERTIFICATE_CODE.get(employee.certificate, employee.certificate or ''),
            employee.study_field or '',
            employee.pueblo_pertenencia or '1',
            employee.comunidad_linguistica or '99',
            employee.children or 0,
            _temporalidad_contrato_code(version),
            # Tipo de contrato (1=Verbal, 2=Escrito): fijo en 2 a propósito - el usuario
            # confirmó 2026-09-17 que en esta empresa todos los contratos son escritos.
            2,
            primera,
            segunda,
            tercera,
            employee.jornada_trabajo or '',
            dias_laborados,
            version.wage or '',
            version.wage or '',
            abs(salario_base),
            0,
            abs(horas_extras),
            version.x_horas_extra_valor or '',
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
