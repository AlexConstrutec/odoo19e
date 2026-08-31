from odoo import fields, models
from odoo.exceptions import UserError


class WizardExportVoucher(models.TransientModel):
    _name = 'wizard.export.voucher'
    _description = 'Exportar Vouchers (Recibos de Pago) en PDF'

    payslip_run_ids = fields.Many2many(
        'hr.payslip.run', string='Lotes de Nómina',
        help='Exporta el voucher de TODAS las nóminas de estos lotes. Combinable con '
             'Empleados: si también eliges empleados, solo exporta las nóminas de esos '
             'empleados dentro de estos lotes.')
    employee_ids = fields.Many2many(
        'hr.employee', string='Empleados',
        help='Exporta el voucher solo de estos empleados. Combinable con Lotes de Nómina: '
             'si no eliges ningún lote, exporta TODAS las nóminas de estos empleados (de '
             'cualquier período) - elige también un lote para acotar a un período concreto.')

    def action_exportar(self):
        """Reutiliza el reporte PDF de voucher ya existente (construtec_hr_reports_19.
        report_voucher) - no genera ningún archivo nuevo, solo resuelve qué nóminas incluir
        y le pide al mismo reporte que las imprima todas juntas (una página por nómina,
        gracias al t-foreach agregado en voucher_templates.xml)."""
        self.ensure_one()
        if not self.payslip_run_ids and not self.employee_ids:
            raise UserError(self.env._(
                'Elige al menos un Lote de Nómina o un Empleado para exportar.'))
        domain = [('state', '!=', 'cancel')]
        if self.payslip_run_ids:
            domain.append(('payslip_run_id', 'in', self.payslip_run_ids.ids))
        if self.employee_ids:
            domain.append(('employee_id', 'in', self.employee_ids.ids))
        payslips = self.env['hr.payslip'].search(domain)
        if not payslips:
            raise UserError(self.env._(
                'No se encontraron nóminas con los criterios seleccionados.'))
        return self.env.ref('construtec_hr_reports_19.report_voucher').report_action(
            payslips, config=False)
