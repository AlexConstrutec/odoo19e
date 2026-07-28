from odoo import fields, models
from odoo.exceptions import ValidationError

COLUMNS = ['Subcuenta', 'Método Pago', 'Número', 'Serie', 'Fecha', 'Proveedor', 'Descripción', 'Monto',
           'Transferencia/Cheque', 'Total Factura', 'Total de Retención IVA', 'IVA Retenido']


class WizardReporteBancarizacion(models.TransientModel):
    _name = 'wizard.reporte.bancarizacion'
    _description = 'Wizard Reporte Bancarización'
    _inherit = ['construtec.financial.report.wizard.mixin']

    date_start = fields.Date(string='Del', required=True)
    date_end = fields.Date(string='Al', required=True)
    journal_ids = fields.Many2many('account.journal', string='Diarios',
                                    domain="[('company_id', '=', company_id), ('type', 'in', ('bank', 'cash'))]")

    def check_date(self):
        for wizard in self:
            if wizard.date_end < wizard.date_start:
                raise ValidationError(self.env._('La fecha final debe ser posterior o igual a la fecha inicial.'))

    def _write_invoice_line(self, sheet, row, money, apunte, metodo_pago='', transferencia_cheque=''):
        invoice = apunte.move_id
        sheet.write(row, 0, apunte.account_id.code or '')
        sheet.write(row, 1, metodo_pago)
        sheet.write(row, 2, invoice.name or '')
        sheet.write(row, 4, invoice.date and invoice.date.strftime('%d-%m-%Y') or '')
        sheet.write(row, 5, invoice.partner_id.name or '')
        sheet.write(row, 6, apunte.name or '')
        sheet.write_number(row, 7, abs(apunte.debit or apunte.credit), money)
        sheet.write(row, 8, transferencia_cheque)
        sheet.write_number(row, 9, invoice.amount_total, money)

    def print_xls_reporte_bancarizacion(self):
        self.ensure_one()
        self.check_date()
        domain_base = [
            ('company_id', '=', self.company_id.id), ('date', '>=', self.date_start), ('date', '<=', self.date_end),
        ]

        buffer, workbook = self.new_workbook()
        sheet = workbook.add_worksheet('Reporte Bancarización')
        sheet.set_landscape()
        bold = workbook.add_format({'bold': True})
        money = workbook.add_format({'num_format': '#,##0.00'})
        sheet.write_row(0, 0, COLUMNS, bold)
        row = 1

        payment_domain = domain_base + [
            ('state', 'in', ('posted', 'sent', 'reconciled')), ('payslip_id', '=', False),
        ]
        if self.journal_ids:
            payment_domain.append(('journal_id', 'in', self.journal_ids.ids))
        payments = self.env['account.payment'].search(payment_domain, order='date desc')

        covered_invoice_ids = set()
        for payment in payments:
            invoices = payment.reconciled_invoice_ids | payment.reconciled_bill_ids
            for invoice in invoices.filtered(lambda m: m.state == 'posted'):
                covered_invoice_ids.add(invoice.id)
                otros_pagos = invoice.matched_payment_ids - payment
                for apunte in invoice.invoice_line_ids:
                    self._write_invoice_line(
                        sheet, row, money, apunte,
                        metodo_pago=payment.payment_method_line_id.name or '',
                        transferencia_cheque=', '.join(otros_pagos.mapped('ref') or []))
                    row += 1

        remaining_invoices = self.env['account.move'].search(domain_base + [
            ('id', 'not in', list(covered_invoice_ids)), ('move_type', 'in', ('in_invoice', 'out_invoice')),
            ('state', '=', 'posted'),
        ], order='date asc')
        for invoice in remaining_invoices:
            for apunte in invoice.invoice_line_ids:
                self._write_invoice_line(sheet, row, money, apunte)
                row += 1

        payroll_domain = domain_base + [
            ('state', 'in', ('posted', 'sent', 'reconciled')), ('payslip_id', '!=', False),
        ]
        if self.journal_ids:
            payroll_domain.append(('journal_id', 'in', self.journal_ids.ids))
        payroll_payments = self.env['account.payment'].search(payroll_domain, order='date desc')
        for payment in payroll_payments:
            for apunte in payment.move_id.line_ids.filtered(lambda l: l.debit > 0):
                sheet.write(row, 0, apunte.account_id.code or '')
                sheet.write(row, 4, payment.date.strftime('%d-%m-%Y'))
                sheet.write(row, 6, payment.payslip_id.name or '')
                sheet.write_number(row, 7, apunte.debit, money)
                row += 1

        return self.finalize_workbook(buffer, workbook, 'Reporte_Bancarizacion.xlsx')
