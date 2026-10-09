from itertools import groupby

from odoo import fields, models
from odoo.exceptions import UserError

TEXT_LEY_1 = ('LIBRO COMPUTARIZADO PARA LA OPERACIÓN DE SALARIOS DE TRABAJADORES PERMANENTES, '
              'AUTORIZADO POR EL MINISTERIO DE TRABAJO Y')
TEXT_LEY_2 = ('PREVISION SOCIAL, FUNDAMENTO LEGAL: ARTÍCULOS 102 DEL DECRETO No. 1441 Y 2 DEL '
              'ACUERDO MINISTERIAL No. 124-2019')

# Cada folio es una página física del libro: encabezado de la entidad + datos del trabajador +
# hasta DATA_ROWS_PER_PAGE pagos de ESE trabajador. Un trabajador nuevo siempre arranca folio nuevo.
PAGE_ROWS = 35
HEADER_ROWS = 15
DATA_ROWS_PER_PAGE = PAGE_ROWS - HEADER_ROWS

# Columnas del formato oficial "Modelo del Formato Único de Salarios" (MINTRAB): B..W
FIRST_COL = 1
LAST_COL = 22
COLUMN_WIDTHS = [1.5, 6.5, 19, 10, 8.5, 9.5, 11.5, 10.5, 11, 10.8, 10.7, 10.4,
                 10, 10.5, 9.5, 10.8, 9, 10.5, 10.5, 10.3, 11.1, 13.4, 13.3]
MONEY_INDEXES = {2, *range(6, 20)}
CENTER_INDEXES = {0, 1, 3, 4, 5}

PERSON_ROW_1 = [
    ('name', 1, 4, 'Nombre del trabajador'),
    ('edad', 8, 8, 'Edad'),
    ('genero', 11, 12, 'Género'),
    ('nacionalidad', 14, 17, 'Nacionalidad'),
    ('puesto', 20, 22, 'Ocupación o puesto que desempeña'),
]
PERSON_ROW_2 = [
    ('igss', 1, 4, 'No. de afiliación al IGSS.'),
    ('dpi', 7, 9, 'No. DPI ó permiso de trabajo.'),
    ('inicio', 14, 17, 'Inicio de relación laboral'),
    ('fin', 20, 22, 'Fecha de finalización de relación laboral'),
]
SINGLE_HEADERS = [
    (1, 'No. de Pago'), (2, 'Período de trabajo'), (3, 'Salario en Quetzales'), (4, 'Días trabajados'),
    (12, 'SALARIO TOTAL'), (17, 'Bonificación anual 42-92, Aguinaldo Decreto 76-78'),
    (18, 'Bonificación Incentivo Decreto 37-2001'), (19, 'Devoluciones I.S.R. y otras'),
    (20, 'Salario Líquido'), (21, 'Firma o número de boleta de pago / váucher.'), (22, 'Observaciones'),
]
GROUP_HEADERS = [
    (5, 6, 'HORAS TRABAJADAS', ('Ordinarias', 'Extraordinarias')),
    (7, 11, 'SALARIO DEVENGADO', ('Ordinario', 'Extraordinario', 'Otros salarios', 'Séptimos y asuetos', 'Vacaciones')),
    (13, 16, 'DEDUCCIONES LEGALES', ('Cuota laboral IGSS', 'Descuentos ISR', 'Otras Deducciones', 'TOTAL')),
]


def _formats(workbook):
    def fmt(**kwargs):
        return workbook.add_format({'font_name': 'Arial Narrow', 'font_size': 8, **kwargs})

    return {
        'folio_label': fmt(font_size=12, align='right'),
        'folio_value': fmt(font_size=14, align='center', valign='vcenter', bottom=1),
        'company': workbook.add_format(
            {'font_name': 'Times New Roman', 'font_size': 14, 'bold': True, 'align': 'center'}),
        'nit': workbook.add_format(
            {'font_name': 'Times New Roman', 'font_size': 13, 'bold': True, 'align': 'center'}),
        'legal': workbook.add_format(
            {'font_name': 'Calibri', 'font_size': 11, 'align': 'center', 'valign': 'vcenter'}),
        'person_value': fmt(font_size=10, align='center', bottom=1),
        'person_label': fmt(font_size=10, align='center'),
        'col_header': fmt(align='center', valign='vcenter', text_wrap=True, border=1),
        'cell_center': fmt(align='center', valign='vcenter', border=1),
        'cell_money': fmt(align='right', valign='vcenter', border=1, num_format='Q#,##0.00'),
        'cell_text': fmt(align='left', valign='vcenter', border=1),
    }


def _write_span(sheet, row, first, last, value, cell_format):
    if first == last:
        sheet.write(row, first, value, cell_format)
    else:
        sheet.merge_range(row, first, row, last, value, cell_format)


def _write_page_header(sheet, fmts, top, folio, company_name, company_vat, person):
    # El sufijo "E" del folio viene del reporte original de Odoo 16 (libro electrónico).
    sheet.write(top, 21, 'Folio No.', fmts['folio_label'])
    sheet.write(top, 22, f'{folio}E', fmts['folio_value'])
    sheet.set_row(top + 1, 18.75)
    sheet.merge_range(top + 1, FIRST_COL, top + 1, LAST_COL, company_name, fmts['company'])
    sheet.set_row(top + 2, 16.5)
    sheet.merge_range(top + 2, FIRST_COL, top + 2, LAST_COL, f'NIT: {company_vat or ""}', fmts['nit'])
    sheet.merge_range(top + 3, FIRST_COL, top + 3, LAST_COL, TEXT_LEY_1, fmts['legal'])
    sheet.merge_range(top + 4, FIRST_COL, top + 4, LAST_COL, TEXT_LEY_2, fmts['legal'])

    for offset, spans in ((6, PERSON_ROW_1), (9, PERSON_ROW_2)):
        for key, first, last, label in spans:
            _write_span(sheet, top + offset, first, last, person[key], fmts['person_value'])
            _write_span(sheet, top + offset + 1, first, last, label, fmts['person_label'])

    first_row, last_row = top + 12, top + 14
    for row in range(first_row, last_row + 1):
        sheet.set_row(row, 20)
    for col, text in SINGLE_HEADERS:
        sheet.merge_range(first_row, col, last_row, col, text, fmts['col_header'])
    for first, last, text, sub_headers in GROUP_HEADERS:
        sheet.merge_range(first_row, first, first_row, last, text, fmts['col_header'])
        for col, sub_text in enumerate(sub_headers, start=first):
            sheet.merge_range(first_row + 1, col, last_row, col, sub_text, fmts['col_header'])


