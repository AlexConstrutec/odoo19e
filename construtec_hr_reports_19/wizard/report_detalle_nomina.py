import base64

from odoo import fields, models

FIXED_HEADERS = ['Empleado', 'Código', 'Puesto', 'Departamento', 'Lote', 'Del', 'Al']

# Códigos de reglas salariales excluidos del detalle por completo (reservas/provisiones
# contables que no forman parte del pago real al empleado, a pedido del usuario) - ni
# columna propia, ni sumados en "Otros Conceptos".
EXCLUDED_CODES = {'BONO14', 'AGUINALDO', 'INDM', 'VACAC'}

# Lista fija de conceptos (una columna por cada uno, en el Excel y en el visor), en vez de
# columnas 100% dinámicas: Odoo fuerza a que las columnas generadas por un campo Properties
# en una vista lista arranquen ocultas (optional="hide" fijo en list_renderer.js, sin forma
# de configurarlo), así que para que el visor muestre todo visible desde el principio hace
# falta que sean campos reales. Los códigos vienen de los que ya se usan en los demás
# wizards de este módulo (report_planilla_sueldos.py/report_libro_sueldos.py/
# report_planilla_igss.py) y de los confirmados directamente por el usuario (ANT1=Vales,
# ANT2=Otros Descuentos, ANT3=Prestamos - LO también es Prestamo, ver
# construtec_hr_payroll_19/models/hr_payslip.py::_compute_extra_inputs()). 'kind' clasifica
# suma/resta para el coloreado del Excel. Cualquier código de regla que NO esté en esta
# lista (y no esté en EXCLUDED_CODES) se suma en la columna "Otros Conceptos" al final, para
# que nada del detalle real desaparezca en silencio.
CONCEPTS = [
    {'field': 'salario_base', 'label': 'Salario Base', 'codes': ['BASIC'], 'kind': 'add'},
    {'field': 'bonificacion_incentivo', 'label': 'Bonificación Incentivo', 'codes': ['BONIN'], 'kind': 'add'},
    {'field': 'bonificacion_fija', 'label': 'Bonificación Fija', 'codes': ['BOFIJ'], 'kind': 'add'},
    {'field': 'bonificacion_ajuste', 'label': 'Bonificación por Ajuste', 'codes': ['MDOA'], 'kind': 'add'},
    {'field': 'bonificacion_asueto', 'label': 'Bonificación por Asueto', 'codes': ['MDOAS'], 'kind': 'add'},
    {'field': 'bonificacion_productividad', 'label': 'Bonificación por Productividad', 'codes': ['BONPRO'], 'kind': 'add'},
    {'field': 'alimentacion', 'label': 'Alimentación', 'codes': ['MDOALIM'], 'kind': 'add'},
    {'field': 'horas_extra', 'label': 'Horas Extras', 'codes': ['VHEB'], 'kind': 'add'},
    {'field': 'bonificacion_horas', 'label': 'Bonificación por Horas', 'codes': ['BHE'], 'kind': 'add'},
    {'field': 'bonificaciones_extras', 'label': 'Bonificaciones Extras', 'codes': ['OTREN'], 'kind': 'add'},
    {'field': 'gratificacion', 'label': 'Gratificación', 'codes': ['OTRGRATIF'], 'kind': 'add'},
    {'field': 'devolucion_isr', 'label': 'Devolución de ISR', 'codes': ['DEVISR'], 'kind': 'add'},
    {'field': 'bono14_pago', 'label': 'Bono 14 Pago', 'codes': ['BONO14P'], 'kind': 'add'},
    {'field': 'aguinaldo_pago', 'label': 'Aguinaldo Pago', 'codes': ['AGUINALDOP'], 'kind': 'add'},
    {'field': 'indemnizacion_pago', 'label': 'Indemnización Pago', 'codes': ['INDEMP'], 'kind': 'add'},
    {'field': 'vacaciones_pago', 'label': 'Vacaciones Pago', 'codes': ['VACACPAG'], 'kind': 'add'},
    {'field': 'igss_patronal', 'label': 'IGSS Patronal', 'codes': ['IGSS PAT'], 'kind': 'add'},
    {'field': 'complemento_igss_patronal', 'label': 'Complemento IGSS Patronal', 'codes': ['CIGSSPAT'], 'kind': 'add'},
    {'field': 'irtra', 'label': 'IRTRA', 'codes': ['IRTRA'], 'kind': 'add'},
    {'field': 'intecap', 'label': 'INTECAP', 'codes': ['INTECAP'], 'kind': 'add'},
    {'field': 'salario_devengado', 'label': 'Salario Devengado', 'codes': ['GROSS'], 'kind': 'add'},
    {'field': 'igss_laboral', 'label': 'IGSS Laboral', 'codes': ['IGSSLABR'], 'kind': 'sub'},
    {'field': 'complemento_igss_laboral', 'label': 'Complemento IGSS Laboral', 'codes': ['CIGSSLAB'], 'kind': 'sub'},
    {'field': 'isr_asalariados', 'label': 'ISR Asalariados', 'codes': ['ISRASA'], 'kind': 'sub'},
    {'field': 'vales', 'label': 'Vales', 'codes': ['ANT1'], 'kind': 'sub'},
    {'field': 'otros_descuentos', 'label': 'Otros Descuentos', 'codes': ['ANT2'], 'kind': 'sub'},
    {'field': 'prestamos', 'label': 'Préstamos', 'codes': ['ANT3', 'LO'], 'kind': 'sub'},
    {'field': 'retencion_isr', 'label': 'Retención ISR', 'codes': ['ISR_AJ'], 'kind': 'sub'},
    {'field': 'total_deducciones', 'label': 'Total Deducciones', 'codes': ['DEDU'], 'kind': 'sub'},
    {'field': 'salario_neto', 'label': 'Salario Neto', 'codes': ['NET'], 'kind': 'add'},
]
OTHER_FIELD = 'otros_conceptos'
OTHER_LABEL = 'Otros Conceptos'


