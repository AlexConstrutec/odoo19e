import base64
import csv
import io

from odoo import models

BANRURAL_CSV_HEADERS = [
    'Código Interno', 'Descripción', 'Cuenta Banrural a acreditar',
    'Tipo de cliente (1=Individual / 2=Jurídico)', '1er apellido', '2do apellido',
    '1er nombre', '2do nombre', 'Apellido de casada',
    'Nombre comercial (Solo si es Jurídico)',
]


class HrPayslipRun(models.Model):
    _inherit = 'hr.payslip.run'

    def action_generar_csv_banrural(self):
        self.ensure_one()
        content = self._build_csv_banrural()
        attachment = self.env['ir.attachment'].create({
            'name': f'CargaCuentasBanrural_{self.id}.csv',
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

    def _build_csv_banrural(self):
        """Genera el CSV de carga de cuentas Banrural para este lote de nómina.

        Ya NO bloquea la generación si algún empleado no tiene cuenta Banrural - en la nómina
        real conviven varios bancos, y bloquear todo el archivo por eso obligaba a corregir
        cuentas antes de poder generar nada. En su lugar: los empleados con cuenta Banrural van
        primero, listos para cargar tal cual al portal del banco; unas líneas en blanco más
        abajo se listan los empleados que NO tienen cuenta Banrural, con su banco real indicado
        en una columna extra - quien vaya a cargar el archivo simplemente borra esas filas antes
        de subirlo, en vez de tener que regenerar el archivo después de corregir cuentas.

        Codificado en Windows-1252 (cp1252), no UTF-8: es lo que espera el portal de carga
        masiva de Banrural (confirmado contra un archivo real de referencia, que falla al
        decodificarse como UTF-8)."""
        self.ensure_one()
        output = io.StringIO()
        writer = csv.writer(output, delimiter=',', lineterminator='\r\n')
        writer.writerow(BANRURAL_CSV_HEADERS)

        con_banrural = []
        sin_banrural = []
        for slip in self.slip_ids.sorted('id'):
            employee = slip.employee_id
            cuenta_banrural = employee.bank_account_ids.filtered(
                lambda b: b.bank_id and 'banrural' in (b.bank_id.name or '').lower())[:1]
            if cuenta_banrural:
                con_banrural.append((employee, cuenta_banrural))
            else:
                sin_banrural.append((employee, employee.bank_account_ids[:1]))

        for employee, cuenta in con_banrural:
            writer.writerow(self._csv_banrural_row(employee, cuenta))

        if sin_banrural:
            for _unused in range(3):
                writer.writerow([])
            writer.writerow([
                'EMPLEADOS SIN CUENTA BANRURAL - eliminar estas filas antes de cargar al banco'])
            writer.writerow(BANRURAL_CSV_HEADERS + ['Banco real'])
            for employee, cuenta in sin_banrural:
                banco = (
                    cuenta.bank_id.name if cuenta and cuenta.bank_id
                    else 'Sin cuenta bancaria registrada')
                writer.writerow(self._csv_banrural_row(employee, cuenta) + [banco])

        return output.getvalue().encode('cp1252')

    def _csv_banrural_row(self, employee, cuenta):
        return [
            employee.codigo_banco or '',
            self.name,
            cuenta.acc_number if cuenta else '',
            '1',
            employee.primer_apellido or '',
            employee.segundo_apellido or '',
            employee.primer_nombre or '',
            employee.segundo_nombre or '',
            employee.apellido_casada or '',
            '',
        ]
