from datetime import datetime

from odoo import models, fields, api
import base64
from io import BytesIO
import openpyxl

from odoo.exceptions import UserError


class HrPayslipWorkedDaysImportWizard(models.TransientModel):
    _name = 'hr.payslip.worked.days.import.wizard'
    _description = 'Importar Otras Entradas de Trabajo'

    file = fields.Binary(string='Archivo XLSX', required=True)
    filename = fields.Char(string='Nombre del Archivo')
    payslip_run_id = fields.Many2one('hr.payslip.run', string='Lote de Nómina', required=True)

    def import_file(self):
        if not self.payslip_run_id:
            raise UserError("No se ha encontrado el ID de la corrida de nómina.")
        """
        Importa el archivo XLSX y crea las líneas correspondientes en hr.payslip.worked_days
        """
        self.ensure_one()

        # Procesar el archivo XLSX
        if self.file:
            data = base64.b64decode(self.file)
            file_content = BytesIO(data)
            workbook = openpyxl.load_workbook(file_content, data_only=True)
            sheet = workbook.active

            headers = []
            for i, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                if i == 1:
                    headers = [cell for cell in row]
                elif row[0] is None or row[0] == 0:
                    continue
                else:
                    row_data = {headers[j]: cell for j, cell in enumerate(row)}
                    employee_id = int(row_data['Empleado/Identificación de la base de datos'])  # Ajustar según el encabezado exacto de tu XLSX
                    #x_fecha_pago = row_data['Fecha de pago']
                    fecha_pago= datetime.now().strftime('%d/%m/%Y')
                    try:
                        fecha_pago = row_data['Fecha de pago']
                    except:
                        fecha_pago = datetime.strptime(row_data['Fecha de pago'], '%d/%m/%Y').date()
                    # Iterar sobre las columnas restantes para obtener los montos
                    for key, monto in row_data.items():
                        if key in ['Empleado/Identificación de la base de datos', 'Código de empleado', 'Nombre del empleado', 'Fecha de pago']:
                            continue

                        codigo = key.strip()
                        monto = float(monto) if monto else 0.0

                        # Buscar el payslip correspondiente al empleado y la fecha de pago
                        payslip = self.env['hr.payslip'].search([
                            ('employee_id.id', '=', employee_id),
                            ('date_from', '<=', fecha_pago),
                            ('date_to', '>=', fecha_pago),
                            ('payslip_run_id.id', '=', self.payslip_run_id.id),
                            ('state', 'in', ['draft', 'verify'])
                        ], limit=1)

                        if not payslip:
                            continue  # Si no se encuentra el payslip, pasar al siguiente dato

                        # Buscar el input_type_id correspondiente al codigo
                        input_type = self.env['hr.payslip.input.type'].search([
                            ('name', '=', codigo)
                        ], limit=1)

                        if not input_type:
                            continue  # Si no se encuentra el tipo de entrada de trabajo, pasar al siguiente dato

                        # Crear la línea de entrada de trabajo en la nómina

                        # compronar si ya existe el registro, actualizarlo
                        input = self.env['hr.payslip.input'].search([
                            ('payslip_id', '=', payslip.id),
                            ('input_type_id', '=', input_type.id)
                        ], limit=1)
                        if input:
                            if monto == 0 or input.amount == 0:
                                input.unlink()
                            else:
                                input.amount = monto
                                input.name = 'Importado desde archivo XLSX, el '+str(datetime.now().strftime('%d %m %Y %H:%M:%S'))
                        else:
                            if monto != 0:
                                self.env['hr.payslip.input'].create({
                                    'payslip_id': payslip.id,
                                    'input_type_id': input_type.id,
                                    'amount': monto,
                                    # Fecha actual formato DD-MM-YYYY
                                    'name': 'Importado desde archivo XLSX, el '+str(datetime.now().strftime('%d %m %Y %H:%M:%S')),
                                })
                        payslip.compute_sheet()
                        # Buscar el work_entry_type_id correspondiente al codigo
                        # work_entry_type = self.env['hr.work.entry.type'].search([
                        #     ('name', '=', codigo)
                        # ], limit=1)
                        #
                        # if not work_entry_type:
                        #     continue  # Si no se encuentra el tipo de entrada de trabajo, pasar al siguiente dato
                        #
                        # # Crear la línea de días trabajados en la nómina
                        # self.env['hr.payslip.worked_days'].create({
                        #     'payslip_id': payslip.id,
                        #     'work_entry_type_id': work_entry_type.id,
                        #     'amount': monto,
                        #     'number_of_days': 0,  # Asignar un valor adecuado según tu lógica
                        #     'number_of_hours': 0  # Asignar un valor adecuado según tu lógica
                        # })


        return {}
