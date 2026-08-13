from markupsafe import escape

from odoo import fields, models

FIXED_HEADERS = ['Empleado', 'Código', 'Puesto', 'Departamento', 'Lote', 'Del', 'Al']


class WizardReporteDetalleNomina(models.TransientModel):
    _name = 'wizard.reporte.detalle.nomina'
    _description = 'Wizard Detalle de Recibos de Nómina'
    _inherit = ['construtec.nomina.report.wizard.mixin']

    date_start = fields.Date(string='Del', required=True)
    date_end = fields.Date(string='Al', required=True)
    payslip_run_ids = fields.Many2many('hr.payslip.run', string='Lotes')
    preview_html = fields.Html(string='Detalle', sanitize=False, readonly=True)

    def _get_payslips(self):
        domain = [
            ('date_from', '>=', self.date_start), ('date_to', '<=', self.date_end),
            ('company_id', '=', self.company_id.id), ('state', 'in', ('validated', 'paid')),
        ]
        if self.payslip_run_ids:
            domain.append(('payslip_run_id', 'in', self.payslip_run_ids.ids))
        return self.env['hr.payslip'].search(domain, order='employee_id, date_from asc')

    def _compute_matrix(self):
        """Arma columnas dinámicamente a partir de los codigos de regla salarial que
        efectivamente aparecen en los recibos seleccionados (no una lista fija), porque
        distintas estructuras salariales pueden tener conjuntos de reglas distintos.
        Devuelve (headers, rows, totals). Usado tanto por el visor como por el Excel para
        que nunca queden desalineados."""
        payslips = self._get_payslips()

        dynamic_codes = []
        dynamic_headers = []
        for payslip in payslips:
            for line in payslip.line_ids:
                if line.code and line.code not in dynamic_codes:
                    dynamic_codes.append(line.code)
                    dynamic_headers.append(line.name or line.code)

        headers = FIXED_HEADERS + dynamic_headers
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

        return headers, rows, totals

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

        return (
            '<div style="overflow-x:auto;">'
            '<table style="border-collapse:collapse;font-size:12px;">'
            f'<thead><tr>{header_cells}</tr></thead>'
            f'<tbody>{"".join(body_rows)}<tr>{total_cells}</tr></tbody>'
            '</table></div>'
        )

    def _build_xlsx(self, headers, rows, totals):
        buffer, workbook = self.new_workbook()
        sheet = workbook.add_worksheet('Detalle de Nómina')
        bold = workbook.add_format({'bold': True})
        money = workbook.add_format({'num_format': '#,##0.00'})
        bold_money = workbook.add_format({'bold': True, 'num_format': '#,##0.00'})

        n_cols = len(headers)
        n_fixed = len(FIXED_HEADERS)
        sheet.merge_range(0, 0, 0, n_cols - 1, self.company_id.name, bold)
        sheet.merge_range(1, 0, 1, n_cols - 1,
                           f'Detalle de Nómina - Del {self.date_start.strftime("%d/%m/%Y")} '
                           f'al {self.date_end.strftime("%d/%m/%Y")}')
        for col, header in enumerate(headers):
            sheet.write(2, col, header, bold)

        row_idx = 3
        for row in rows:
            for col, value in enumerate(row):
                if col >= n_fixed:
                    sheet.write_number(row_idx, col, value, money)
                else:
                    sheet.write(row_idx, col, value)
            row_idx += 1

        for col, value in enumerate(totals):
            if col >= n_fixed:
                sheet.write_number(row_idx, col, value, bold_money)
            else:
                sheet.write(row_idx, col, value or '', bold)

        return self.finalize_workbook(buffer, workbook, 'Detalle_Nomina.xlsx')

    def action_generar(self):
        self.ensure_one()
        self.check_date()
        headers, rows, totals = self._compute_matrix()
        self.preview_html = self._build_preview_html(headers, rows, totals)
        return self._build_xlsx(headers, rows, totals)