class WizardReporteDetalleNomina(models.TransientModel):
    _name = 'wizard.reporte.detalle.nomina'
    _description = 'Wizard Detalle de Recibos de Nómina'
    _inherit = ['construtec.nomina.report.wizard.mixin']

    date_start = fields.Date(string='Del', required=True)
    date_end = fields.Date(string='Al', required=True)
    payslip_run_ids = fields.Many2many('hr.payslip.run', string='Lotes')

    def _get_payslips(self):
        # Domain por solapamiento (no por contención estricta): toma cualquier recibo cuyo
        # periodo se cruce con el rango Del/Al elegido, para no dejar fuera lotes cuyo
        # periodo no calza exactamente con las fechas seleccionadas.
        # Estado: cualquiera excepto 'cancel' (no solo 'validated'/'paid' como los demás
        # wizards de compliance de este módulo) - si el usuario generó varios lotes pero
        # solo validó uno, los demás siguen en 'draft' y aun así deben aparecer aquí; este
        # reporte es de revisión/exportación del detalle, no un reporte legal que dependa
        # de que la nómina ya esté cerrada.
        domain = [
            ('date_from', '<=', self.date_end), ('date_to', '>=', self.date_start),
            ('company_id', '=', self.company_id.id), ('state', '!=', 'cancel'),
        ]
        if self.payslip_run_ids:
            domain.append(('payslip_run_id', 'in', self.payslip_run_ids.ids))
        return self.env['hr.payslip'].search(domain, order='employee_id, date_from asc')

    def _compute_matrix(self):
        """Arma la matriz con la lista fija de CONCEPTS (una columna por concepto conocido,
        más "Otros Conceptos" para códigos de regla no reconocidos). Devuelve (headers,
        rows, totals, column_kinds, payslips). column_kinds está alineado con headers: None
        para las columnas fijas, 'add'/'sub' para las de concepto ('Otros Conceptos' queda
        en None porque puede mezclar ambos). payslips está alineado 1 a 1 con rows. Usado
        tanto por el visor como por el Excel para que nunca queden desalineados."""
        payslips = self._get_payslips()
        known_codes = {code for concept in CONCEPTS for code in concept['codes']}

        headers = FIXED_HEADERS + [c['label'] for c in CONCEPTS] + [OTHER_LABEL]
        column_kinds = [None] * len(FIXED_HEADERS) + [c['kind'] for c in CONCEPTS] + [None]

        rows = []
        for payslip in payslips:
            employee = payslip.employee_id
            codes = {}
            for line in payslip.line_ids:
                if line.code:
                    codes[line.code] = codes.get(line.code, 0.0) + line.total
            row = [
                employee.name,
                employee.codigo_empleado or '',
                employee.job_id.name or '',
                employee.department_id.name or '',
                payslip.payslip_run_id.name or '',
                payslip.date_from.strftime('%d/%m/%Y'),
                payslip.date_to.strftime('%d/%m/%Y'),
            ]
            for concept in CONCEPTS:
                row.append(sum(codes.get(code, 0.0) for code in concept['codes']))
            row.append(sum(
                amount for code, amount in codes.items()
                if code not in known_codes and code not in EXCLUDED_CODES))
            rows.append(row)

        n_fixed = len(FIXED_HEADERS)
        totals = [None] * n_fixed
        totals[0] = 'TOTAL'
        for col in range(len(CONCEPTS) + 1):
            totals.append(sum(row[n_fixed + col] for row in rows))

        return headers, rows, totals, column_kinds, payslips

    def _build_xlsx(self, headers, rows, totals, column_kinds):
        buffer, workbook = self.new_workbook()
        sheet = workbook.add_worksheet('Detalle de Nómina')
        bold = workbook.add_format({'bold': True})
        money = workbook.add_format({'num_format': '#,##0.00'})
        bold_money = workbook.add_format({'bold': True, 'num_format': '#,##0.00'})
        # Verde claro para columnas que suman, rojo claro para las que restan.
        add_header = workbook.add_format({'bold': True, 'bg_color': '#C6EFCE'})
        add_money = workbook.add_format({'num_format': '#,##0.00', 'bg_color': '#C6EFCE'})
        add_bold_money = workbook.add_format({'bold': True, 'num_format': '#,##0.00', 'bg_color': '#C6EFCE'})
        sub_header = workbook.add_format({'bold': True, 'bg_color': '#FFC7CE'})
        sub_money = workbook.add_format({'num_format': '#,##0.00', 'bg_color': '#FFC7CE'})
        sub_bold_money = workbook.add_format({'bold': True, 'num_format': '#,##0.00', 'bg_color': '#FFC7CE'})

        n_cols = len(headers)
        n_fixed = len(FIXED_HEADERS)
        sheet.merge_range(0, 0, 0, n_cols - 1, self.company_id.name, bold)
        sheet.merge_range(1, 0, 1, n_cols - 1,
                           f'Detalle de Nómina - Del {self.date_start.strftime("%d/%m/%Y")} '
                           f'al {self.date_end.strftime("%d/%m/%Y")}')
        for col, header in enumerate(headers):
            kind = column_kinds[col]
            fmt = add_header if kind == 'add' else sub_header if kind == 'sub' else bold
            sheet.write(2, col, header, fmt)

        row_idx = 3
        for row in rows:
            for col, value in enumerate(row):
                if col >= n_fixed:
                    kind = column_kinds[col]
                    fmt = add_money if kind == 'add' else sub_money if kind == 'sub' else money
                    sheet.write_number(row_idx, col, value, fmt)
                else:
                    sheet.write(row_idx, col, value)
            row_idx += 1

        for col, value in enumerate(totals):
            if col >= n_fixed:
                kind = column_kinds[col]
                fmt = add_bold_money if kind == 'add' else sub_bold_money if kind == 'sub' else bold_money
                sheet.write_number(row_idx, col, value, fmt)
            else:
                sheet.write(row_idx, col, value or '', bold)

        workbook.close()
        filename = 'Detalle_Nomina.xlsx'
        self.write({'data': base64.b64encode(buffer.getvalue()), 'name': filename})
        # ir.actions.act_url con download=true dispara la descarga directa del archivo,
        # sin pasar por una pantalla intermedia de "Archivo listo, haga clic para bajarlo".
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{self._name}/{self.id}/data/{filename}?download=true',
            'target': 'self',
        }

    def action_ver(self):
        """Abre el detalle en una vista lista nativa de Odoo: una fila por recibo, con cada
        concepto conocido como su propia columna (igual que el Excel), todas visibles por
        defecto. Se usan campos reales (no fields.Properties) porque Odoo fuerza a que las
        columnas de un campo Properties en una vista lista arranquen ocultas
        (optional="hide" fijo en list_renderer.js), sin ninguna forma soportada de
        cambiarlo - ver CONCEPTS más arriba."""
        self.ensure_one()
        self.check_date()
        headers, rows, totals, kinds, payslips = self._compute_matrix()
        n_fixed = len(FIXED_HEADERS)
        concept_fields = [c['field'] for c in CONCEPTS] + [OTHER_FIELD]

        line_vals = []
        for row, payslip in zip(rows, payslips):
            employee = payslip.employee_id
            vals = {
                'employee_id': employee.id,
                'codigo_empleado': employee.codigo_empleado or '',
                'job_id': employee.job_id.id,
                'department_id': employee.department_id.id,
                'payslip_run_id': payslip.payslip_run_id.id,
                'date_from': payslip.date_from,
                'date_to': payslip.date_to,
            }
            for i, field_name in enumerate(concept_fields):
                vals[field_name] = row[n_fixed + i]
            line_vals.append(vals)

        lines = self.env['wizard.reporte.detalle.nomina.line'].create(line_vals)
        return {
            'type': 'ir.actions.act_window',
            'name': 'Detalle de Nómina',
            'res_model': 'wizard.reporte.detalle.nomina.line',
            'view_mode': 'list',
            'domain': [('id', 'in', lines.ids)],
            'target': 'current',
        }

    def action_excel(self):
        self.ensure_one()
        self.check_date()
        headers, rows, totals, kinds, _payslips = self._compute_matrix()
        return self._build_xlsx(headers, rows, totals, kinds)


