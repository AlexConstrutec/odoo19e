from collections import defaultdict

from odoo import fields, models

BRUTO_CODES = {'GROSS', 'IGSS PAT', 'CIGSSPAT', 'IRTRA', 'INTECAP'}
PRESTACIONES_CODES = {'BONO14', 'AGUINALDO', 'INDM', 'VACAC'}


class WizardReportFacturacion(models.TransientModel):
    _name = 'wizard.report.facturacion'
    _description = 'Wizard Reporte de Facturación'
    _inherit = ['construtec.nomina.report.wizard.mixin']

    planillas = fields.Many2many('hr.payslip.run', string='Lotes de Nómina', required=True)

    def print_xls_reporte_facturacion(self):
        self.ensure_one()
        runs = self.env['hr.payslip.run'].search([
            ('id', 'in', self.planillas.ids), ('company_id', '=', self.company_id.id)])
        payslips = self.env['hr.payslip'].search([
            ('company_id', '=', self.company_id.id), ('payslip_run_id', 'in', runs.ids)])

        groups = defaultdict(lambda: {'bruto': 0.0, 'prestaciones': 0.0, 'alimentacion': 0.0, 'analytic': None})
        for payslip in payslips:
            version = payslip.version_id
            analytic = self.analytic_account(version.analytic_distribution)
            key = (
                payslip.company_id.name,
                version.department_id.parent_id.name or '',
                analytic.name or '',
            )
            bucket = groups[key]
            bucket['analytic'] = analytic
            for line in payslip.line_ids:
                if line.code in BRUTO_CODES:
                    bucket['bruto'] += line.total
                elif line.code in PRESTACIONES_CODES:
                    bucket['prestaciones'] += line.total
                elif line.code == 'MDOALIM':
                    bucket['alimentacion'] += line.total

        buffer, workbook = self.new_workbook()
        sheet = workbook.add_worksheet('Reporte de Facturación')
        bold = workbook.add_format({'bold': True})
        headers = ['Empresa Recibe', 'Departamento', 'Centro de Costo', 'Sueldos',
                   'Prestaciones', 'Alimentación', 'Fac.Salarios', 'Fac.Prestaciones', 'Tipo Facturación']
        for col, header in enumerate(headers):
            sheet.write(0, col, header, bold)

        row = 1
        for (empresa_recibe, departamento, centro_costo), bucket in groups.items():
            analytic = bucket['analytic']
            sheet.write(row, 0, empresa_recibe)
            sheet.write(row, 1, departamento)
            sheet.write(row, 2, centro_costo)
            sheet.write(row, 3, (bucket['bruto'] - bucket['alimentacion']) * 1.12)
            sheet.write(row, 4, bucket['prestaciones'] * 1.12)
            sheet.write(row, 5, bucket['alimentacion'] * 1.12)
            sheet.write(row, 6, '')
            sheet.write(row, 7, '')
            sheet.write(row, 8, analytic.plan_id.name if analytic else '')
            row += 1

        return self.finalize_workbook(buffer, workbook, 'Reporte_Facturacion.xlsx')
