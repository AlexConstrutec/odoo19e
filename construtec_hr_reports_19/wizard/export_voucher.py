import base64
import io
import zipfile

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
        """Genera un PDF individual por nómina (reutilizando el mismo reporte que cada
        estructura salarial tiene configurado - `_get_pdf_reports()`, el mismo método que usa
        Odoo al validar una nómina para adjuntar su PDF, en vez de forzar un solo reporte fijo)
        y entrega todos los PDFs juntos en un único archivo ZIP - nunca un PDF combinado."""
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

        Report = self.env['ir.actions.report'].sudo()
        mapped_reports = payslips._get_pdf_reports()

        buffer = io.BytesIO()
        nombres_usados = set()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for report, slips in mapped_reports.items():
                for slip in slips:
                    pdf_content, _report_type = Report.with_context(
                        lang=slip.employee_id.lang or self.env.lang
                    )._render_qweb_pdf(report, slip.id)
                    zf.writestr(self._voucher_filename(slip, nombres_usados), pdf_content)

        attachment = self.env['ir.attachment'].create({
            'name': 'Vouchers.zip',
            'type': 'binary',
            'datas': base64.b64encode(buffer.getvalue()),
            'res_model': self._name,
            'res_id': self.id,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    @staticmethod
    def _voucher_filename(slip, nombres_usados):
        """Nombre del archivo dentro del ZIP - solo para esta exportación (no toca el
        contenido del voucher en sí): primer nombre + primer apellido del empleado, más el
        lote/período para no chocar si el mismo empleado aparece en más de una nómina
        seleccionada. Si aun así el nombre ya se usó, agrega un contador."""
        empleado = slip.employee_id
        base = f'{empleado.primer_nombre or ""} {empleado.primer_apellido or ""}'.strip()
        base = base or empleado.name or 'Empleado'
        base = base.replace('/', '-')
        periodo = slip.payslip_run_id.name or f'{slip.date_from}_{slip.date_to}'
        filename = f'{base} - {periodo}.pdf'
        contador = 2
        while filename in nombres_usados:
            filename = f'{base} - {periodo} ({contador}).pdf'
            contador += 1
        nombres_usados.add(filename)
        return filename
