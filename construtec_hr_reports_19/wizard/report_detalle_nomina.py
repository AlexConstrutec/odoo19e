import base64

from markupsafe import Markup, escape

from odoo import fields, models

FIXED_HEADERS = ['Empleado', 'Código', 'Puesto', 'Departamento', 'Lote', 'Del', 'Al']

# Códigos de reglas salariales excluidos del detalle (reservas/provisiones contables que
# no forman parte del pago real al empleado, a pedido del usuario).
EXCLUDED_CODES = {'BONO14', 'AGUINALDO', 'INDM', 'VACAC'}

# Clasificación suma/resta para colorear el Excel. Los códigos conocidos vienen de las
# reglas ya usadas en los demás wizards de este módulo (report_planilla_sueldos.py,
# report_libro_sueldos.py, report_planilla_igss.py) y fueron confirmados por el usuario:
# ANT1 = Vales, ANT2 = Otros Descuentos, ANT3 = Prestamos. Para códigos no vistos antes
# (cada empresa configura sus reglas directo en la UI de Odoo) se usa como respaldo una
# búsqueda de palabras clave en el nombre de la regla.
DEDUCTION_CODES = {
    'IGSSLABR', 'CIGSSLAB', 'ISRASA', 'ANT1', 'ANT2', 'ANT3', 'DEDU', 'LO', 'ISR_AJ', 'SAR',
}
DEDUCTION_KEYWORDS = ['descuento', 'deduccion', 'deducción', 'retenc', 'prestamo', 'préstamo', 'anticipo']


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
        domain = [
            ('date_from', '<=', self.date_end), ('date_to', '>=', self.date_start),
            ('company_id', '=', self.company_id.id), ('state', 'in', ('validated', 'paid')),
        ]
        if self.payslip_run_ids:
            domain.append(('payslip_run_id', 'in', self.payslip_run_ids.ids))
        return self.env['hr.payslip'].search(domain, order='employee_id, date_from asc')

    @staticmethod
    def _is_deduction(code, name):
        if code in DEDUCTION_CODES:
            return True
        name_l = (name or '').lower()
        return any(kw in name_l for kw in DEDUCTION_KEYWORDS)

    def _compute_matrix(self):
        """Arma columnas dinámicamente a partir de los codigos de regla salarial que
        efectivamente aparecen en los recibos seleccionados (no una lista fija), porque
        distintas estructuras salariales pueden tener conjuntos de reglas distintos.
        Devuelve (headers, rows, totals, column_kinds). column_kinds está alineado con
        headers: None para las columnas fijas, 'add'/'sub' para las dinámicas (usado para
        colorear el Excel). Usado tanto por el visor como por el Excel para que nunca
        queden desalineados."""
        payslips = self._get_payslips()

        dynamic_codes = []
        dynamic_headers = []
        dynamic_kinds = []
        for payslip in payslips:
            for line in payslip.line_ids:
                if line.code and line.code not in EXCLUDED_CODES and line.code not in dynamic_codes:
                    dynamic_codes.append(line.code)
                    dynamic_headers.append(line.name or line.code)
                    dynamic_kinds.append('sub' if self._is_deduction(line.code, line.name) else 'add')

        headers = FIXED_HEADERS + dynamic_headers
        column_kinds = [None] * len(FIXED_HEADERS) + dynamic_kinds
        rows = []
        for payslip in payslips:
            employee = payslip.employee_id
            codes = {}
            for line in payslip.line_ids:
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
            row.extend(codes.get(code, 0.0) for code in dynamic_codes)
            rows.append(row)

        totals = [None] * len(FIXED_HEADERS)
        totals[0] = 'TOTAL'
        for col in range(len(dynamic_codes)):
            totals.append(sum(row[len(FIXED_HEADERS) + col] for row in rows))

        return headers, rows, totals, column_kinds

    def _build_preview_html(self, headers, rows, totals):
        n_fixed = len(FIXED_HEADERS)

        def fmt(value, is_amount):
            if value is None:
                return ''
            if is_amount:
                return f'{value:,.2f}'
            return str(value)

        header_cells = ''.join(f'<th style="border:1px solid #ccc;padding:4px;background:#f2f2f2;'
                                f'white-space:nowrap;">{escape(h)}</th>' for h in headers)
        body_rows = []
        for row in rows:
            cells = ''.join(
                f'<td style="border:1px solid #ccc;padding:4px;text-align:{"right" if i >= n_fixed else "left"};'
                f'white-space:nowrap;">{escape(fmt(value, i >= n_fixed))}</td>'
                for i, value in enumerate(row))
            body_rows.append(f'<tr>{cells}</tr>')
        total_cells = ''.join(
            f'<td style="border:1px solid #ccc;padding:4px;text-align:{"right" if i >= n_fixed else "left"};'
            f'white-space:nowrap;font-weight:bold;">{escape(fmt(value, i >= n_fixed))}</td>'
            for i, value in enumerate(totals))

        # Markup (no un str plano) para que el reporte qweb-html lo pueda mostrar con
        # t-out sin que se escape como texto - ver report_detalle_nomina_document.
        return Markup(
            '<div style="overflow-x:auto;">'
            '<table style="border-collapse:collapse;font-size:12px;">'
            f'<thead><tr>{header_cells}</tr></thead>'
            f'<tbody>{"".join(body_rows)}<tr>{total_cells}</tr></tbody>'
            '</table></div>'
        )

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
                    fmt = add_money if kind == 'add' else sub_money
                    sheet.write_number(row_idx, col, value, fmt)
                else:
                    sheet.write(row_idx, col, value)
            row_idx += 1

        for col, value in enumerate(totals):
            if col >= n_fixed:
                kind = column_kinds[col]
                fmt = add_bold_money if kind == 'add' else sub_bold_money
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
        """Abre el detalle en una pantalla nueva (reporte qweb-html), no en este mismo wizard."""
        self.ensure_one()
        self.check_date()
        return self.env.ref('construtec_hr_reports_19.action_report_detalle_nomina').report_action(self, config=False)

    def action_excel(self):
        self.ensure_one()
        self.check_date()
        headers, rows, totals, kinds = self._compute_matrix()
        return self._build_xlsx(headers, rows, totals, kinds)