def _write_data_row(sheet, fmts, row, values):
    for index, value in enumerate(values):
        col = FIRST_COL + index
        if index in MONEY_INDEXES:
            sheet.write_number(row, col, value, fmts['cell_money'])
        elif index in CENTER_INDEXES:
            sheet.write(row, col, value, fmts['cell_center'])
        else:
            sheet.write(row, col, value, fmts['cell_text'])


def _write_libro(workbook, company_name, company_vat, first_folio, employees):
    """employees: lista de (person: dict, rows: lista de listas con las 22 columnas B..W)."""
    sheet = workbook.add_worksheet('Libro de Sueldos y Salarios')
    sheet.set_landscape()
    sheet.set_paper(5)
    sheet.set_margins(left=0.5, right=0.5, top=0.6, bottom=0.6)
    sheet.center_horizontally()
    # fit_to_pages() anularía los saltos de página manuales de abajo, por eso escala fija.
    sheet.set_print_scale(70)
    for col, width in enumerate(COLUMN_WIDTHS):
        sheet.set_column(col, col, width)

    fmts = _formats(workbook)
    folio, top, page_breaks = first_folio, 0, []
    for person, rows in employees:
        for start in range(0, len(rows), DATA_ROWS_PER_PAGE):
            if top:
                page_breaks.append(top)
            _write_page_header(sheet, fmts, top, folio, company_name, company_vat, person)
            for offset, values in enumerate(rows[start:start + DATA_ROWS_PER_PAGE]):
                _write_data_row(sheet, fmts, top + HEADER_ROWS + offset, values)
            folio += 1
            top += PAGE_ROWS
    sheet.set_h_pagebreaks(page_breaks)


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

    def _person_values(self, employee, version):
        inicio = version.contract_date_start or employee._get_first_contract_date()
        fin = version.contract_date_end
        return {
            'name': employee.name,
            'edad': employee.edad or '',
            'genero': self.selection_label(employee, 'sex'),
            'nacionalidad': (employee.country_id or employee.country_of_birth).name or '',
            'puesto': employee.job_title or '',
            'igss': employee.igss or '',
            'dpi': employee.identification_id or employee.permit_no or '',
            'inicio': inicio.strftime('%d/%m/%Y') if inicio else '',
            'fin': fin.strftime('%d/%m/%Y') if fin else '',
        }

    def _payslip_row(self, payslip, numero_pago):
        codes = {}
        for line in payslip.line_ids:
            codes[line.code] = codes.get(line.code, 0.0) + line.total

        salario_base = codes.get('BASIC', 0.0)
        salario_extra = codes.get('VHEB', 0.0)
        vacaciones = codes.get('VACACPAG', 0.0)
        cuota_igss = codes.get('IGSSLABR', 0.0) + codes.get('CIGSSLAB', 0.0)
        isr = codes.get('ISRASA', 0.0)
        otras_deducciones = codes.get('ANT1', 0.0) + codes.get('ANT2', 0.0) + codes.get('ANT3', 0.0)
        bono_aguinaldo = codes.get('AGUINALDOP', 0.0) + codes.get('BONO14P', 0.0)
        bono_incentivo = sum(codes.get(c, 0.0) for c in
                              ('BONIN', 'BOFIJ', 'BONPRO', 'OTREN', 'MDOA', 'MDOAS', 'BHE', 'MDOALIM'))
        devoluciones = codes.get('DEVISR', 0.0) + codes.get('INDEMP', 0.0)
        dias_trabajados = (payslip.date_to - payslip.date_from).days + 1

        return [
            numero_pago,
            f'{payslip.date_from:%d/%m/%Y} al {payslip.date_to:%d/%m/%Y}',
            salario_base,
            dias_trabajados,
            dias_trabajados * 8,
            round(self._horas_extraordinarias(payslip), 2),
            salario_base,
            salario_extra,
            0.0,
            0.0,
            vacaciones,
            salario_base + salario_extra + vacaciones,
            cuota_igss,
            isr,
            otras_deducciones,
            cuota_igss + isr + otras_deducciones,
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
        ])
        if not payslips:
            raise UserError(self.env._('No hay nóminas validadas o pagadas en el rango de fechas seleccionado.'))

        payslips = payslips.sorted(key=lambda p: (p.employee_id.name or '', p.employee_id.id, p.date_from))
        employees = []
        for _employee_id, group in groupby(payslips, key=lambda p: p.employee_id.id):
            slips = list(group)
            rows = [self._payslip_row(slip, number) for number, slip in enumerate(slips, start=1)]
            employees.append((self._person_values(slips[-1].employee_id, slips[-1].version_id), rows))

        buffer, workbook = self.new_workbook()
        _write_libro(workbook, self.company_id.name, self.company_id.vat, self.folio, employees)
        return self.finalize_workbook(buffer, workbook, 'Libro_Sueldos_Salarios.xlsx')