class WizardReporteDetalleNominaLine(models.TransientModel):
    _name = 'wizard.reporte.detalle.nomina.line'
    _description = 'Línea de Detalle de Nómina (visor)'
    _order = 'employee_id, date_from'

    employee_id = fields.Many2one('hr.employee', string='Empleado')
    codigo_empleado = fields.Char(string='Código')
    job_id = fields.Many2one('hr.job', string='Puesto')
    department_id = fields.Many2one('hr.department', string='Departamento')
    payslip_run_id = fields.Many2one('hr.payslip.run', string='Lote')
    date_from = fields.Date(string='Del')
    date_to = fields.Date(string='Al')

    salario_base = fields.Float(string='Salario Base')
    bonificacion_incentivo = fields.Float(string='Bonificación Incentivo')
    bonificacion_fija = fields.Float(string='Bonificación Fija')
    bonificacion_ajuste = fields.Float(string='Bonificación por Ajuste')
    bonificacion_asueto = fields.Float(string='Bonificación por Asueto')
    bonificacion_productividad = fields.Float(string='Bonificación por Productividad')
    alimentacion = fields.Float(string='Alimentación')
    horas_extra = fields.Float(string='Horas Extras')
    bonificacion_horas = fields.Float(string='Bonificación por Horas')
    bonificaciones_extras = fields.Float(string='Bonificaciones Extras')
    gratificacion = fields.Float(string='Gratificación')
    devolucion_isr = fields.Float(string='Devolución de ISR')
    bono14_pago = fields.Float(string='Bono 14 Pago')
    aguinaldo_pago = fields.Float(string='Aguinaldo Pago')
    indemnizacion_pago = fields.Float(string='Indemnización Pago')
    vacaciones_pago = fields.Float(string='Vacaciones Pago')
    igss_patronal = fields.Float(string='IGSS Patronal')
    complemento_igss_patronal = fields.Float(string='Complemento IGSS Patronal')
    irtra = fields.Float(string='IRTRA')
    intecap = fields.Float(string='INTECAP')
    salario_devengado = fields.Float(string='Salario Devengado')
    igss_laboral = fields.Float(string='IGSS Laboral')
    complemento_igss_laboral = fields.Float(string='Complemento IGSS Laboral')
    isr_asalariados = fields.Float(string='ISR Asalariados')
    vales = fields.Float(string='Vales')
    otros_descuentos = fields.Float(string='Otros Descuentos')
    prestamos = fields.Float(string='Préstamos')
    retencion_isr = fields.Float(string='Retención ISR')
    total_deducciones = fields.Float(string='Total Deducciones')
    salario_neto = fields.Float(string='Salario Neto')
    otros_conceptos = fields.Float(string='Otros Conceptos')
