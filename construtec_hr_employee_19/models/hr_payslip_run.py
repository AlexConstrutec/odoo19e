import base64
import csv
import io

from odoo import models
from odoo.exceptions import UserError

CSV_HEADERS = [
    'Código Interno', 'Descripción', 'Cuenta Banrural a acreditar',
    'Tipo de cliente (1=Individual / 2=Jurídico)', '1er apellido', '2do apellido',
    '1er nombre', '2do nombre', 'Apellido de casada',
    'Nombre comercial (Solo si es Jurídico)',
]


class HrPayslipRun(models.Model):
    _inherit = 'hr.payslip.run'

    def action_generar_csv_banco(self):
        self.ensure_one()
        content, sin_cuenta = self._build_csv_banco()
        if sin_cuenta:
            raise UserError(self.env._(
                'Los siguientes empleados no tienen una cuenta Banrural registrada '
                '(Empleados > pestaña Trabajo/HR Settings > Cuentas bancarias) y no se '
                'puede generar el CSV hasta corregirlo:\n%s',
                '\n'.join(sin_cuenta),
            ))
        attachment = self.env['ir.attachment'].create({
            'name': f'CargaCuentas_{self.id}.csv',
            'type': 'binary',
            'datas': base64.b64encode(content),
            'res_model': self._name,
            'res_id': self.id,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    def _build_csv_banco(self):
        """Genera el contenido del CSV de carga de cuentas Banrural para este lote de
        nómina. Codificado en Windows-1252 (cp1252), no UTF-8: es lo que espera el
        portal de carga masiva de Banrural (confirmado contra un archivo real de
        referencia, que falla al decodificarse como UTF-8)."""
        self.ensure_one()
        output = io.StringIO()
        writer = csv.writer(output, delimiter=',', lineterminator='\r\n')
        writer.writerow(CSV_HEADERS)

        sin_cuenta_banrural = []
        for slip in self.slip_ids.sorted('id'):
            employee = slip.employee_id
            cuenta = employee.bank_account_ids.filtered(
                lambda b: b.bank_id and 'banrural' in (b.bank_id.name or '').lower())[:1]
            if not cuenta:
                sin_cuenta_banrural.append(f'{employee.name} ({employee.barcode or "sin código"})')
                continue
            writer.writerow([
                employee.barcode or '',
                self.name,
                cuenta.acc_number or '',
                '1',
                employee.primer_apellido or '',
                employee.segundo_apellido or '',
                employee.primer_nombre or '',
                employee.segundo_nombre or '',
                employee.apellido_casada or '',
                '',
            ])

        return output.getvalue().encode('cp1252'), sin_cuenta_banrural
