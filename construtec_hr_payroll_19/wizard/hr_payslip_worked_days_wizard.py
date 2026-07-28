import base64
from datetime import datetime
from io import BytesIO

import openpyxl

from odoo import fields, models
from odoo.exceptions import UserError

IGNORED_COLUMNS = (
    'Empleado/Identificación de la base de datos',
    'Código de empleado',
    'Nombre del empleado',
    'Fecha de pago',
)


class HrPayslipWorkedDaysImportWizard(models.TransientModel):
    _name = 'hr.payslip.worked.days.import.wizard'
    _description = 'Importar Otras Entradas de Trabajo'

    file = fields.Binary(string='Archivo XLSX', required=True)
    filename = fields.Char(string='Nombre del Archivo')
    payslip_run_id = fields.Many2one('hr.payslip.run', string='Lote de Nómina', required=True)

    def import_file(self):
        self.ensure_one()
        if not self.file:
            raise UserError(self.env._('Seleccione un archivo XLSX para importar.'))

        workbook = openpyxl.load_workbook(BytesIO(base64.b64decode(self.file)), data_only=True)
        sheet = workbook.active
        import_label = self.env._(
            'Importado desde archivo XLSX, el %s', fields.Datetime.now().strftime('%d/%m/%Y %H:%M:%S'))

        headers = []
        touched_payslips = self.env['hr.payslip']
        for i, row in enumerate(sheet.iter_rows(values_only=True), start=1):
            if i == 1:
                headers = list(row)
                continue
            if not row[0]:
                continue

            row_data = dict(zip(headers, row))
            employee_id = int(row_data['Empleado/Identificación de la base de datos'])
            fecha_pago = row_data.get('Fecha de pago')
            if isinstance(fecha_pago, str):
                try:
                    fecha_pago = datetime.strptime(fecha_pago, '%d/%m/%Y').date()
                except ValueError:
                    continue

            for key, monto in row_data.items():
                if key in IGNORED_COLUMNS:
                    continue
                codigo = key.strip()
                monto = float(monto) if monto else 0.0

                payslip = self.env['hr.payslip'].search([
                    ('employee_id', '=', employee_id),
                    ('date_from', '<=', fecha_pago),
                    ('date_to', '>=', fecha_pago),
                    ('payslip_run_id', '=', self.payslip_run_id.id),
                    ('state', '=', 'draft'),
                ], limit=1)
                if not payslip:
                    continue

                input_type = self.env['hr.payslip.input.type'].search([('name', '=', codigo)], limit=1)
                if not input_type:
                    continue

                existing = self.env['hr.payslip.input'].search([
                    ('payslip_id', '=', payslip.id),
                    ('input_type_id', '=', input_type.id),
                ], limit=1)
                if existing:
                    if monto:
                        existing.write({'amount': monto, 'name': import_label})
                    else:
                        existing.unlink()
                elif monto:
                    self.env['hr.payslip.input'].create({
                        'payslip_id': payslip.id,
                        'input_type_id': input_type.id,
                        'amount': monto,
                        'name': import_label,
                    })
                touched_payslips |= payslip

        touched_payslips.compute_sheet()
        return {}
