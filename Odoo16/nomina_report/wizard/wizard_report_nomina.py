# -*- coding: utf-8 -*-
##############################################################################
#
# Copyright 2024 SIESA
#
##############################################################################
from decorator import append
from xlsxwriter.utility import xl_rowcol_to_cell
from collections import defaultdict
from odoo import models, api, fields, _
from odoo.exceptions import ValidationError
import xlsxwriter
import base64
from datetime import datetime, date
from calendar import monthrange
import tempfile
import os
import locale

import math
from odoo.tools.misc import formatLang

class WizardReportFacturacion(models.TransientModel):
    _name = 'wizard.report.facturacion'
    _description = "Wizard Report Facturacion"

    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id)
    # date_start = fields.Date('Del', required=True)
    # date_end = fields.Date('Al', required=True)
    planillas = fields.Many2many('hr.payslip.run', string='Lotes de Nómina', required=True)
    state = fields.Selection([('choose', 'choose'), ('get', 'get')], default='choose')
    name = fields.Char(string='File Name', readonly=True)
    data = fields.Binary(string='File', readonly=True)

    @api.onchange('company_id')
    def onchange_company_id(self):
        domain = [('company_id', '=', self.company_id.id)]
        return {'domain': {'company_id': domain}}

    def got_back(self):
        self.state = 'choose'
        return {
            'name': 'Reporte de Facturación',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def check_date(self):
        if self.date_end < self.date_start:
            raise ValidationError(_('La fecha de inicio no puede ser mayor que la fecha de finalización.'))
        # if self.date_start.year != self.date_end.year:
        #     raise ValidationError(_('El rango de fechas debe estar dentro del mismo año.'))

    def print_xls_reporte_facturacion(self):
        #self.check_date()

        xls_filename = 'Reporte de Facturación.xlsx'
        temp_dir = tempfile.gettempdir()
        xls_path = os.path.join(temp_dir, xls_filename)
        workbook = xlsxwriter.Workbook(xls_path)
        worksheet = workbook.add_worksheet('Reporte de Facturación')
        x_rows = 0
        # Configurar formatos
        header_format = workbook.add_format({'bold': True, 'font_size': 16, 'bg_color': '#d2996a'})
        cell_format = workbook.add_format({'bold': True, 'bg_color': '#d2996a'})
        worksheet.set_column('A:A', 40)
        worksheet.set_column('B:B', 40)
        worksheet.set_column('C:C', 30)
        worksheet.set_column('D:D', 30)
        worksheet.set_column('E:E', 12)
        worksheet.set_column('F:F', 12)
        worksheet.set_column('G:G', 12)
        worksheet.set_column('H:H', 20)
        worksheet.set_column('I:I', 20)
        worksheet.set_column('J:J', 20)
        # Escribir el encabezado
        worksheet.write('A1', 'Empresa Recibe', cell_format)
        worksheet.write('B1', 'Empresa Factura', cell_format)
        worksheet.write('C1', 'Departamento', cell_format)
        worksheet.write('D1', 'Centro de Costo', cell_format)
        worksheet.write('E1', 'Sueldos', cell_format)
        worksheet.write('F1', 'Prestaciones', cell_format)
        worksheet.write('G1', 'Alimentación', cell_format)
        worksheet.write('H1', 'Fac.Salarios', cell_format)
        worksheet.write('I1', 'Fac.Prestaciones', cell_format)
        worksheet.write('J1', 'Tipo Facturación', cell_format)

        #buscar los lotes
        x_lote_planillas = self.env['hr.payslip.run'].search([
            ('id', 'in', self.planillas.ids),
            ('company_id', '=', self.company_id.id)
        ])
        #buscar las nominas de los lotes
        pre_facturas = self.env['hr.payslip'].search([
            ('company_id', '=', self.company_id.id),
            ('payslip_run_id', 'in', x_lote_planillas.ids)
        ])
        # Ordenar los resultados por company_id.name
        x_facturas = pre_facturas.sorted(key=lambda r: (
            r.employee_id.contract_id.empresa_facturar.name or '',
            r.company_id.name or '',
            r.employee_id.contract_id.department_id.parent_id.name or '',
            r.employee_id.contract_id.analytic_account_id.name or ''
        ))
        if x_facturas:
            x_cuenta = self.env['account.analytic.account']
            grupo_nomina = defaultdict(list)
            for nominas in x_facturas:
                key = (
                    nominas.employee_id.contract_id.empresa_facturar.name or '',
                    nominas.company_id.name or '',
                    nominas.employee_id.contract_id.department_id.parent_id.name or '',
                    nominas.employee_id.contract_id.analytic_account_id or ''
                )
                grupo_nomina[key].append(nominas)
            for key, facturas in grupo_nomina.items():
                x_empresa_recibe, x_empresa_factura, x_departamento, x_cuenta_analitica = key
                if x_cuenta_analitica:
                    x_cuenta = self.env['account.analytic.account'].search([('id', '=', x_cuenta_analitica.id)])
                    x_name = '['+x_cuenta.code+'] '+x_cuenta.name
                else:
                    x_name = ''

                x_bruto = 0
                x_prestaciones = 0
                x_alimentación = 0
                for factura in facturas:
                    for regla in factura.line_ids:
                        if regla.code in ['GROSS', 'IGSS PAT', 'CIGSSPAT','IRTRA','INTECAP']:
                            x_bruto += regla.total
                        if regla.code in ['BONO14', 'AGUINALDO', 'INDM', 'VACAC']:
                            x_prestaciones += regla.total
                        if regla.code == 'MDOALIM':
                            x_alimentación += regla.total

                # x_bruto += (x_bruto + (x_bruto * 1.12))
                # x_prestaciones += (x_prestaciones + (x_prestaciones * 1.12))
                # x_alimentación += (x_alimentación + (x_alimentación * 1.12))
                    # x_empresa_facturar = factura.employee_id.contract_id.empresa_facturar.name if factura.employee_id.contract_id.empresa_facturar.name else ''
                    # x_empresa = factura.company_id.name if factura.company_id.name else ''
                    # x_departamento = factura.employee_id.contract_id.department_id.parent_id.name if factura.employee_id.contract_id.department_id.parent_id.name else ''
                    # x_cuenta_analitica = factura.employee_id.contract_id.analytic_account_id.name if factura.employee_id.contract_id.analytic_account_id.name else ''
                x_rows += 1
                worksheet.write(x_rows, 0, x_empresa_recibe)
                worksheet.write(x_rows, 1, x_empresa_factura)
                worksheet.write(x_rows, 2, x_departamento)
                worksheet.write(x_rows, 3, x_name)#cuenta Analitica
                worksheet.write(x_rows, 4, (x_bruto-x_alimentación)*1.12)
                worksheet.write(x_rows, 5, x_prestaciones*1.12)
                worksheet.write(x_rows, 6, x_alimentación*1.12)
                worksheet.write(x_rows, 7, '')
                worksheet.write(x_rows, 8, '')
                worksheet.write(x_rows, 9, x_cuenta.plan_id.name or '')
        else:
            #Encabezados
            worksheet.write('A1', 'Empresa Recibe', cell_format)
            worksheet.write('B1', 'Empresa Factura', cell_format)
            worksheet.write('C1', 'Departamento', cell_format)
            worksheet.write('D1', 'Centro de costo', cell_format)
            worksheet.write('E1', 'Sueldos', cell_format)
            worksheet.write('F1', 'Prestaciones', cell_format)
            worksheet.write('G1', 'Alimentación', cell_format)
            worksheet.write('H1', 'Fac.Salarios', cell_format)
            worksheet.write('I1', 'Fac.Prestaciones', cell_format)
            worksheet.write('J1', 'Tipo Facturación', cell_format)

        x_rows += 1

        # Escribir los datos

        workbook.close()
        self.write(
            {
                'state': 'get',
                'name': xls_filename,
                'data': base64.b64encode(open(xls_path, 'rb').read())
            }
        )
        return {
            'name': 'Reporte de Facturación',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new',
        }

class WizardLibroSueldosSalarios(models.TransientModel):
    _name = 'wizard.libro.sueldos.salarios'
    _description = "Wizard Libro de Sueldos y Salarios "

    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id)
    date_start = fields.Date('Del', required=True)
    date_end = fields.Date('Al', required=True)
    #employee_id = fields.Many2one('hr.employee', string='Empleado', required=True )
    state = fields.Selection([('choose', 'choose'), ('get', 'get')], default='choose')
    name = fields.Char(string='File Name', readonly=True)
    data = fields.Binary(string='File', readonly=True)
    folio = fields.Integer('Folio', required=True)

    @api.onchange('company_id')
    def onchange_company_id(self):
        domain = [('company_id', '=', self.company_id.id)]
        return {'domain': {'company_id': domain}}

    def got_back(self):
        self.state = 'choose'
        return {
            'name': 'Libro de Sueldos y Salarios ',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def check_date(self):
        if self.date_end < self.date_start:
            raise ValidationError(_('La fecha de inicio no puede ser mayor que la fecha de finalización.'))
        # if self.date_start.year != self.date_end.year:
        #     raise ValidationError(_('El rango de fechas debe estar dentro del mismo año.'))

    def print_xls_libro_sueldos_salarios(self):
        self.check_date()
        xls_filename = 'Libro de Sueldos y Salarios.xlsx'
        temp_dir = tempfile.gettempdir()
        xls_path = os.path.join(temp_dir, xls_filename)
        workbook = xlsxwriter.Workbook(xls_path)
        worksheet = workbook.add_worksheet("Libro de Sueldos y Salarios")
        worksheet.set_landscape()
        worksheet.set_page_view()
        worksheet.set_paper(5)
        worksheet.set_margins(0.7, 0.7, 0.7, 0.7)
        worksheet.set_column('A:A', 1)
        worksheet.set_column('B:B', 4)
        worksheet.set_column('C:C', 6)
        worksheet.set_column('D:D', 6)
        worksheet.set_column('E:E', 6)
        worksheet.set_column('F:F', 6)
        worksheet.set_column('G:G', 6)
        worksheet.set_column('H:H', 6)
        worksheet.set_column('I:I', 6)
        worksheet.set_column('J:J', 6)
        worksheet.set_column('K:K', 6)
        worksheet.set_column('L:L', 6)
        worksheet.set_column('M:M', 6)
        worksheet.set_column('N:N', 6)
        worksheet.set_column('O:O', 6)
        worksheet.set_column('P:P', 6)
        worksheet.set_column('Q:Q', 6)
        worksheet.set_column('R:R', 6)
        worksheet.set_column('S:S', 8)
        worksheet.set_column('T:T', 7)
        worksheet.set_column('U:U', 6)
        worksheet.set_column('V:V', 6)
        worksheet.set_column('W:W', 6)
        worksheet.set_column('X:X', 6)
        worksheet.set_column('Y:Y', 1)

        x_recorre = 0
        x_max_rows = 35  # Maximo de lineas por pagina
        x_row_page = 0  # Linea actual vrs maximo de lineas

        # Tamaño de columnas

        # Detalles
        frmt_folio = workbook.add_format({'bold': True, 'align': 'right', 'font': 'Arial', 'font_size': 6})
        frmt_encabezado = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'font': 'Arial', 'font_size': 6})
        frmt_encabezado_columna = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'font': 'Arial', 'font_size': 6, 'border': 1, 'bg_color': '#DDEBF7', 'text_wrap': True})
        detail_emp_1 = workbook.add_format({'bold': True, 'align': 'center', 'font': 'Arial', 'font_size': 6, 'bottom': 1})
        detail_emp_2 = workbook.add_format({'align': 'center', 'font': 'Arial', 'font_size': 6, 'border': 1})
        detail_emp_3 = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 6, 'border': 1, 'num_format': 'Q#,##0.00'})

        pre_nominas = self.env['hr.payslip'].search([
            ('date_from', '>=', self.date_start),
            ('date_to', '<=', self.date_end),
            ('company_id', '=', self.company_id.id),
            ('state', 'in', ['verify', 'done', 'paid'])
        ])
        nominas = pre_nominas.sorted(
            key=lambda x: (x.employee_id.name, -x.date_from.toordinal())
        )
        if nominas:
            x_rows = 0
            aux_employee = None
            x_count_nomina = 0
            a_imprimir = []
            x_altura = 0
            for nomina in nominas:
                if aux_employee != nomina.employee_id:
                    x_count_nomina = 0
                    aux_employee = nomina.employee_id
                x_count_nomina += 1
                a_imprimir.append([])
                a_imprimir[x_altura].append(nomina.employee_id.name)  # Nombre del trabajador
                # a_imprimir[x_altura].append((date.today() - nomina.employee_id.birthday).days // 365)  # Edad
                if nomina.employee_id.birthday:
                    age = (date.today() - nomina.employee_id.birthday).days // 365
                else:
                    age = 0  # or any default value you prefer
                a_imprimir[x_altura].append(age)
                genero = ''
                if nomina.employee_id.gender == 'female':
                    genero = 'Femenino'
                elif nomina.employee_id.gender == 'male':
                    genero = 'Masculino'
                else:
                    genero = ''
                a_imprimir[x_altura].append(genero) # Genero
                a_imprimir[x_altura].append(nomina.employee_id.country_of_birth.name) # Nacionalidad
                a_imprimir[x_altura].append(nomina.employee_id.job_title) # Ocupación o puesto que desempeña
                a_imprimir[x_altura].append(nomina.employee_id.igss if nomina.employee_id.igss else '') # IGSS
                a_imprimir[x_altura].append(nomina.employee_id.identification_id if nomina.employee_id.identification_id else '')  # No. DPI ó permiso de trabajo
                a_imprimir[x_altura].append(nomina.employee_id.contract_id.date_start if nomina.employee_id.contract_id else nomina.employee_id.first_contract_date) # Inicio de relación laboral
                a_imprimir[x_altura].append(nomina.employee_id.contract_id.date_end) # Fecha de finalización de relación laboral

                a_imprimir[x_altura].append(x_count_nomina) # No de pago
                a_imprimir[x_altura].append(nomina.date_from.strftime('%d-%m-%Y')) # Perido de trabajo
                a_imprimir[x_altura].append(nomina.date_to.strftime('%d-%m-%Y')) # Perido de trabajo
                a_imprimir[x_altura].append(sum(line.total for line in nomina.line_ids if line.code == 'BASIC')) # Salario base
                a_imprimir[x_altura].append((nomina.date_to - nomina.date_from).days +1) # Dias trabajados
                a_imprimir[x_altura].append(((nomina.date_to - nomina.date_from).days +1) * 8) # Horas ordinarias
                extraordinarias = 0
                if '100HE' in nomina.struct_id.name:
                    if nomina.contract_id.horas_extra_valor > 0 and sum(line.total for line in nomina.line_ids if line.code == 'VHEB')>0:
                        extraordinarias = sum(line.total for line in nomina.line_ids if line.code == 'VHEB')/nomina.contract_id.horas_extra_valor
                    else:
                        extraordinarias = 0
                elif '100BH' in nomina.struct_id.name:
                    if sum(worked_day.number_of_hours for worked_day in nomina.worked_days_line_ids if worked_day.work_entry_type_id.code == 'HORAEXTRA') > 60:
                        extraordinarias = sum(worked_day.number_of_hours for worked_day in nomina.worked_days_line_ids if worked_day.work_entry_type_id.code == 'HORAEXTRA') - 60
                    else:
                        extraordinarias = 0
                else:
                    extraordinarias = 0
                a_imprimir[x_altura].append(extraordinarias) # Horas extraordinarias
                a_imprimir[x_altura].append(sum(line.total for line in nomina.line_ids if line.code == 'BASIC')) # Salario devengado ordinario
                a_imprimir[x_altura].append(sum(line.total for line in nomina.line_ids if line.code == 'VHEB')) # Salario devengado extraordinario
                a_imprimir[x_altura].append(0)  # Salario devengado otros salarios
                a_imprimir[x_altura].append(0)  # Salario devengado septimos y asuetos
                a_imprimir[x_altura].append(sum(line.total for line in nomina.line_ids if line.code == 'VACACPAG'))  # Salario devengado vacaciones
                a_imprimir[x_altura].append(sum(line.total for line in nomina.line_ids if line.code == 'BASIC') + sum(line.total for line in nomina.line_ids if line.code == 'VHEB') + sum(line.total for line in nomina.line_ids if line.code == 'VACACPAG'))  # Salario total
                a_imprimir[x_altura].append(sum(line.total for line in nomina.line_ids if line.code == 'IGSSLABR' or line.code == 'CIGSSLAB'))  # Deducciones legales - Cuota laboral IGSS
                a_imprimir[x_altura].append(sum(line.total for line in nomina.line_ids if line.code == 'ISRASA'))  # Deducciones legales - Descuentos ISR
                a_imprimir[x_altura].append(sum(line.total for line in nomina.line_ids if line.code in ['ANT1', 'ANT2', 'ANT3']))
                a_imprimir[x_altura].append(sum(line.total for line in nomina.line_ids if line.code in ['ANT1', 'ANT2', 'ANT3']) + sum(line.total for line in nomina.line_ids if line.code == 'IGSSLABR') + sum(line.total for line in nomina.line_ids if line.code == 'ISRASA'))  # Deducciones legales - Total deducciones
                a_imprimir[x_altura].append(sum(line.total for line in nomina.line_ids if line.code in ['AGUINALDOP', 'BONO14P']))  # Bonificación anual 42-92, Aguinaldo Decreto 76-78
                a_imprimir[x_altura].append(sum(line.total for line in nomina.line_ids if line.code in ['BONIN', 'BOFIJ', 'BONPRO', 'OTREN', 'MDOA', 'MDOAS', 'BHE', 'MDOALIM']))  # Bonificación Incentivo Decreto 37-2001
                a_imprimir[x_altura].append(sum(line.total for line in nomina.line_ids if line.code == 'DEVISR' or line.code == 'INDEMP'))  # Devoluciones I.S.R. y otras
                a_imprimir[x_altura].append(sum(line.total for line in nomina.line_ids if line.code == 'NET'))  # Salario Liquido
                if nomina.payment_ids:
                    a_imprimir[x_altura].append(nomina.payment_ids[0].ref)
                else:
                    a_imprimir[x_altura].append('')
                #a_imprimir[x_altura].append(nomina.payment_ids[0].communication if nomina.payment_ids[0] else '')  #  Firma o número de boleta de pago / váucher.
                a_imprimir[x_altura].append('')  # Observaciones
                x_altura += 1
            aux_employee = None
            while x_recorre < len(a_imprimir):
                if x_row_page < x_max_rows:
                    if aux_employee != a_imprimir[x_recorre][0]:
                        aux_employee = a_imprimir[x_recorre][0]
                        if x_recorre > 0:
                            x_rows += ((x_max_rows)-x_row_page)
                            x_row_page = x_max_rows - 1
                    if x_row_page >= x_max_rows - 1:
                        x_row_page = 0
                        self.folio += 1
                    if x_row_page == 0:  # Nueva pagina
                        # Encabezado
                        worksheet.write(x_rows, 22, 'Folio No.', frmt_folio)
                        worksheet.write(x_rows, 23, str(self.folio) + 'E', frmt_folio)
                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 1, x_rows, 24, self.company_id.name, frmt_encabezado)
                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 1, x_rows, 24, "NIT: " + self.company_id.vat, frmt_encabezado)
                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 1, x_rows, 22, "LIBRO COMPUTARIZADO PARA LA OPERACIÓN DE SALARIOS DE TRABAJADORES PERMANENTES, AUTORIZADO POR EL MINISTERIO DE TRABAJO Y ",                                              frmt_encabezado)
                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 1, x_rows, 22, "PREVISION SOCIAL, FUNDAMENTO LEGAL: ARTÍCULOS 102 DEL DECRETO No. 1441 Y 2 DEL ACUERDO MINISTERIAL No. 124-2019 ", frmt_encabezado)
                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 1, x_rows, 5, a_imprimir[x_recorre][0], detail_emp_1)
                        worksheet.write(x_rows, 9, a_imprimir[x_recorre][1], detail_emp_1)
                        worksheet.merge_range(x_rows, 12, x_rows, 13, a_imprimir[x_recorre][2], detail_emp_1)
                        worksheet.merge_range(x_rows, 15, x_rows, 18, a_imprimir[x_recorre][3], detail_emp_1)
                        worksheet.merge_range(x_rows, 20, x_rows, 23, a_imprimir[x_recorre][4], detail_emp_1)
                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 1, x_rows, 5, "Nombre del trabajador", frmt_encabezado)
                        worksheet.write(x_rows, 9, "Edad", frmt_encabezado)
                        worksheet.merge_range(x_rows, 12, x_rows, 13, "Género", frmt_encabezado)
                        worksheet.merge_range(x_rows, 15, x_rows, 18, "Nacionalidad", frmt_encabezado)
                        worksheet.merge_range(x_rows, 20, x_rows, 23, "Ocupación o puesto que desempeña", frmt_encabezado)
                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 1, x_rows, 5, a_imprimir[x_recorre][5], detail_emp_1)
                        worksheet.merge_range(x_rows, 8, x_rows, 10, a_imprimir[x_recorre][6], detail_emp_1)
                        worksheet.merge_range(x_rows, 15, x_rows, 18, a_imprimir[x_recorre][7].strftime('%d-%m-%Y') if a_imprimir[x_recorre][7] else '', detail_emp_1)
                        worksheet.merge_range(x_rows, 20, x_rows, 23, a_imprimir[x_recorre][8].strftime('%d-%m-%Y') if a_imprimir[x_recorre][8] else '',detail_emp_1)
                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 1, x_rows, 5, "No. de afiliación al IGSS.", frmt_encabezado)
                        worksheet.merge_range(x_rows, 8, x_rows, 10, "No. DPI ó permiso de trabajo.", frmt_encabezado)
                        worksheet.merge_range(x_rows, 15, x_rows, 18, "Inicio de relación laboral", frmt_encabezado)
                        worksheet.merge_range(x_rows, 20, x_rows, 23, "Fecha de finalización de relación laboral", frmt_encabezado)
                        x_rows += 2
                        x_row_page += 2
                        x_row_aux = x_rows + 3
                        worksheet.merge_range(x_rows, 1, x_row_aux, 1, "Pago", frmt_encabezado_columna)
                        worksheet.merge_range(x_rows, 2, x_row_aux, 3, "Periodo de trabajo ", frmt_encabezado_columna)
                        worksheet.merge_range(x_rows, 4, x_row_aux, 4, "Salario en Quetzales", frmt_encabezado_columna)
                        worksheet.merge_range(x_rows, 5, x_row_aux, 5, "Días trabajados", frmt_encabezado_columna)
                        worksheet.merge_range(x_rows, 6, x_rows, 7, "HORAS TRABAJADAS", frmt_encabezado_columna)
                        worksheet.merge_range(x_rows + 1, 6, x_row_aux, 6, "Ordinarias", frmt_encabezado_columna)
                        worksheet.merge_range(x_rows + 1, 7, x_row_aux, 7, "Extraordinarias", frmt_encabezado_columna)
                        worksheet.merge_range(x_rows, 8, x_rows, 12, "SALARIO DEVENGADO", frmt_encabezado_columna)
                        worksheet.merge_range(x_rows + 1, 8, x_row_aux, 8, "Ordinario", frmt_encabezado_columna)
                        worksheet.merge_range(x_rows + 1, 9, x_row_aux, 9, "Extraordinario", frmt_encabezado_columna)
                        worksheet.merge_range(x_rows + 1, 10, x_row_aux, 10, "Otros Salarios", frmt_encabezado_columna)
                        worksheet.merge_range(x_rows + 1, 11, x_row_aux, 11, "Séptimos y asuetos", frmt_encabezado_columna)
                        worksheet.merge_range(x_rows + 1, 12, x_row_aux, 12, "Vacaciones", frmt_encabezado_columna)
                        worksheet.merge_range(x_rows, 13, x_row_aux, 13, "Salario Total", frmt_encabezado_columna)
                        worksheet.merge_range(x_rows, 14, x_rows, 17, "DEDUCCIONES LEGALES", frmt_encabezado_columna)
                        worksheet.merge_range(x_rows + 1, 14, x_row_aux, 14, "Cuota laboral IGSS", frmt_encabezado_columna)
                        worksheet.merge_range(x_rows + 1, 15, x_row_aux, 15, "Descuentos ISR", frmt_encabezado_columna)
                        worksheet.merge_range(x_rows + 1, 16, x_row_aux, 16, "Otras Deducciones", frmt_encabezado_columna)
                        worksheet.merge_range(x_rows + 1, 17, x_row_aux, 17, "Total", frmt_encabezado_columna)
                        worksheet.merge_range(x_rows, 18, x_row_aux, 18, "Bonificación anual 42-92, Aguinaldo Decreto 76-78", frmt_encabezado_columna)
                        worksheet.merge_range(x_rows, 19, x_row_aux, 19, "Bonificación Incentivo Decreto 37-2001", frmt_encabezado_columna)
                        worksheet.merge_range(x_rows, 20, x_row_aux, 20, "Devoluciones I.S.R. y otras", frmt_encabezado_columna)
                        worksheet.merge_range(x_rows, 21, x_row_aux, 21, "Salario Liquido", frmt_encabezado_columna)
                        worksheet.merge_range(x_rows, 22, x_row_aux, 22, "Firma o número de boleta de pago / váucher.", frmt_encabezado_columna)
                        worksheet.merge_range(x_rows, 23, x_row_aux, 23, "Observaciones", frmt_encabezado_columna)
                        x_rows += 4
                        x_row_page += 4
                    worksheet.write(x_rows, 1, a_imprimir[x_recorre][9], detail_emp_2)
                    worksheet.write(x_rows, 2, a_imprimir[x_recorre][10], detail_emp_2)
                    worksheet.write(x_rows, 3, a_imprimir[x_recorre][11], detail_emp_2)
                    worksheet.write(x_rows, 4, a_imprimir[x_recorre][12], detail_emp_3)
                    worksheet.write(x_rows, 5, a_imprimir[x_recorre][13], detail_emp_2)
                    worksheet.write(x_rows, 6, a_imprimir[x_recorre][14], detail_emp_2)
                    worksheet.write(x_rows, 7, a_imprimir[x_recorre][15], detail_emp_2)
                    worksheet.write(x_rows, 8, a_imprimir[x_recorre][16], detail_emp_3)
                    worksheet.write(x_rows, 9, a_imprimir[x_recorre][17], detail_emp_3)
                    worksheet.write(x_rows, 10, a_imprimir[x_recorre][18], detail_emp_3)
                    worksheet.write(x_rows, 11, a_imprimir[x_recorre][19], detail_emp_3)
                    worksheet.write(x_rows, 12, a_imprimir[x_recorre][20], detail_emp_3)
                    worksheet.write(x_rows, 13, a_imprimir[x_recorre][21], detail_emp_3)
                    worksheet.write(x_rows, 14, a_imprimir[x_recorre][22], detail_emp_3)
                    worksheet.write(x_rows, 15, a_imprimir[x_recorre][23], detail_emp_3)
                    worksheet.write(x_rows, 16, a_imprimir[x_recorre][24], detail_emp_3)
                    worksheet.write(x_rows, 17, a_imprimir[x_recorre][25], detail_emp_3)
                    worksheet.write(x_rows, 18, a_imprimir[x_recorre][26], detail_emp_3)
                    worksheet.write(x_rows, 19, a_imprimir[x_recorre][27], detail_emp_3)
                    worksheet.write(x_rows, 20, a_imprimir[x_recorre][28], detail_emp_3)
                    worksheet.write(x_rows, 21, a_imprimir[x_recorre][29], detail_emp_3)
                    worksheet.write(x_rows, 22, a_imprimir[x_recorre][30], detail_emp_2)
                    worksheet.write(x_rows, 23, a_imprimir[x_recorre][31], detail_emp_2)
                    x_recorre += 1
                    x_rows += 1
                    x_row_page += 1
        workbook.close()
        self.write(
            {
                'state': 'get',
                'name': xls_filename,
                'data': base64.b64encode(open(xls_path, 'rb').read())
            }
        )
        return {
            'name': 'Libro de Sueldos y Salarios',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new',
        }

class WizardReportePrestacionesLaborales(models.TransientModel):
    _name = 'wizard.reporte.prestaciones.laborales'
    _description = "Wizard Reporte Prestaciones Laborales"

    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id)
    date_start = fields.Date('Del', required=True)
    date_end = fields.Date('Al', required=True)
    employee_id = fields.Many2many('hr.employee', string='Empleado', required=True )
    state = fields.Selection([('choose', 'choose'), ('get', 'get')], default='choose')
    name = fields.Char(string='File Name', readonly=True)
    data = fields.Binary(string='File', readonly=True)

    @api.onchange('company_id')
    def onchange_company_id(self):
        domain = [('company_id', '=', self.company_id.id)]
        return {'domain': {'company_id': domain}}

    def got_back(self):
        self.state = 'choose'
        return {
            'name': 'Reporte de Prestaciones Laborales',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def check_date(self):
        if self.date_end < self.date_start:
            raise ValidationError(_('La fecha de inicio no puede ser mayor que la fecha de finalización.'))
        # if self.date_start.year != self.date_end.year:
        #     raise ValidationError(_('El rango de fechas debe estar dentro del mismo año.'))

    def print_xls_reporte_prestaciones_laborales(self):
        self.check_date()
        # locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')
        xls_filename = 'Reporte de Prestaciones Laborales.xlsx'
        temp_dir = tempfile.gettempdir()
        xls_path = os.path.join(temp_dir, xls_filename)
        workbook = xlsxwriter.Workbook(xls_path)
        worksheet = workbook.add_worksheet("Reporte de Prestaciones Laborales")
        frmt_folio = workbook.add_format({'bold': True, 'align': 'right', 'font': 'Arial', 'font_size': 6})
        frmt_encabezado = workbook.add_format(
            {'bold': True, 'align': 'center', 'valign': 'vcenter', 'font': 'Arial', 'font_size': 6})
        frmt_encabezado_columna = workbook.add_format(
            {'bold': True, 'align': 'center', 'valign': 'vcenter', 'font': 'Arial', 'font_size': 6, 'border': 1,
             'bg_color': '#DDEBF7', 'text_wrap': True})
        detail_emp_1 = workbook.add_format({'bold': True, 'align': 'center', 'font': 'Arial', 'font_size': 6})
        # construir el libro en este espacio de trabajo
        # Tamaño de columnas
        worksheet.set_column('E:E', 20)
        worksheet.set_column('F:F', 12)
        worksheet.set_column('G:G', 15)
        worksheet.set_column('J:J', 15)
        # Encabezados
        worksheet.write('A1', 'Mes', frmt_encabezado_columna)
        worksheet.write('B1', 'Fecha Del', frmt_encabezado_columna)
        worksheet.write('C1', 'Fecha Al', frmt_encabezado_columna)
        worksheet.write('D1', 'Referendia de Nómina', frmt_encabezado_columna)
        worksheet.write('E1', 'Nombre de Empleado', frmt_encabezado_columna)
        worksheet.write('F1', 'Departamento', frmt_encabezado_columna)
        worksheet.write('G1', 'Area', frmt_encabezado_columna)
        worksheet.write('H1', 'Fecha de Contrato', frmt_encabezado_columna)
        worksheet.write('I1', 'Status', frmt_encabezado_columna)
        worksheet.write('J1', 'Puesto', frmt_encabezado_columna)
        worksheet.write('K1', 'Bono Anual', frmt_encabezado_columna)
        worksheet.write('L1', 'Aguinaldo', frmt_encabezado_columna)
        worksheet.write('M1', 'Indemnizacion', frmt_encabezado_columna)
        worksheet.write('N1', 'Vacaciones', frmt_encabezado_columna)
        worksheet.write('O1', 'Total reserva de prestaciones', frmt_encabezado_columna)

        x_rows = 1
        x_nomina = self.env['hr.payslip'].search([
            ('date_from', '>=', self.date_start),
            ('date_to', '<=', self.date_end),
            ('company_id', '=', self.company_id.id),
            ('employee_id', 'in', self.employee_id.ids),
            ('state', 'in', ['done', 'paid'])
        ])
        if x_nomina:
            for nomina in x_nomina:
                x_suma_bono_14 = 0
                x_suma_aguinaldo = 0
                x_suma_indemnizacion = 0
                x_suma_vacaciones = 0
                x_total_prestaciones = 0
                for x_line in nomina.line_ids:
                    if x_line.code == 'BONO14':
                        x_suma_bono_14 += x_line.total
                    elif x_line.code == 'BONO14P':
                        x_suma_bono_14 -= x_line.total
                    elif x_line.code == 'AGUINALDO':
                        x_suma_aguinaldo += x_line.total
                    elif x_line.code == 'AGUINALDOP':
                        x_suma_aguinaldo -= x_line.total
                    elif x_line.code == 'INDM':
                        x_suma_indemnizacion += x_line.total
                    elif x_line.code == 'INDEMP':
                        x_suma_indemnizacion -= x_line.total
                    elif x_line.code == 'VACAC':
                        x_suma_vacaciones += x_line.total
                    elif x_line.code == 'VACACPAG':
                        x_suma_vacaciones -= x_line.total
                x_total_prestaciones = x_suma_bono_14 + x_suma_aguinaldo + x_suma_indemnizacion + x_suma_vacaciones

                # worksheet.write(x_rows, 0, nomina.date.strftime('%B'), detail_emp_1)
                if nomina.date:
                    x_mes = nomina.date.month
                else:
                    x_mes = ''
                if nomina.date_from:
                    x_del = nomina.date_from.strftime('%d-%m-%Y')
                else:
                    x_del = ''
                if nomina.date_to:
                    x_al = nomina.date_to.strftime('%d-%m-%Y')
                else:
                    x_al = ''
                if nomina.employee_id.first_contract_date:
                    x_contrato = nomina.employee_id.first_contract_date.strftime('%d-%m-%Y')
                else:
                    x_contrato = ''
                if nomina.employee_id.contract_id.estado_contrato:
                    x_estado_contrato = nomina.employee_id.contract_id.estado_contrato.name
                else:
                    x_estado_contrato = ''
                if nomina.number:
                    x_referencia = nomina.number
                else:
                    x_referencia = ''
                worksheet.write(x_rows, 0, x_mes, detail_emp_1)
                worksheet.write(x_rows, 1, x_del, detail_emp_1)
                worksheet.write(x_rows, 2, x_al, detail_emp_1)
                worksheet.write(x_rows, 3, x_referencia, detail_emp_1)
                worksheet.write(x_rows, 4, nomina.employee_id.name, detail_emp_1)
                worksheet.write(x_rows, 5, nomina.employee_id.contract_id.department_id.parent_id.name,
                                detail_emp_1)  # Departamento
                worksheet.write(x_rows, 6, nomina.employee_id.department_id.name, detail_emp_1)  # Area
                worksheet.write(x_rows, 7, x_contrato, detail_emp_1)
                worksheet.write(x_rows, 8, x_estado_contrato, detail_emp_1)
                worksheet.write(x_rows, 9, nomina.employee_id.job_title, detail_emp_1)  # Puesto
                worksheet.write(x_rows, 10, x_suma_bono_14, detail_emp_1)
                worksheet.write(x_rows, 11, x_suma_aguinaldo, detail_emp_1)
                worksheet.write(x_rows, 12, x_suma_indemnizacion, detail_emp_1)
                worksheet.write(x_rows, 13, x_suma_vacaciones, detail_emp_1)
                worksheet.write(x_rows, 14, x_total_prestaciones, detail_emp_1)
                x_rows += 1

        workbook.close()
        self.write(
            {
                'state': 'get',
                'name': xls_filename,
                'data': base64.b64encode(open(xls_path, 'rb').read())
            }
        )
        return {
            'name': 'Reporte de Prestaciones Laborales',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new',
        }

class WizardReportePlanillaIGSS(models.TransientModel):
    _name = 'wizard.reporte.planilla.igss'
    _description = "Wizard Reporte Planilla IGSS"

    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id)
    date_start = fields.Date('Del', required=True)
    date_end = fields.Date('Al', required=True)
    #employee_id = fields.Many2one('hr.employee', string='Empleado', required=True)
    state = fields.Selection([('choose', 'choose'), ('get', 'get')], default='choose')
    name = fields.Char(string='File Name', readonly=True)
    data = fields.Binary(string='File', readonly=True)

    @api.onchange('company_id')
    def onchange_company_id(self):
        domain = [('company_id', '=', self.company_id.id)]
        return {'domain': {'company_id': domain}}

    def got_back(self):
        self.state = 'choose'
        return {
            'name': 'Reporte Planilla IGSS',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def check_date(self):
        if self.date_end < self.date_start:
            raise ValidationError(_('La fecha de inicio no puede ser mayor que la fecha de finalización.'))
        # if self.date_start.year != self.date_end.year:
        #     raise ValidationError(_('El rango de fechas debe estar dentro del mismo año.'))

    def get_selection_label(self, record, field_name):
        # Obtén la definición del campo
        field = record._fields[field_name]
        # Obtén el valor actual del campo
        value = getattr(record, field_name)
        # Busca la etiqueta correspondiente al valor
        label = dict(field.selection).get(value)
        return label
    def print_xls_reporte_planilla_igss(self):
        self.check_date()
        xls_filename = 'Reporte Planilla IGSS.xlsx'
        temp_dir = tempfile.gettempdir()
        xls_path = os.path.join(temp_dir, xls_filename)
        workbook = xlsxwriter.Workbook(xls_path)
        worksheet = workbook.add_worksheet("Reporte de Planilla IGSS")
        frmt_folio = workbook.add_format({'bold': True, 'align': 'right', 'font': 'Arial', 'font_size': 6})
        frmt_encabezado = workbook.add_format(
            {'bold': True, 'align': 'center', 'valign': 'vcenter', 'font': 'Arial', 'font_size': 11})
        frmt_encabezado_columna = workbook.add_format(
            {'bold': True, 'align': 'center', 'valign': 'vcenter', 'font': 'Arial', 'font_size': 10, 'border': 1,
             'bg_color': '#DDEBF7', 'text_wrap': True})
        detail_emp_1 = workbook.add_format(
            { 'align': 'center', 'font': 'Arial', 'font_size': 11, 'border': 1, 'valign': 'vcenter'})

        # configuracion columnas
        worksheet.set_column('A:A', 15)
        worksheet.set_column('B:B', 15)
        worksheet.set_column('C:C', 15)
        worksheet.set_column('D:D', 30)
        worksheet.set_column('E:E', 10)
        worksheet.set_column('F:F', 10)
        worksheet.set_column('G:G', 11)
        worksheet.set_column('H:H', 10)
        worksheet.set_column('I:I', 10)
        worksheet.set_column('J:J', 10)
        worksheet.set_column('K:K', 10)
        worksheet.set_column('L:L', 10)
        worksheet.set_column('M:M', 10)
        worksheet.set_column('N:N', 10)
        worksheet.set_column('O:O', 18)
        worksheet.set_column('P:P', 18)
        worksheet.set_column('Q:Q', 18)
        worksheet.set_column('R:R', 18)
        worksheet.set_column('S:S', 18)
        worksheet.set_column('T:T', 18)
        # Encabezados
        x_rows = 0
        worksheet.merge_range(x_rows, 0, x_rows, 17, 'Planilla IGSS', frmt_encabezado)
        x_rows += 1
        worksheet.merge_range(x_rows, 0, x_rows, 17, self.company_id.name, frmt_encabezado)
        x_rows += 1
        worksheet.merge_range(x_rows, 0, x_rows, 17, 'Del: '+str(self.date_start)+' Al: '+str(self.date_end), frmt_encabezado)
        x_rows += 2
        worksheet.write(x_rows, 0, 'Inicio de contrato', frmt_encabezado_columna)
        worksheet.write(x_rows, 1, 'Fin de contrato', frmt_encabezado_columna)
        worksheet.write(x_rows, 2, 'No. Afiliación', frmt_encabezado_columna)
        worksheet.write(x_rows, 3, 'Nombres y Apellidos', frmt_encabezado_columna)
        worksheet.write(x_rows, 4, 'Salario Base', frmt_encabezado_columna)
        worksheet.write(x_rows, 5, 'Horas Extras', frmt_encabezado_columna)
        worksheet.write(x_rows, 6, 'Vacaciones', frmt_encabezado_columna)
        worksheet.write(x_rows, 7, 'Total', frmt_encabezado_columna)
        worksheet.write(x_rows, 8, 'IGSS Laboral', frmt_encabezado_columna)
        worksheet.write(x_rows, 9, 'Complemento IGSS Laboral', frmt_encabezado_columna)
        worksheet.write(x_rows, 10, 'IGSS Patronal', frmt_encabezado_columna)
        worksheet.write(x_rows, 11, 'Complemento IGSS Patronal', frmt_encabezado_columna)
        worksheet.write(x_rows, 12, 'IRTRA', frmt_encabezado_columna)
        worksheet.write(x_rows, 13, 'INTECAP', frmt_encabezado_columna)
        worksheet.write(x_rows, 14, 'Departamento', frmt_encabezado_columna)
        worksheet.write(x_rows, 15, 'Área', frmt_encabezado_columna)
        worksheet.write(x_rows, 16, 'Puesto', frmt_encabezado_columna)
        worksheet.write(x_rows, 17, 'Tempo de Contrato', frmt_encabezado_columna)
        worksheet.write(x_rows, 18, 'Cantidad de Dias laborados en el mes', frmt_encabezado_columna)
        worksheet.write(x_rows, 19, 'Cantidad horas laborados del mes.', frmt_encabezado_columna)
        # construir el libro en este espacio de trabajo
        x_nomina = self.env['hr.payslip'].search([
            ('date_from', '>=', self.date_start),
            ('date_to', '<=', self.date_end),
            ('company_id', '=', self.company_id.id),
            ('struct_id.name', 'not ilike', '%PRESTACIONES%')
            # ('state', 'in', ['done', 'paid'])
        ])

        if x_nomina:
            # Crear un diccionario para agrupar las nóminas por empleado
            grouped_nomina = {}
            for nominas in x_nomina:
                employee_id = nominas.employee_id.id
                if employee_id not in grouped_nomina:
                    grouped_nomina[employee_id] = []
                grouped_nomina[employee_id].append(nominas)

            sorted_employees = sorted(grouped_nomina.items(), key=lambda item: item[1][0].employee_id.name)

            for employee_id, nominaas in sorted_employees:
                x_horas_extras = 0
                x_pago_vacaciones = 0
                x_total_devegando = 0
                x_igss_lab_report = 0
                x_c_igss_lab_report = 0
                x_igss_pat_report = 0
                x_c_igss_pat_report = 0
                x_irtra_report = 0
                x_intecap_report = 0
                x_basic_wage = 0
                x_fecha = ''
                x_date_end = ''
                x_igss = ''
                x_name = ''
                x_departamento = ''
                x_area = ''
                x_puesto = ''
                x_tiempo_contrato = ''
                x_dias = 0
                x_horas = 0
                for nomina in nominaas:
                    x_fecha = nomina.employee_id.contract_id.date_start.strftime('%d-%m-%Y') if nomina.employee_id.contract_id.date_start else ''
                    x_date_end = nomina.employee_id.contract_id.date_end.strftime('%d-%m-%Y') if nomina.employee_id.contract_id.date_end else ''
                    x_igss = nomina.employee_id.igss if nomina.employee_id.igss else ''
                    x_name = nomina.employee_id.name if nomina.employee_id.name else ''

                    for x_line in nomina.line_ids:
                        if x_line.code == 'VHEB':
                            x_horas_extras += x_line.total
                        elif x_line.code == 'VACACPAG':
                            x_pago_vacaciones += x_line.total
                        elif x_line.code == 'IGSSLABR':
                            x_igss_lab_report += x_line.total
                        elif x_line.code == 'CIGSSLAB':
                            x_c_igss_lab_report += x_line.total
                        elif x_line.code == 'IGSS PAT':
                            x_igss_pat_report += x_line.total
                        elif x_line.code == 'CIGSSPAT':
                            x_c_igss_pat_report += x_line.total
                        elif x_line.code == 'IRTRA':
                            x_irtra_report += x_line.total
                        elif x_line.code == 'INTECAP':
                            x_intecap_report += x_line.total
                    x_total_devegando += nomina.basic_wage + x_horas_extras + x_pago_vacaciones
                    # x_dias = (nomina.date_to - nomina.date_from).days + 1
                    x_dias = 0
                    # x_horas = x_dias * 8
                    x_horas = 0

                    #Edvin en esta linea de codigo estoy obteniendo el valor de la etiqueta de la seleccion
                    #con la función get_selection_label me da el nombre y no  el valor de la selección
                    x_tiempo_contrato = self.get_selection_label(nomina.employee_id.contract_id, 'tiempo_contrato')
                    if nomina.basic_wage:
                        x_basic_wage += nomina.basic_wage
                    x_departamento = nomina.employee_id.contract_id.department_id.parent_id.name if nomina.employee_id.contract_id.department_id.parent_id.name else ''
                    x_area = nomina.employee_id.department_id.name if nomina.employee_id.department_id.name else ''
                    x_puesto = nomina.employee_id.job_title if nomina.employee_id.job_title else ''
                x_rows += 1
                worksheet.write(x_rows, 0, x_fecha, detail_emp_1)  # Inicio de contrato
                worksheet.write(x_rows, 1, x_date_end, detail_emp_1)  # Fin de Contrato
                worksheet.write(x_rows, 2, x_igss, detail_emp_1)  # No. afiliación
                worksheet.write(x_rows, 3, x_name, detail_emp_1)  # Nombres y Apellidos
                worksheet.write(x_rows, 4, x_basic_wage, detail_emp_1)  # salario Base
                worksheet.write(x_rows, 5, x_horas_extras, detail_emp_1)  # horas extras
                worksheet.write(x_rows, 6, x_pago_vacaciones, detail_emp_1)  # Vacaciones
                worksheet.write(x_rows, 7, x_basic_wage + x_horas_extras + x_pago_vacaciones, detail_emp_1)  # Total
                worksheet.write(x_rows, 8, abs(x_igss_lab_report), detail_emp_1)  # Igss laboral
                worksheet.write(x_rows, 9, abs(x_c_igss_lab_report), detail_emp_1)  # Complemento Igss Laboral
                worksheet.write(x_rows, 10, abs(x_igss_pat_report), detail_emp_1)  # Igss patronal
                worksheet.write(x_rows, 11, abs(x_c_igss_pat_report), detail_emp_1)  # Complemento Igss Patronal
                worksheet.write(x_rows, 12, abs(x_irtra_report), detail_emp_1)  # irtra
                worksheet.write(x_rows, 13, abs(x_intecap_report), detail_emp_1)  # Intecap
                worksheet.write(x_rows, 14, x_departamento, detail_emp_1)  # Departamento
                worksheet.write(x_rows, 15, x_area, detail_emp_1)  # Area
                worksheet.write(x_rows, 16, x_puesto, detail_emp_1)  # Puesto
                worksheet.write(x_rows, 17, x_tiempo_contrato, detail_emp_1)  # Tiempo de Contrato
                worksheet.write(x_rows, 18, x_dias, detail_emp_1)  # Cantidad de días laboradas en el mes
                worksheet.write(x_rows, 19, x_horas, detail_emp_1)  # Cantidad de horas laborados del mes
        workbook.close()
        self.write(
            {
                'state': 'get',
                'name': xls_filename,
                'data': base64.b64encode(open(xls_path, 'rb').read())
            }
        )
        return {
            'name': 'Reporte Planilla IGSS',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new',
        }

class WizardInformeEmpleador(models.TransientModel):
    _name = 'wizard.informe.empleador'
    _description = "Wizard Informe del Empleador"

    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id)

    #company_id = fields.Many2one('res.company', string='Companilla', required=True)
    date_start = fields.Date('Del', required=True)
    date_end = fields.Date('Al', required=True)
    # employee_id = fields.Many2one('hr.employee', string='Empleado', required=False)
    state = fields.Selection([('choose', 'choose'), ('get', 'get')], default='choose')
    name = fields.Char(string='File Name', readonly=True)
    data = fields.Binary(string='File', readonly=True)

    @api.onchange('company_id')
    def onchange_company_id(self):
        domain = [('company_id', '=', self.company_id.id)]
        return {'domain': {'company_id': domain}}

    def got_back(self):
        self.state = 'choose'
        return {
            'name': 'Informe del Empleador',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def check_date(self):
        if self.date_end < self.date_start:
            raise ValidationError(_('La fecha de inicio no puede ser mayor que la fecha de finalización.'))
        # if self.date_start.year != self.date_end.year:
        #     raise ValidationError(_('El rango de fechas debe estar dentro del mismo año.'))

    def get_selection_label(self, record, field_name):
        # Obtén la definición del campo
        field = record._fields[field_name]
        # Obtén el valor actual del campo
        value = getattr(record, field_name)
        # Busca la etiqueta correspondiente al valor
        label = dict(field.selection).get(value)
        return label
    def get_dias_laborados(self, date_start, date_end):
        datos_mes = [
            {
                "Mes": 1,
                "Dias_calendario": 31,
                "Descanso_semanal": 4,
                "Asueto": 1,
                "Total_ausencia": 5,
                "Total_dias_laborados": 26
            },
            {
                "Mes": 2,
                "Dias_calendario": 28,
                "Descanso_semanal": 4,
                "Asueto": 0,
                "Total_ausencia": 4,
                "Total_dias_laborados": 24
            },
            {
                "Mes": 3,
                "Dias_calendario": 31,
                "Descanso_semanal": 4,
                "Asueto": 3,
                "Total_ausencia": 7,
                "Total_dias_laborados": 24
            },
            {
                "Mes": 4,
                "Dias_calendario": 30,
                "Descanso_semanal": 4,
                "Asueto": 0,
                "Total_ausencia": 4,
                "Total_dias_laborados": 26
            },
            {
                "Mes": 5,
                "Dias_calendario": 31,
                "Descanso_semanal": 4,
                "Asueto": 1,
                "Total_ausencia": 5,
                "Total_dias_laborados": 26
            },
            {
                "Mes": 6,
                "Dias_calendario": 30,
                "Descanso_semanal": 4,
                "Asueto": 1,
                "Total_ausencia": 5,
                "Total_dias_laborados": 25
            },
            {
                "Mes": 7,
                "Dias_calendario": 31,
                "Descanso_semanal": 4,
                "Asueto": 0,
                "Total_ausencia": 4,
                "Total_dias_laborados": 27
            },
            {
                "Mes": 8,
                "Dias_calendario": 31,
                "Descanso_semanal": 4,
                "Asueto": 0,
                "Total_ausencia": 4,
                "Total_dias_laborados": 27
            },
            {
                "Mes": 9,
                "Dias_calendario": 30,
                "Descanso_semanal": 4,
                "Asueto": 1,
                "Total_ausencia": 5,
                "Total_dias_laborados": 25
            },
            {
                "Mes": 10,
                "Dias_calendario": 31,
                "Descanso_semanal": 4,
                "Asueto": 1,
                "Total_ausencia": 5,
                "Total_dias_laborados": 26
            },
            {
                "Mes": 11,
                "Dias_calendario": 30,
                "Descanso_semanal": 4,
                "Asueto": 1,
                "Total_ausencia": 5,
                "Total_dias_laborados": 25
            },
            {
                "Mes": 12,
                "Dias_calendario": 31,
                "Descanso_semanal": 4,
                "Asueto": 2,
                "Total_ausencia": 6,
                "Total_dias_laborados": 25
            }
        ]


        hoy = datetime.now()
        if date_end is None:
            date_end = hoy

        mes_inicio = date_start.month
        anio_inicio = date_start.year
        dia_inicio = date_start.day
        mes_fin = date_end.month
        anio_fin = date_end.year
        dia_fin = date_end.day
        total_dias_laborados = 0

        if anio_inicio < anio_fin:
            mes_inicio = 1

        for mes in datos_mes:
            if mes['Mes'] >= mes_inicio and mes['Mes'] <= mes_fin:
                total_dias_laborados += mes['Total_dias_laborados']

        return total_dias_laborados


    def print_xls_informe_empleador(self):
        self.check_date()
        xls_filename = 'Informe del Empleador.xlsx'
        temp_dir = tempfile.gettempdir()
        xls_path = os.path.join(temp_dir, xls_filename)
        workbook = xlsxwriter.Workbook(xls_path)
        worksheet = workbook.add_worksheet("Informe del Empleador")
        frmt_folio = workbook.add_format({'bold': True, 'align': 'right', 'font': 'Arial', 'font_size': 6})
        frmt_encabezado = workbook.add_format(
            {'bold': True, 'align': 'center', 'valign': 'vcenter', 'font': 'Arial', 'font_size': 6})
        frmt_encabezado_columna = workbook.add_format(
            {'bold': True, 'align': 'center', 'valign': 'vcenter', 'font': 'Arial', 'font_size': 10, 'border': 1,
             'bg_color': '#DDEBF7', 'text_wrap': True})
        detail_emp_1 = workbook.add_format(
            { 'font': 'Arial', 'font_size': 10, 'border': 1})
        x_rows = 0
        #Tamaño de Columnas
        worksheet.set_column('A:A', 10)
        worksheet.set_column('B:B', 8)
        worksheet.set_column('C:C', 8)
        worksheet.set_column('D:D', 8)
        worksheet.set_column('E:E', 8)
        worksheet.set_column('F:F', 8)
        worksheet.set_column('G:G', 8)
        worksheet.set_column('H:H', 10)
        worksheet.set_column('I:I', 10)
        worksheet.set_column('J:J', 10)
        worksheet.set_column('K:K', 10)
        worksheet.set_column('L:L', 15)
        worksheet.set_column('M:M', 8)
        worksheet.set_column('N:N', 8)
        worksheet.set_column('O:O', 8)
        worksheet.set_column('P:P', 12)
        worksheet.set_column('Q:Q', 15)
        worksheet.set_column('R:R', 5)
        worksheet.set_column('S:S', 10)
        worksheet.set_column('T:T', 10)
        worksheet.set_column('U:U', 10)
        worksheet.set_column('V:V', 10)
        worksheet.set_column('W:W', 10)
        worksheet.set_column('X:X', 10)
        worksheet.set_column('Y:Y', 10)
        worksheet.set_column('Z:Z', 10)
        worksheet.set_column('AA:AA', 10)
        worksheet.set_column('AB:AB', 10)
        worksheet.set_column('AC:AC', 10)
        worksheet.set_column('AD:AD', 10)
        worksheet.set_column('AE:AE', 10)
        worksheet.set_column('AF:AF', 10)
        worksheet.set_column('AG:AG', 10)
        worksheet.set_column('AH:AH', 10)
        worksheet.set_column('AI:AI', 10)
        worksheet.set_column('AJ:AJ', 10)
        worksheet.set_column('AK:AK', 10)
        worksheet.set_column('AL:AL', 10)
        worksheet.set_column('AM:AM', 10)
        worksheet.set_column('AN:AN', 10)
        worksheet.set_column('AO:AO', 10)
        worksheet.set_column('AP:AP', 10)
        worksheet.set_column('AQ:AQ', 10)
        worksheet.set_column('AR:AR', 10)
        worksheet.set_column('AS:AS', 10)
        worksheet.set_column('AT:AT', 10)
        worksheet.set_column('AU:AU', 11)
        worksheet.set_column('AV:AV', 11)
        #Encabezados
        worksheet.write(x_rows,0, 'Número de empleado', frmt_encabezado_columna)
        worksheet.write(x_rows,1, 'Primer nombre', frmt_encabezado_columna)
        worksheet.write(x_rows,2, 'Segundo nombre', frmt_encabezado_columna)
        worksheet.write(x_rows,3, 'Tercer nombre', frmt_encabezado_columna)
        worksheet.write(x_rows,4, 'Primer apellido', frmt_encabezado_columna)
        worksheet.write(x_rows,5, 'Segundo apellido', frmt_encabezado_columna)
        worksheet.write(x_rows,6, 'Apellido de Casada', frmt_encabezado_columna)
        worksheet.write(x_rows,7, 'Nacionalidad', frmt_encabezado_columna)
        worksheet.write(x_rows,8, 'Tipo de discapacidad', frmt_encabezado_columna)
        worksheet.write(x_rows,9, 'Estado civil', frmt_encabezado_columna)
        worksheet.write(x_rows,10, 'Documento identificación (DPI, Pasaporte u otro)', frmt_encabezado_columna)
        worksheet.write(x_rows,11, 'Número de documento', frmt_encabezado_columna)
        worksheet.write(x_rows,12, 'País de origen', frmt_encabezado_columna)
        worksheet.write(x_rows,13, 'Número de expediente del permiso de extranjero', frmt_encabezado_columna)
        worksheet.write(x_rows,14, 'Lugar de nacimiento (municipio)', frmt_encabezado_columna)
        worksheet.write(x_rows,15, 'Número de Identificación Tributaria (NIT)', frmt_encabezado_columna)
        worksheet.write(x_rows,16, 'Número de afiliación al IGSS', frmt_encabezado_columna)
        worksheet.write(x_rows,17, 'Sexo', frmt_encabezado_columna)
        worksheet.write(x_rows,18, 'Fecha de nacimiento', frmt_encabezado_columna)
        worksheet.write(x_rows,19, 'Nivel académico más alto alcanzado', frmt_encabezado_columna)
        worksheet.write(x_rows,20, 'Titulo o diploma (profesión)', frmt_encabezado_columna)
        worksheet.write(x_rows,21, 'Pueblo de pertenencia', frmt_encabezado_columna)
        worksheet.write(x_rows,22, 'Comunidad Lingüística', frmt_encabezado_columna)
        worksheet.write(x_rows,23, 'Cantidad de hijos', frmt_encabezado_columna)
        worksheet.write(x_rows,24, 'Temporalidad del contrato', frmt_encabezado_columna)
        worksheet.write(x_rows,25, 'Tipo de contrato', frmt_encabezado_columna)
        worksheet.write(x_rows,26, 'Fecha de inicio de labores', frmt_encabezado_columna)
        worksheet.write(x_rows,27, 'Fecha  de reinicio de labores', frmt_encabezado_columna)
        worksheet.write(x_rows,28, 'Fecha de finalización de labores', frmt_encabezado_columna)
        worksheet.write(x_rows,29, 'Ocupación (Puesto)', frmt_encabezado_columna)
        worksheet.write(x_rows,30, 'Jornada de Trabajo', frmt_encabezado_columna)
        worksheet.write(x_rows,31, 'Días laborados en el año', frmt_encabezado_columna)
        worksheet.write(x_rows,32, 'Salario mensual nominal', frmt_encabezado_columna)
        worksheet.write(x_rows,33, 'Salario mensual nominal interno', frmt_encabezado_columna)
        worksheet.write(x_rows,34, 'Salario anual nominal', frmt_encabezado_columna)
        worksheet.write(x_rows,35, 'Bonificación Decreto 78-89  (Q.250.00)', frmt_encabezado_columna)
        worksheet.write(x_rows,36, 'Total horas extras anuales', frmt_encabezado_columna)
        worksheet.write(x_rows,37, 'Valor de la hora extra', frmt_encabezado_columna)
        worksheet.write(x_rows,38, 'Monto Aguinaldo Decreto 76-78', frmt_encabezado_columna)
        worksheet.write(x_rows,39, 'Monto Bono 14  Decreto 42-92', frmt_encabezado_columna)
        worksheet.write(x_rows,40, 'Retribución por comisiones', frmt_encabezado_columna)
        worksheet.write(x_rows,41, 'Viáticos', frmt_encabezado_columna)
        worksheet.write(x_rows,42, 'Bonificaciones adicionales', frmt_encabezado_columna)
        worksheet.write(x_rows,43, 'Retribución por vacaciones', frmt_encabezado_columna)
        worksheet.write(x_rows,44, 'Retribución por indemnización (Artículo 82 Código de Trabajo)', frmt_encabezado_columna)
        worksheet.write(x_rows,45, 'Sucursal', frmt_encabezado_columna)
        worksheet.write(x_rows,46, 'Del', frmt_encabezado_columna)
        worksheet.write(x_rows,47, 'Hasta', frmt_encabezado_columna)
        x_rows += 1

        x_employees = self.env['hr.employee'].with_context(active_test=False).search([
            ('company_id', '=', self.company_id.id),
            ('contract_id', '!=', False),
        ])
        if x_employees:
            for x_employee in x_employees:
                x_primera_fecha = ''
                x_segunda_fecha = ''
                x_tercera_fecha = ''
                todos_Contratos = self.env['hr.contract'].search([
                    ('employee_id', '=', x_employee.id),
                    ('company_id', '=', self.company_id.id),
                ], order='date_start desc')
                if todos_Contratos:
                    #Fecha Inicio de contrato registrado ante la inspección
                    for contrato in todos_Contratos:
                        if self.date_start.year == contrato.date_start.year and contrato.registrar_fecha_inspeccion and x_primera_fecha == '':
                            x_primera_fecha = contrato.date_start.strftime('%d-%m-%Y')
                            break
                        elif contrato.date_start.year < self.date_start.year and x_primera_fecha == '' and contrato.registrar_fecha_inspeccion:
                            x_primera_fecha = contrato.date_start.strftime('%d-%m-%Y')
                            break
                    #fecha reinicio de contrato registrado ante la inspección
                    for contrato in todos_Contratos:
                        if contrato.date_start.year <= self.date_start.year and x_primera_fecha != '' and contrato.date_start.strftime('%d-%m-%Y') != x_primera_fecha and contrato.registrar_fecha_inspeccion:
                            pass
                        if contrato.date_start.year <= self.date_start.year and x_primera_fecha != '' and contrato.date_start.strftime('%d-%m-%Y') != x_primera_fecha and contrato.registrar_fecha_inspeccion:
                            x_segunda_fecha = x_primera_fecha
                            x_primera_fecha = contrato.date_start.strftime('%d-%m-%Y')
                            break
                    #Fecha Fin de contrato registrado ante la inspección
                    for contrato in todos_Contratos:
                        if contrato.date_end and contrato.date_end.year <= self.date_end.year:
                            x_tercera_fecha = contrato.date_end.strftime('%d-%m-%Y')
                            break
                        elif contrato.date_end == False and contrato.date_start.year <= self.date_end.year:
                            x_tercera_fecha = contrato.date_end.strftime('%d-%m-%Y') if contrato.date_end else ''
                            break
                    #se existe un contrato con fedha fin vació pero la fecha inicio el contrato es igual o menoar al año de busqueda que lo salte
                    #si encuentra un contrato con una fecha final y mientras sea menor del año de busqueda reeescribe la fecha
                    for contrato in todos_Contratos:
                        if contrato.date_end == False and contrato.date_start.year <= self.date_end.year:
                            pass
                        elif contrato.date_end and contrato.date_end.year <= self.date_end.year and x_segunda_fecha != '':
                            x_tercera_fecha = contrato.date_end.strftime('%d-%m-%Y')
                            break

                x_code_employee = x_employee.registration_number if x_employee.registration_number else ''
                x_pNombre = x_employee.primer_nombre if x_employee.primer_nombre else ''
                x_sNombre = x_employee.segundo_nombre if x_employee.segundo_nombre else ''
                x_tNombre = x_employee.tercer_nombre if x_employee.tercer_nombre else ''
                x_pApellido = x_employee.primer_apellido if x_employee.primer_apellido else ''
                x_sApellido = x_employee.segundo_apellido if x_employee.segundo_apellido else ''
                x_aCasada = x_employee.apellido_casada if x_employee.apellido_casada else ''
                x_country = x_employee.country_id.code if x_employee.country_id.code == 'GTM' else 'GTM'
                x_discapacidad = x_employee.discapacidad if x_employee.discapacidad else '1'

                if x_employee.marital == 'single' or x_employee.marital == 'divorced' or x_employee.marital == 'widower':
                    x_code_marital = '1'
                elif x_employee.marital == 'married':
                    x_code_marital = '2'
                elif x_employee.marital == 'cohabitant':
                    x_code_marital = '3'
                else:
                    x_code_marital = '1'

                if x_employee.identification_id:
                    x_tipo_documento = '1'
                else:
                    x_tipo_documento = '2'

                x_identification_id = x_employee.identification_id if x_employee.identification_id else ''
                x_municipio = x_employee.municipio_id.code if x_employee.municipio_id.code else ''
                x_nit = x_employee.nit if x_employee.nit else ''
                x_igss = x_employee.igss if x_employee.igss else ''

                if x_employee.gender == 'male':
                    x_code_gender = '1'
                elif x_employee.gender == 'female':
                    x_code_gender = '2'
                else:
                    x_code_gender = '1'

                x_fecha_nacimiento = x_employee.birthday.strftime('%d-%m-%Y') if x_employee.birthday else ''

                if x_employee.certificate == 'other':
                    x_code_certificate = '1'
                elif x_employee.certificate == 'graduate':
                    x_code_certificate = '7'
                elif x_employee.certificate == 'bachelor':
                    x_code_certificate = '10'
                elif x_employee.certificate == 'master':
                    x_code_certificate = '12'
                elif x_employee.certificate == 'doctor':
                    x_code_certificate = '13'
                else:
                    x_code_certificate = x_employee.certificate
                x_nominas = self.env['hr.payslip'].search([
                    ('employee_id', '=', x_employee.id),
                    ('date_to', '>=', self.date_start),
                    ('date_to', '<=', self.date_end),
                    ('company_id', '=', self.company_id.id)
                ])
                x_salario_base = 0
                x_horas_extras = 0
                x_aguinaldo = 0
                x_bonopag = 0
                x_sumatod = 0
                x_reva = 0
                x_idmp = 0
                for x_nomina in x_nominas:
                    x_salario_base += x_nomina.basic_wage
                    codes = ['MDOA', 'BHE', 'BONIN','BOFIJ','BONPRO','MDOP','MDOAS','MDOALIM','OTREN','OTRGRATIF']
                    for x_line in x_nomina.line_ids:
                        if x_line.code == 'VHEB':
                            x_horas_extras += x_line.total
                        elif x_line.code == 'AGUINALDOP':
                            x_aguinaldo  += x_line.total
                        elif x_line.code == 'BONO14P':
                            x_bonopag += x_line.total
                    #desde esta condición se empueza a sumar todas las bonificaciones de la columna AQ
                        elif x_line.code in codes:
                            x_sumatod += x_line.total
                        elif x_line.code == 'VACACPAG':
                            x_reva += x_line.total
                        elif x_line.code == 'INDEMP':
                            x_idmp += x_line.total

                x_study_field = x_employee.study_field if x_employee.study_field else ''
                x_cantidad_hijos = x_employee.children if x_employee.children else '0'
                x_temporalidad_contrato = x_employee.contract_id.contract_type_id.id if x_employee.contract_id.contract_type_id.id else ''
                x_fecha_contrato = x_employee.first_contract_date.strftime('%d-%m-%Y') if x_employee.first_contract_date else ''
                x_date_end = x_employee.contract_id.date_end.strftime('%d-%m-%Y') if x_employee.contract_id.date_end else ''
                x_ocupacion = x_employee.ocupacion_puesto_id.code if x_employee.ocupacion_puesto_id.code else ''
                x_jornada_trabajo = x_employee.jornada_trabajo if x_employee.jornada_trabajo else ''
                x_salario_mensual = x_employee.contract_id.wage if x_employee.contract_id.wage else ''
                x_valor_hora = x_employee.contract_id.horas_extra_valor if x_employee.contract_id.horas_extra_valor else ''

                if x_employee.contract_id.date_start and x_employee.contract_id.date_end:
                    x_dias = self.get_dias_laborados(x_employee.contract_id.date_start, x_employee.contract_id.date_end)
                elif x_employee.contract_id.date_start:
                    x_dias = self.get_dias_laborados(x_employee.contract_id.date_start, datetime.now())
                else:
                    x_dias = 0

                worksheet.write(x_rows, 0, x_code_employee, detail_emp_1)#codigo del empleado
                worksheet.write(x_rows, 1, x_pNombre, detail_emp_1)#Primer nombre
                worksheet.write(x_rows, 2, x_sNombre, detail_emp_1)#Segundo nombre
                worksheet.write(x_rows, 3, x_tNombre, detail_emp_1)#Tercer nombre
                worksheet.write(x_rows, 4, x_pApellido, detail_emp_1)#Primer apellido
                worksheet.write(x_rows, 5, x_sApellido, detail_emp_1)#Segundo apellido
                worksheet.write(x_rows, 6, x_aCasada, detail_emp_1)#Apellido de Casada
                worksheet.write(x_rows, 7, x_country, detail_emp_1)#Nacionalidad
                worksheet.write(x_rows, 8, x_discapacidad, detail_emp_1)#Tipo de discapacidad
                worksheet.write(x_rows, 9, x_code_marital, detail_emp_1)# Estado civil
                worksheet.write(x_rows, 10, x_tipo_documento, detail_emp_1)#Tipo de documento
                worksheet.write(x_rows, 11, x_identification_id, detail_emp_1)#Número de documento
                worksheet.write(x_rows, 12, x_country, detail_emp_1)#País de origen
                worksheet.write(x_rows, 13, '', detail_emp_1)#Número de expediente del permiso de extranjero
                worksheet.write(x_rows, 14, x_municipio, detail_emp_1)#Lugar de nacimiento (municipio)
                worksheet.write(x_rows, 15, x_nit, detail_emp_1)#Número de Identificación Tributaria (NIT)
                worksheet.write(x_rows, 16, x_igss, detail_emp_1)#Número de afiliación al IGSS
                worksheet.write(x_rows, 17, x_code_gender, detail_emp_1)#Sexo
                worksheet.write(x_rows, 18, x_fecha_nacimiento, detail_emp_1)#Fecha de nacimiento
                worksheet.write(x_rows, 19, x_code_certificate, detail_emp_1)#Codigo Nivel academico
                worksheet.write(x_rows, 20, x_study_field,detail_emp_1) # campo de estudio
                worksheet.write(x_rows, 21, 1,detail_emp_1) # codigo Pueblo de pertenencia
                worksheet.write(x_rows, 22, 10,detail_emp_1) # codigo comunidad lingúistica
                worksheet.write(x_rows, 23, x_cantidad_hijos,   detail_emp_1) # cantidad de hijos
                worksheet.write(x_rows, 24, x_temporalidad_contrato,detail_emp_1) # codigo Temporalidad Contrato
                worksheet.write(x_rows, 25, 2, detail_emp_1) # codigo Tipo de Contrato
                worksheet.write(x_rows, 26, x_primera_fecha,detail_emp_1) # Fecha contrato
                worksheet.write(x_rows, 27, x_segunda_fecha,detail_emp_1) # Fecha reinicio
                worksheet.write(x_rows, 28, x_tercera_fecha,detail_emp_1) #Fecha fin
                worksheet.write(x_rows, 29, x_ocupacion,detail_emp_1) # codigo ocupación
                worksheet.write(x_rows, 30, x_jornada_trabajo,detail_emp_1) # Jornada de Trabajo --
                worksheet.write(x_rows, 31, x_dias,detail_emp_1) # Días laborados en el año --
                #preguntar por esta columna g si es correcto
                worksheet.write(x_rows, 32, x_salario_mensual,detail_emp_1) # Salario mensual nominal clumna AG PREGUNTAR
                worksheet.write(x_rows, 33, x_salario_mensual,detail_emp_1)#Salario nominal Interno
                worksheet.write(x_rows, 34, abs(x_salario_base),detail_emp_1)# salario segun decreto campo calculado
                # # se dejo en cero porque el reporte original estaba devolviendo 0
                worksheet.write(x_rows, 35, 0,detail_emp_1)# Bonificación Decreto    78-89  (Q.250.00)
                worksheet.write(x_rows, 36, abs(x_horas_extras),detail_emp_1)# horas extras
                worksheet.write(x_rows, 37, x_valor_hora,detail_emp_1)# valor hora extra
                worksheet.write(x_rows, 38,abs(x_aguinaldo),detail_emp_1)#aguinaldo mas bono
                worksheet.write(x_rows, 39,abs(x_bonopag),detail_emp_1) # bono pagado
                worksheet.write(x_rows, 40,0,detail_emp_1)#retribución por comisiones
                worksheet.write(x_rows, 41,0,detail_emp_1)#viáticos
                worksheet.write(x_rows, 42,abs(x_sumatod),detail_emp_1)#bonificaciones adicionales
                worksheet.write(x_rows, 43,abs(x_reva),detail_emp_1)#retribución por vacaciones
                worksheet.write(x_rows, 44,abs(x_idmp),detail_emp_1)#retribución por indemnización
                worksheet.write(x_rows, 45,1,detail_emp_1)#sucursal
                worksheet.write(x_rows, 46,self.date_start.strftime('%d-%m-%Y'),detail_emp_1)#del
                worksheet.write(x_rows, 47,self.date_end.strftime('%d-%m-%Y'),detail_emp_1)#hasta
                x_rows += 1

        workbook.close()
        self.write(
            {
                'state': 'get',
                'name': xls_filename,
                'data': base64.b64encode(open(xls_path, 'rb').read())
            }
        )
        return {
            'name': 'Informe del Empleador',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new',
        }

class WizardReporteDescuentos(models.TransientModel):
    _name = 'wizard.reporte.descuentos'
    _description = "Wizard Reporte de Descuentos"

    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id)
    date_start = fields.Date('Del', required=True)
    date_end = fields.Date('Al', required=True)
    #employee_id = fields.Many2one('hr.employee', string='Empleado', required=True)
    state = fields.Selection([('choose', 'choose'), ('get', 'get')], default='choose')
    name = fields.Char(string='File Name', readonly=True)
    data = fields.Binary(string='File', readonly=True)

    @api.onchange('company_id')
    def onchange_company_id(self):
        domain = [('company_id', '=', self.company_id.id)]
        return {'domain': {'company_id': domain}}

    def got_back(self):
        self.state = 'choose'
        return {
            'name': 'Reporte de Descuentos',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def check_date(self):
        if self.date_start > self.date_end:
            raise ValidationError(_('La fecha de inicio no puede ser mayor que la fecha de finalización.'))
        #if self.date_start.year != self.date_end.year:
        #     #raise ValidationError(_('El rango de fechas debe estar dentro del mismo año.'))

    def get_selection_label(self, record, field_name):
        # Obtén la definición del campo
        field = record._fields[field_name]
        # Obtén el valor actual del campo
        value = getattr(record, field_name)
        # Busca la etiqueta correspondiente al valor
        label = dict(field.selection).get(value)
        return label
    def print_xls_reporte_descuentos(self):
        self.check_date()
        xls_filename = 'Reporte de Descuentos.xlsx'
        temp_dir = tempfile.gettempdir()
        xls_path = os.path.join(temp_dir, xls_filename)
        workbook = xlsxwriter.Workbook(xls_path)
        worksheet = workbook.add_worksheet("Reporte de descuentos")
        frmt_folio = workbook.add_format({'bold': True, 'align': 'right', 'font': 'Arial', 'font_size': 6})
        frmt_encabezado = workbook.add_format(
            {'bold': True, 'align': 'center', 'valign': 'vcenter', 'font': 'Arial', 'font_size': 12})
        frmt_encabezado_columna = workbook.add_format(
            {'bold': True, 'align': 'center', 'valign': 'vcenter', 'font': 'Arial', 'font_size': 11, 'border': 1,
             'bg_color': '#DDEBF7', 'text_wrap': True})
        detail_emp_1 = workbook.add_format(
            {'valign': 'vcenter', 'font': 'Arial', 'font_size': 11, 'border': 1})
        # configuracion columnas
        worksheet.set_column('A:A', 30)
        worksheet.set_column('B:B', 30)
        worksheet.set_column('C:C', 20)
        worksheet.set_column('D:D', 20)
        worksheet.set_column('E:E', 20)
        worksheet.set_column('F:F', 20)
        worksheet.set_column('G:G', 25)
        worksheet.set_column('H:H', 20)
        worksheet.set_column('I:I', 20)
        worksheet.set_column('J:J', 20)
        # Encabezados
        x_rows = 0
        worksheet.merge_range(x_rows, 0, x_rows, 9, 'Reporte de Descuentos', frmt_encabezado)
        x_rows += 1
        worksheet.write(x_rows, 0, 'Empleado', frmt_encabezado_columna)
        worksheet.write(x_rows, 1, 'Empresa', frmt_encabezado_columna)
        worksheet.write(x_rows, 2, 'Area', frmt_encabezado_columna)
        worksheet.write(x_rows, 3, 'Departamento', frmt_encabezado_columna)
        worksheet.write(x_rows, 4, 'Fecha', frmt_encabezado_columna)
        worksheet.write(x_rows, 5, 'Tipo de anticipo', frmt_encabezado_columna)
        worksheet.write(x_rows, 6, 'Concepto', frmt_encabezado_columna)
        worksheet.write(x_rows, 7, 'Monto', frmt_encabezado_columna)
        worksheet.write(x_rows, 8, 'Ingreso', frmt_encabezado_columna)
        worksheet.write(x_rows, 9, 'Comentario', frmt_encabezado_columna)
        x_rows += 1
        # construir el libro en este espacio de trabajo
        x_employee = self.env['hr.employee'].with_context(active_test=False).search([
            ('company_id', '=', self.company_id.id),
        ])
        if x_employee:
            for employee in x_employee:
                if employee.descuentos:
                    for x_descuento in employee.descuentos:
                        if self.date_start <= x_descuento.date <= self.date_end:
                            x_comentario = x_descuento.reason if x_descuento.reason else ''
                            x_name = x_descuento.employee_id.name if x_descuento.employee_id.name else ''
                            x_company = x_descuento.employee_id.company_id.name if x_descuento.employee_id.company_id.name else ''
                            x_area = x_descuento.employee_id.department_id.name if x_descuento.employee_id.department_id.name else ''
                            x_department = x_descuento.employee_id.contract_id.department_id.parent_id.name if x_descuento.employee_id.contract_id.department_id.parent_id.name else ''
                            x_fecha = x_descuento.date.strftime('%d-%m-%Y') if x_descuento.date.strftime('%d-%m-%Y') else ''
                            x_tipo = x_descuento.tipo_anticipo.name if x_descuento.tipo_anticipo.name else ''
                            x_concepto = x_descuento.concepto.name if x_descuento.concepto.name else ''
                            x_cantidad = x_descuento.advance if x_descuento.advance else 0
                            x_registro = x_descuento.create_uid.name if x_descuento.create_uid.name else ''
                            worksheet.write(x_rows, 0, x_name, detail_emp_1)
                            worksheet.write(x_rows, 1, x_company, detail_emp_1)
                            worksheet.write(x_rows, 2, x_area, detail_emp_1)  # Area
                            worksheet.write(x_rows, 3, x_department,
                                            detail_emp_1)  # Departamento
                            worksheet.write(x_rows, 4, x_fecha, detail_emp_1)
                            worksheet.write(x_rows, 5, x_tipo, detail_emp_1)
                            worksheet.write(x_rows, 6, x_concepto, detail_emp_1)
                            worksheet.write(x_rows, 7, abs(x_cantidad), detail_emp_1)
                            worksheet.write(x_rows, 8, x_registro, detail_emp_1)
                            worksheet.write(x_rows, 9, x_comentario, detail_emp_1)
                            x_rows += 1
                if employee.prestamos:
                    for x_prestamo in employee.prestamos:
                        for x_prestamo_pago in x_prestamo.loan_lines:
                            if self.date_start <= x_prestamo_pago.date <= self.date_end:
                                x_name =  x_prestamo_pago.employee_id.name if x_prestamo_pago.employee_id.name else ''
                                x_company = x_prestamo_pago.employee_id.company_id.name if x_prestamo_pago.employee_id.company_id.name else ''
                                x_area = x_prestamo_pago.employee_id.department_id.name if x_prestamo_pago.employee_id.department_id.name else ''
                                x_departamento = x_prestamo_pago.employee_id.contract_id.department_id.parent_id.name if x_prestamo_pago.employee_id.contract_id.department_id.parent_id.name else ''
                                x_fecha = x_prestamo_pago.date.strftime('%d-%m-%Y') if x_prestamo_pago.date.strftime('%d-%m-%Y') else ''
                                x_cantidad = x_prestamo_pago.amount if x_prestamo_pago.amount else 0
                                x_registro = x_prestamo_pago.create_uid.name if x_prestamo_pago.create_uid.name else ''
                                x_concepto = x_prestamo.concepto.name if x_prestamo.concepto.name else ''
                                worksheet.write(x_rows, 0, x_name, detail_emp_1)
                                worksheet.write(x_rows, 1, x_company, detail_emp_1)
                                worksheet.write(x_rows, 2, x_area, detail_emp_1)  # Area
                                worksheet.write(x_rows, 3, x_departamento,
                                                detail_emp_1)  # Departamento
                                worksheet.write(x_rows, 4, x_fecha, detail_emp_1)
                                worksheet.write(x_rows, 5, 'Anticipo 3', detail_emp_1) #Tipo de anticipo
                                worksheet.write(x_rows, 6, x_concepto, detail_emp_1)
                                worksheet.write(x_rows, 7, abs(x_cantidad), detail_emp_1)
                                worksheet.write(x_rows, 8, x_registro, detail_emp_1)
                                worksheet.write(x_rows, 9, 'Prestamo', detail_emp_1)
                                x_rows += 1

        workbook.close()
        self.write(
            {
                'state': 'get',
                'name': xls_filename,
                'data': base64.b64encode(open(xls_path, 'rb').read())
            }
        )
        return {
            'name': 'Reporte de Descuentos',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new',
        }

class WizardPlanillaSueldos(models.TransientModel):
    _name = 'wizard.planilla.sueldos'
    _description = "Wizard Planilla de Sueldos"

    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id)
    # date_start = fields.Date('Del', required=True)
    # date_end = fields.Date('Al', required=True)
    planillas = fields.Many2many('hr.payslip.run', string='Lotes de Nómina', required=True)
    state = fields.Selection([('choose', 'choose'), ('get', 'get')], default='choose')
    name = fields.Char(string='File Name', readonly=True)
    data = fields.Binary(string='File', readonly=True)

    @api.onchange('company_id')
    def onchange_company_id(self):
        domain = [('company_id', '=', self.company_id.id)]
        return {'domain': {'company_id': domain}}

    def got_back(self):
        self.state = 'choose'
        return {
            'name': 'Planilla de Sueldos',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def check_date(self):
        if self.date_start > self.date_end:
            raise ValidationError(_('La fecha de inicio no puede ser mayor que la fecha de finalización.'))
        #if self.date_start.year != self.date_end.year:
        #     #raise ValidationError(_('El rango de fechas debe estar dentro del mismo año.'))

    def get_selection_label(self, record, field_name):
        # Obtén la definición del campo
        field = record._fields[field_name]
        # Obtén el valor actual del campo
        value = getattr(record, field_name)
        # Busca la etiqueta correspondiente al valor
        label = dict(field.selection).get(value)
        return label
    def print_xls_planilla_sueldos(self):
        # self.check_date()
        xls_filename = 'Planilla de Sueldos.xlsx'
        temp_dir = tempfile.gettempdir()
        xls_path = os.path.join(temp_dir, xls_filename)
        workbook = xlsxwriter.Workbook(xls_path)
        worksheet = workbook.add_worksheet("Planilla de Sueldos")
        frmt_folio = workbook.add_format({'bold': True, 'align': 'right', 'font': 'Arial', 'font_size': 6})
        frmt_encabezado = workbook.add_format(
            {'bold': True, 'align': 'center', 'valign': 'vcenter', 'font': 'Arial', 'font_size': 6})
        frmt_encabezado_columna = workbook.add_format(
            {'bold': True, 'align': 'center', 'valign': 'vcenter', 'font': 'Arial', 'font_size': 11, 'border': 1,
             'bg_color': '#DDEBF7', 'text_wrap': True})
        detail_emp_1 = workbook.add_format(
            {'font': 'Arial', 'font_size': 11, 'border': 1, 'valign': 'vcenter'})        # construir el libro en este espacio de trabajo

        detail_emp_1_date = workbook.add_format(
            {'font': 'Arial', 'font_size': 11, 'border': 1,
             'valign': 'vcenter', 'num_format': 'dd/mm/yyyy'})  # construir el libro en este espacio de trabajo

        # configuracion columnas
        worksheet.set_column('A:A', 6)
        worksheet.set_column('B:B', 20)
        worksheet.set_column('C:C', 18)
        worksheet.set_column('D:D', 18)
        worksheet.set_column('E:E', 30)
        worksheet.set_column('F:F', 13)
        worksheet.set_column('G:G', 10)
        worksheet.set_column('H:H', 11)
        worksheet.set_column('I:I', 11)
        worksheet.set_column('J:J', 18)
        worksheet.set_column('L:L', 10)
        worksheet.set_column('M:M', 10)
        worksheet.set_column('N:N', 10)
        worksheet.set_column('O:O', 10)
        worksheet.set_column('P:P', 10)
        worksheet.set_column('Q:Q', 10)
        worksheet.set_column('R:R', 10)
        worksheet.set_column('S:S', 10)
        worksheet.set_column('T:T', 10)
        worksheet.set_column('U:U', 10)
        worksheet.set_column('V:V', 10)
        worksheet.set_column('W:W', 10)
        worksheet.set_column('X:X', 10)
        worksheet.set_column('Y:Y', 10)
        worksheet.set_column('Z:Z', 10)
        worksheet.set_column('AA:AA', 10)
        worksheet.set_column('AB:AB', 10)
        worksheet.set_column('AC:AC', 10)
        worksheet.set_column('AD:AD', 10)
        worksheet.set_column('AE:AE', 10)
        worksheet.set_column('AF:AF', 10)
        worksheet.set_column('AG:AG', 10)
        worksheet.set_column('AH:AH', 10)
        worksheet.set_column('AI:AI', 10)
        worksheet.set_column('AJ:AJ', 10)
        worksheet.set_column('AK:AK', 10)
        worksheet.set_column('AL:AL', 10)
        worksheet.set_column('AM:AM', 10)
        worksheet.set_column('AN:AN', 10)
        worksheet.set_column('AO:AO', 10)
        worksheet.set_column('AP:AP', 10)
        worksheet.set_column('AQ:AQ', 10)
        worksheet.set_column('AR:AR', 10)
        worksheet.set_column('AS:AS', 10)
        worksheet.set_column('AT:AT', 10)
        worksheet.set_column('AU:AU', 20)
        worksheet.set_column('AV:AV', 12)
        worksheet.set_column('AW:AW', 20)
        worksheet.set_column('AX:AX', 25)
        worksheet.set_column('AY:AY', 30)
        worksheet.set_column('AZ:AZ', 12)
        worksheet.set_column('BA:BA', 11)
        worksheet.set_column('BB:BB', 11)

        # Encabezados
        x_rows = 0
        worksheet.write(x_rows, 0, 'Mes', frmt_encabezado_columna)
        worksheet.write(x_rows, 1, 'Código de Planilla', frmt_encabezado_columna)
        worksheet.write(x_rows, 2, 'Departamento', frmt_encabezado_columna)
        worksheet.write(x_rows, 3, 'Área', frmt_encabezado_columna)
        worksheet.write(x_rows, 4, 'Nombre del empleado', frmt_encabezado_columna)
        worksheet.write(x_rows, 5, 'Status', frmt_encabezado_columna)
        worksheet.write(x_rows, 6, 'Cod. de empleado', frmt_encabezado_columna)
        worksheet.write(x_rows, 7, 'Fecha de ingreso', frmt_encabezado_columna)
        worksheet.write(x_rows, 8, 'Fecha fin Contrato', frmt_encabezado_columna)
        worksheet.write(x_rows, 9, 'Puesto', frmt_encabezado_columna)
        worksheet.write(x_rows, 10, 'Días', frmt_encabezado_columna)
        worksheet.write(x_rows, 11, 'Salario base', frmt_encabezado_columna)
        worksheet.write(x_rows, 12, 'Bonificación Incentivo', frmt_encabezado_columna)
        worksheet.write(x_rows, 13, 'Bonificación Fija', frmt_encabezado_columna)
        worksheet.write(x_rows, 14, 'Bonificación por ajuste', frmt_encabezado_columna)
        worksheet.write(x_rows, 15, 'Bonificación por asueto', frmt_encabezado_columna)
        worksheet.write(x_rows, 16, 'Bonificación por productividad', frmt_encabezado_columna)
        worksheet.write(x_rows, 17, 'Alimentación', frmt_encabezado_columna)
        worksheet.write(x_rows, 18, 'Horas Extras', frmt_encabezado_columna)
        worksheet.write(x_rows, 19, 'Bonificación por Horas', frmt_encabezado_columna)
        worksheet.write(x_rows, 20, 'Bonificaciones Extras', frmt_encabezado_columna)
        worksheet.write(x_rows, 21, 'Salario devengado', frmt_encabezado_columna)
        worksheet.write(x_rows, 22, 'Cuota Laboral IGSS', frmt_encabezado_columna)
        worksheet.write(x_rows, 23, 'Complemento Cuota Laboral IGSS', frmt_encabezado_columna)
        worksheet.write(x_rows, 24, 'ISR Asalariados', frmt_encabezado_columna)
        worksheet.write(x_rows, 25, 'Anticipo 1', frmt_encabezado_columna)
        worksheet.write(x_rows, 26, 'Anticipo 2', frmt_encabezado_columna)
        worksheet.write(x_rows, 27, 'Anticipo 3', frmt_encabezado_columna)
        worksheet.write(x_rows, 28, 'Total deducciones', frmt_encabezado_columna)
        worksheet.write(x_rows, 29, 'Salario líquido', frmt_encabezado_columna)
        worksheet.write(x_rows, 30, 'Cuota Patronal', frmt_encabezado_columna)
        worksheet.write(x_rows, 31, 'Complemento Cuota Patronal', frmt_encabezado_columna)
        worksheet.write(x_rows, 32, 'Irtra', frmt_encabezado_columna)
        worksheet.write(x_rows, 33, 'Intecap', frmt_encabezado_columna)
        worksheet.write(x_rows, 34, 'Bono anual Reserva', frmt_encabezado_columna)
        worksheet.write(x_rows, 35, 'Aguinaldo Reserva', frmt_encabezado_columna)
        worksheet.write(x_rows, 36, 'Indemnización Reserva', frmt_encabezado_columna)
        worksheet.write(x_rows, 37, 'Vacaciones Reserva', frmt_encabezado_columna)
        worksheet.write(x_rows, 38, 'Total Reserva Para Prestaciones', frmt_encabezado_columna)
        worksheet.write(x_rows, 39, 'Gratificación', frmt_encabezado_columna)
        worksheet.write(x_rows, 40, 'Devolución de ISR', frmt_encabezado_columna)
        worksheet.write(x_rows, 41, 'Bono Anual Pago', frmt_encabezado_columna)
        worksheet.write(x_rows, 42, 'Aguinaldo Pago', frmt_encabezado_columna)
        worksheet.write(x_rows, 43, 'Indemnización Pago', frmt_encabezado_columna)
        worksheet.write(x_rows, 44, 'Vacaciones Pago', frmt_encabezado_columna)
        worksheet.write(x_rows, 45, 'Líquido a recibir', frmt_encabezado_columna)
        worksheet.write(x_rows, 46, 'Banco a depositar', frmt_encabezado_columna)
        worksheet.write(x_rows, 47, 'Cuenta a Depositar', frmt_encabezado_columna)
        worksheet.write(x_rows, 48, 'Observaciones', frmt_encabezado_columna)
        worksheet.write(x_rows, 49, 'Centro de Costo', frmt_encabezado_columna)
        worksheet.write(x_rows, 50, 'Empresa que debe Facturar', frmt_encabezado_columna)
        worksheet.write(x_rows, 51, 'Tipo Facturación', frmt_encabezado_columna)
        worksheet.write(x_rows, 52, 'Fecha desde Nómina', frmt_encabezado_columna)
        worksheet.write(x_rows, 53, 'Fecha hasta Nómina', frmt_encabezado_columna)
        # Buscando planillas de sueldos
        x_lote_planillas = self.env['hr.payslip.run'].search([
            ('id', 'in', self.planillas.ids),
            ('company_id', '=', self.company_id.id)
        ])
        x_rows += 1
        if x_lote_planillas:
            for planillas in x_lote_planillas:
                for nomina in planillas.slip_ids:
                    x_horas_extras = 0
                    x_aguinaldomasbono = 0
                    x_bonopag = 0
                    x_sumatod = 0
                    x_bonifajuste = 0
                    x_mdopres = 0
                    x_boni_incentivo = 0
                    x_bon_fija = 0
                    x_bon_variable = 0
                    x_mdoproductividad = 0
                    x_bonasueto = 0
                    x_alimento = 0
                    x_mdoajuste = 0
                    x_reva = 0
                    x_idmp = 0
                    x_salario_base = 0
                    x_salarybrute = 0
                    x_igss_lab_report = 0
                    x_c_igss_lab_report = 0
                    x_isr_asalariados = 0
                    x_ant1 = 0
                    x_ant2 = 0
                    x_ant3 = 0
                    x_deducciones = 0
                    x_salario_devengado = 0
                    x_igss_pat_report = 0
                    x_c_igss_pat_report = 0
                    x_irtra_report = 0
                    x_intecap_report = 0
                    x_bono14 = 0
                    x_aguinaldo = 0
                    x_suma_indemnizacion = 0
                    x_gratificacion = 0
                    x_vacaciones = 0
                    x_devolucionisr = 0
                    x_aginaldopago = 0
                    x_indemnizacion_pago = 0
                    x_pago_vacaciones = 0
                    x_reserva_prestaciones = 0

                    for x_line in nomina.line_ids:
                        if x_line.code == 'BASIC':
                            x_salario_base += x_line.total
                        elif x_line.code == 'BONIN':
                            x_boni_incentivo += x_line.total
                        elif x_line.code == 'BOFIJ':
                            x_bon_fija += x_line.total
                        elif x_line.code == 'MDOA':
                            x_bonifajuste += x_line.total
                        elif x_line.code == 'MDOAS':
                            x_bonasueto += x_line.total
                        elif x_line.code == 'MDOP':
                            x_mdoproductividad += x_line.total
                        elif x_line.code == 'BONPRO':
                            x_bon_variable += x_line.total
                        elif x_line.code == 'MDOALIM':
                            x_alimento += x_line.total
                        elif x_line.code == 'VHEB':
                            x_horas_extras += x_line.total
                        elif x_line.code == 'BHE':
                            x_mdopres += x_line.total
                        elif x_line.code == 'OTREN':
                            x_mdoajuste += x_line.total
                        elif x_line.code == 'GROSS':
                            x_salarybrute += x_line.total
                        elif x_line.code == 'IGSSLABR':
                            x_igss_lab_report += x_line.total
                        elif x_line.code == 'CIGSSLAB':
                            x_c_igss_lab_report += x_line.total
                        elif x_line.code == 'ISRASA':
                            x_isr_asalariados += x_line.total
                        elif x_line.code == 'ANT1':
                            x_ant1 += x_line.total
                        elif x_line.code == 'ANT2':
                            x_ant2 += x_line.total
                        elif x_line.code == 'ANT3':
                            x_ant3 += x_line.total
                        elif x_line.code == 'DEDU':
                            x_deducciones += x_line.total
                        elif x_line.code == 'NET':
                            x_salario_devengado += x_line.total
                        elif x_line.code == 'IGSS PAT':
                            x_igss_pat_report += x_line.total
                        elif x_line.code == 'CIGSSPAT':
                            x_c_igss_pat_report += x_line.total
                        elif x_line.code == 'IRTRA':
                            x_irtra_report += x_line.total
                        elif x_line.code == 'INTECAP':
                            x_intecap_report += x_line.total
                        elif x_line.code == 'BONO14':
                            x_bono14 += x_line.total
                        elif x_line.code == 'AGUINALDO':
                            x_aguinaldo += x_line.total
                        elif x_line.code == 'INDM':
                            x_suma_indemnizacion += x_line.total
                        elif x_line.code == 'VACAC':
                            x_vacaciones += x_line.total
                        elif x_line.code == 'OTRGRATIF':
                            x_gratificacion += x_line.total
                        elif x_line.code == 'DEVISR':
                            x_devolucionisr += x_line.total
                        elif x_line.code == 'BONO14P':
                            x_bonopag += x_line.total
                        elif x_line.code == 'AGUINALDOP':
                            x_aginaldopago += x_line.total
                        elif x_line.code == 'INDEMP':
                            x_indemnizacion_pago += x_line.total
                        elif x_line.code == 'VACACPAG':
                            x_pago_vacaciones += x_line.total


                        elif x_line.code == 'BONO14P' or x_line.code == 'AGUINALDOP':
                            x_aguinaldomasbono += x_line.total

                    x_reserva_prestaciones = x_bono14 + x_aguinaldo + x_suma_indemnizacion + x_vacaciones
                    x_status = nomina.contract_id.estado_contrato.name if nomina.employee_id.contract_id.estado_contrato.name else ''
                    x_dias = (nomina.date_to - nomina.date_from).days + 1
                    x_fecha_ingreso = nomina.contract_id.date_start.strftime('%d/%m/%Y') if nomina.contract_id.date_start else ''
                    x_date_end = nomina.contract_id.date_end.strftime('%d/%m/%Y') if nomina.contract_id.date_end else ''
                    x_fecha_inicio = nomina.date_from.strftime('%d/%m/%Y') if nomina.date_from else ''
                    x_fecha_fin = nomina.date_to.strftime('%d/%m/%Y') if nomina.date_to else ''
                    x_mes = nomina.date_from.month if nomina.date_from else ''
                    x_banco = nomina.employee_id.bank_account_id.bank_id.name if nomina.employee_id.bank_account_id.bank_id.name else ''
                    x_numero_cuenta = nomina.employee_id.bank_account_id.acc_number if nomina.employee_id.bank_account_id.acc_number else  ''

                    if nomina.employee_id.contract_id.analytic_account_id.name and nomina.employee_id.contract_id.analytic_account_id.code:
                        x_centro_costo_name = nomina.employee_id.contract_id.analytic_account_id.name
                        x_centro_costo_code = nomina.employee_id.contract_id.analytic_account_id.code
                        x_centro_costo = '['+x_centro_costo_code+'] ' + x_centro_costo_name
                    else:
                        x_centro_costo = ''

                    x_planilla_name = planillas.name if planillas.name else ''
                    x_departamento = nomina.employee_id.contract_id.department_id.parent_id.name if nomina.employee_id.contract_id.department_id.parent_id.name else ''
                    x_area = nomina.employee_id.department_id.name if nomina.employee_id.department_id.name else ''
                    x_empleado = nomina.employee_id.name if nomina.employee_id.name else ''
                    x_codigo_empleado = nomina.employee_id.codigo_empleado if nomina.employee_id.codigo_empleado else ''
                    x_puesto = nomina.contract_id.job_id.name if nomina.employee_id.job_id.name else ''
                    x_empresa_factura = nomina.contract_id.empresa_facturar.name if nomina.contract_id.empresa_facturar.name else ''
                    x_observaciones = nomina.note if nomina.note else ''

                    if nomina.employee_id.contract_id.analytic_account_id.plan_id.name == 'Default':
                        x_tipo = ''
                    elif nomina.employee_id.contract_id.analytic_account_id.plan_id.name:
                        x_tipo = nomina.employee_id.contract_id.analytic_account_id.plan_id.name
                    else:
                        x_tipo = ''

                    worksheet.write(x_rows, 0, x_mes, detail_emp_1)     #Mes
                    worksheet.write(x_rows, 1, x_planilla_name, detail_emp_1)        #Código de Planilla
                    worksheet.write(x_rows, 2, x_departamento, detail_emp_1) #Departamento
                    worksheet.write(x_rows, 3, x_area, detail_emp_1) #Área
                    worksheet.write(x_rows, 4, x_empleado, detail_emp_1) #Nombre de empleado
                    worksheet.write(x_rows, 5, x_status, detail_emp_1) #Status
                    worksheet.write(x_rows, 6, x_codigo_empleado, detail_emp_1) #Cod. de empleado
                    worksheet.write(x_rows, 7, x_fecha_ingreso, detail_emp_1) #Fecha de ingreso
                    worksheet.write(x_rows, 8, x_date_end, detail_emp_1) #Fecha fin de contrato
                    worksheet.write(x_rows, 9, x_puesto, detail_emp_1) #Puesto
                    worksheet.write(x_rows, 10, x_dias, detail_emp_1) #Días
                    worksheet.write(x_rows, 11, x_salario_base, detail_emp_1) #Salario base
                    worksheet.write(x_rows, 12, x_boni_incentivo, detail_emp_1) #Bonificación Incentivo
                    worksheet.write(x_rows, 13, x_bon_fija, detail_emp_1) #Bonificación Fija
                    worksheet.write(x_rows, 14, x_bonifajuste, detail_emp_1) #Bonificación por ajuste
                    worksheet.write(x_rows, 15, x_bonasueto, detail_emp_1) #Bonificación por asueto
                    worksheet.write(x_rows, 16, x_mdoproductividad + x_bon_variable, detail_emp_1) #Bonificación por productividad
                    worksheet.write(x_rows, 17, x_alimento, detail_emp_1) #Alimentación
                    worksheet.write(x_rows, 18, x_horas_extras, detail_emp_1) #Horas Extras
                    worksheet.write(x_rows, 19, x_mdopres, detail_emp_1) #Bonificación por Horas
                    worksheet.write(x_rows, 20, x_mdoajuste, detail_emp_1) #Bonificaciones Extras
                    worksheet.write(x_rows, 21, x_salarybrute, detail_emp_1) #Salario devengado
                    worksheet.write(x_rows, 22, x_igss_lab_report, detail_emp_1) #Cuota Laboral IGSS
                    worksheet.write(x_rows, 23, x_c_igss_lab_report, detail_emp_1) #Complemento Cuota Laboral IGSS
                    worksheet.write(x_rows, 24, x_isr_asalariados, detail_emp_1) #ISR Asalariados
                    worksheet.write(x_rows, 25, x_ant1, detail_emp_1) #Anticipo 1
                    worksheet.write(x_rows, 26, x_ant2, detail_emp_1) #Anticipo 2
                    worksheet.write(x_rows, 27, x_ant3, detail_emp_1) #Anticipo 3
                    worksheet.write(x_rows, 28, x_deducciones, detail_emp_1) #Total deducciones
                    worksheet.write(x_rows, 29, x_salario_devengado, detail_emp_1) #Salario líquido
                    worksheet.write(x_rows, 30, x_igss_pat_report, detail_emp_1) #Cuota Patronal
                    worksheet.write(x_rows, 31, x_c_igss_pat_report, detail_emp_1) #Complemento Cuota Patronal
                    worksheet.write(x_rows, 32, x_irtra_report, detail_emp_1) #Irtra
                    worksheet.write(x_rows, 33, x_intecap_report, detail_emp_1) #Intecap
                    worksheet.write(x_rows, 34, x_bono14, detail_emp_1) #Bono anual Reserva
                    worksheet.write(x_rows, 35, x_aguinaldo, detail_emp_1) #Aguinaldo Reserva
                    worksheet.write(x_rows, 36, x_suma_indemnizacion, detail_emp_1) #Indemnización Reserva
                    worksheet.write(x_rows, 37, x_vacaciones, detail_emp_1) #Vacaciones Reserva
                    worksheet.write(x_rows, 38, x_reserva_prestaciones, detail_emp_1) #Total Reserva Para Prestaciones
                    worksheet.write(x_rows, 39, x_gratificacion, detail_emp_1) #Gratificación
                    worksheet.write(x_rows, 40, x_devolucionisr, detail_emp_1) #Devolución de ISR
                    worksheet.write(x_rows, 41, x_bonopag, detail_emp_1) #Bono Anual Pago
                    worksheet.write(x_rows, 42, x_aginaldopago, detail_emp_1) #Aguinaldo Pago
                    worksheet.write(x_rows, 43, x_indemnizacion_pago, detail_emp_1) #Indemnización Pago
                    worksheet.write(x_rows, 44, x_pago_vacaciones, detail_emp_1) #Vacaciones Pago
                    worksheet.write(x_rows, 45, x_salario_devengado, detail_emp_1) #Líquido a recibir
                    worksheet.write(x_rows, 46, x_banco, detail_emp_1) #Banco a depositar
                    worksheet.write(x_rows, 47, x_numero_cuenta, detail_emp_1) #Cuenta a Depositar
                    worksheet.write(x_rows, 48, x_observaciones, detail_emp_1) #Observaciones
                    worksheet.write(x_rows, 49, x_centro_costo, detail_emp_1) #centro de costo
                    worksheet.write(x_rows, 50, x_empresa_factura, detail_emp_1) #Empresa que debe Facturar
                    worksheet.write(x_rows, 51, x_tipo, detail_emp_1) #Tipo Facturación
                    # la proxima columna que sea de tipo fecha corta como en excel


                    worksheet.write(x_rows, 52, x_fecha_inicio, detail_emp_1_date)
                    worksheet.write(x_rows, 53, x_fecha_fin, detail_emp_1_date)
                    x_rows += 1
        workbook.close()
        self.write(
            {
                'state': 'get',
                'name': xls_filename,
                'data': base64.b64encode(open(xls_path, 'rb').read())
            }
        )
        return {
            'name': 'Planilla de Sueldos',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new',
        }

class WizardPasivoLaboralConsolidado(models.TransientModel):
    _name = 'wizard.pasivo.laboral.consolidado'
    _description = "Wizard Pasivo Laboral Consolidado"

    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id)
    date_start = fields.Date('Del', required=True)
    date_end = fields.Date('Al', required=True)
    #employee_id = fields.Many2one('hr.employee', string='Empleado', required=True)
    state = fields.Selection([('choose', 'choose'), ('get', 'get')], default='choose')
    name = fields.Char(string='File Name', readonly=True)
    data = fields.Binary(string='File', readonly=True)

    @api.onchange('company_id')
    def onchange_company_id(self):
        domain = [('company_id', '=', self.company_id.id)]
        return {'domain': {'company_id': domain}}

    def got_back(self):
        self.state = 'choose'
        return {
            'name': 'Pasivo Laboral Consolidado',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def check_date(self):
        if self.date_start > self.date_end:
            raise ValidationError(_('La fecha de inicio no puede ser mayor que la fecha de finalización.'))
        #if self.date_start.year != self.date_end.year:
        #     #raise ValidationError(_('El rango de fechas debe estar dentro del mismo año.'))

    def get_selection_label(self, record, field_name):
        # Obtén la definición del campo
        field = record._fields[field_name]
        # Obtén el valor actual del campo
        value = getattr(record, field_name)
        # Busca la etiqueta correspondiente al valor
        label = dict(field.selection).get(value)
        return label
    def print_xls_pasivo_laboral_consolidado(self):
        self.check_date()
        xls_filename = 'Pasivo laboral consolidado.xlsx'
        temp_dir = tempfile.gettempdir()
        xls_path = os.path.join(temp_dir, xls_filename)
        workbook = xlsxwriter.Workbook(xls_path)
        worksheet = workbook.add_worksheet("Pasivo laboral consolidado")
        frmt_folio = workbook.add_format({'bold': True, 'align': 'right', 'font': 'Arial', 'font_size': 6})
        frmt_encabezado = workbook.add_format(
            {'bold': True, 'align': 'center', 'valign': 'vcenter', 'font': 'Arial', 'font_size': 6})
        frmt_encabezado_columna = workbook.add_format(
            {'bold': True, 'align': 'center', 'valign': 'vcenter', 'font': 'Arial', 'font_size': 10, 'border': 1,
             'bg_color': '#DDEBF7', 'text_wrap': True})
        detail_emp_1 = workbook.add_format(
            { 'font': 'Arial', 'font_size': 10, 'border': 1})
        # construir el libro en este espacio de trabajo
        x_nomina = self.env['hr.payslip'].search([
            ('date_from', '>=', self.date_start),
            ('date_to', '<=', self.date_end),
            ('company_id', '=', self.company_id.id)
        ])
        # configuracion columnas
        worksheet.set_column('A:A', 6)
        worksheet.set_column('B:B', 11)
        worksheet.set_column('C:C', 11)
        worksheet.set_column('D:D', 12)
        worksheet.set_column('E:E', 30)
        worksheet.set_column('F:F', 15)
        worksheet.set_column('G:G', 13)
        worksheet.set_column('H:H', 11)
        worksheet.set_column('I:I', 11)
        worksheet.set_column('J:J', 20)
        worksheet.set_column('L:L', 10)
        worksheet.set_column('M:M', 10)
        worksheet.set_column('N:N', 10)
        worksheet.set_column('O:O', 10)

        # Encabezados
        x_rows = 0
        worksheet.write(x_rows, 0, 'Mes', frmt_encabezado_columna)
        worksheet.write(x_rows, 1, 'Fecha Del', frmt_encabezado_columna)
        worksheet.write(x_rows, 2, 'Fecha Al', frmt_encabezado_columna)
        worksheet.write(x_rows, 3, 'Referencia de Nómina', frmt_encabezado_columna)
        worksheet.write(x_rows, 4, 'Nombre de empleado', frmt_encabezado_columna)
        worksheet.write(x_rows, 5, 'Departamento', frmt_encabezado_columna)
        worksheet.write(x_rows, 6, 'Area', frmt_encabezado_columna)
        worksheet.write(x_rows, 7, 'Fecha de contrato', frmt_encabezado_columna)
        worksheet.write(x_rows, 8, 'Status', frmt_encabezado_columna)
        worksheet.write(x_rows, 9, 'Puesto', frmt_encabezado_columna)
        worksheet.write(x_rows, 10, 'Bono Anual', frmt_encabezado_columna)
        worksheet.write(x_rows, 11, 'Aguinaldo', frmt_encabezado_columna)
        worksheet.write(x_rows, 12, 'Indemnización', frmt_encabezado_columna)
        worksheet.write(x_rows, 13, 'Vacaciones', frmt_encabezado_columna)
        worksheet.write(x_rows, 14, 'Total de Prestaciones', frmt_encabezado_columna)
        x_rows += 1

        if x_nomina:
            for nomina in x_nomina:
                x_mes = nomina.date_from.month if nomina.date_from else ''
                x_del = nomina.date_from.strftime('%d-%m-%Y') if nomina.date_from else ''
                x_al = nomina.date_to.strftime('%d-%m-%Y') if nomina.date_to else ''
                x_referencia = nomina.number if nomina.number else ''
                x_fecha_contrato = nomina.employee_id.contract_id.date_start.strftime('%d-%m-%Y') if nomina.employee_id.contract_id.date_start else ''
                x_status = nomina.employee_id.contract_id.estado_contrato.name if nomina.employee_id.contract_id.estado_contrato.name else ''
                x_name = nomina.employee_id.name if nomina.employee_id.name else ''
                x_departamento = nomina.employee_id.contract_id.department_id.parent_id.name if nomina.employee_id.contract_id.department_id.parent_id.name else ''
                x_area = nomina.employee_id.department_id.name if nomina.employee_id.department_id.name else ''
                x_puesto = nomina.employee_id.job_id.name if nomina.employee_id.job_id.name else ''

                x_bono14 = 0
                x_bono14P = 0
                x_aguinaldo = 0
                x_aguinaldoP = 0
                x_suma_indemnizacion = 0
                x_suma_indemnizacionP = 0
                x_vacaciones = 0
                x_vacacionesP = 0
                x_reserva_prestaciones = 0
                for x_line in nomina.line_ids:
                    if x_line.code == 'BONO14':
                        x_bono14 += x_line.total
                    if x_line.code == 'BONO14P':
                        x_bono14P += x_line.total
                    elif x_line.code == 'AGUINALDO':
                        x_aguinaldo += x_line.total
                    elif x_line.code == 'AGUINALDOP':
                        x_aguinaldoP += x_line.total
                    elif x_line.code == 'INDM':
                        x_suma_indemnizacion += x_line.total
                    elif x_line.code == 'INDEMP':
                        x_suma_indemnizacionP += x_line.total
                    elif x_line.code == 'VACAC':
                        x_vacaciones += x_line.total
                    elif x_line.code == 'VACACPAG':
                        x_vacacionesP += x_line.total
                x_reserva_prestaciones = (x_bono14-x_bono14P) + (x_aguinaldo-x_aguinaldoP) + (x_suma_indemnizacion-x_suma_indemnizacionP) + (x_vacaciones-x_vacacionesP)
                worksheet.write(x_rows, 0, x_mes, detail_emp_1)
                worksheet.write(x_rows, 1, x_del, detail_emp_1)
                worksheet.write(x_rows, 2, x_al, detail_emp_1)
                worksheet.write(x_rows, 3, x_referencia, detail_emp_1)
                worksheet.write(x_rows, 4, x_name, detail_emp_1)
                worksheet.write(x_rows, 5, x_departamento, detail_emp_1)
                worksheet.write(x_rows, 6, x_area, detail_emp_1)
                worksheet.write(x_rows, 7, x_fecha_contrato, detail_emp_1)
                worksheet.write(x_rows, 8, x_status, detail_emp_1)
                worksheet.write(x_rows, 9, x_puesto, detail_emp_1)
                worksheet.write(x_rows, 10, x_bono14-x_bono14P, detail_emp_1)
                worksheet.write(x_rows, 11, x_aguinaldo-x_aguinaldoP, detail_emp_1)
                worksheet.write(x_rows, 12, x_suma_indemnizacion-x_suma_indemnizacionP, detail_emp_1)
                worksheet.write(x_rows, 13, x_vacaciones-x_vacacionesP, detail_emp_1)
                worksheet.write(x_rows, 14, x_reserva_prestaciones, detail_emp_1)
                x_rows += 1

        workbook.close()
        self.write(
            {
                'state': 'get',
                'name': xls_filename,
                'data': base64.b64encode(open(xls_path, 'rb').read())
            }
        )
        return {
            'name': 'Pasivo Laboral Consolidado',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new',
        }

class WizardPasivoLaboralEmpleado(models.TransientModel):
    _name = 'wizard.pasivo.laboral.empleado'
    _description = "Wizard Pasivo Laboral Empleado"

    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id)
    date_start = fields.Date('Del', required=True)
    date_end = fields.Date('Al', required=True)
    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True)
    state = fields.Selection([('choose', 'choose'), ('get', 'get')], default='choose')
    name = fields.Char(string='File Name', readonly=True)
    data = fields.Binary(string='File', readonly=True)

    @api.onchange('company_id')
    def onchange_company_id(self):
        domain = [('company_id', '=', self.company_id.id)]
        return {'domain': {'company_id': domain}}

    def got_back(self):
        self.state = 'choose'
        return {
            'name': 'Pasivo Laboral Empleado',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def check_date(self):
        if self.date_start > self.date_end:
            raise ValidationError(_('La fecha de inicio no puede ser mayor que la fecha de finalización.'))
        #if self.date_start.year != self.date_end.year:
        #     #raise ValidationError(_('El rango de fechas debe estar dentro del mismo año.'))

    def get_selection_label(self, record, field_name):
        # Obtén la definición del campo
        field = record._fields[field_name]
        # Obtén el valor actual del campo
        value = getattr(record, field_name)
        # Busca la etiqueta correspondiente al valor
        label = dict(field.selection).get(value)
        return label
    def print_xls_pasivo_laboral_empleado(self):
        self.check_date()
        xls_filename = 'Pasivo laboral Empleado.xlsx'
        temp_dir = tempfile.gettempdir()
        xls_path = os.path.join(temp_dir, xls_filename)
        workbook = xlsxwriter.Workbook(xls_path)
        worksheet = workbook.add_worksheet("Pasivo laboral empleado")
        frmt_folio = workbook.add_format({'bold': True, 'align': 'right', 'font': 'Arial', 'font_size': 6})
        frmt_encabezado = workbook.add_format(
            {'bold': True, 'align': 'center', 'valign': 'vcenter', 'font': 'Arial', 'font_size': 6})
        frmt_encabezado_columna = workbook.add_format(
            {'bold': True, 'align': 'center', 'valign': 'vcenter', 'font': 'Arial', 'font_size': 10, 'border': 1,
             'bg_color': '#DDEBF7', 'text_wrap': True})
        frmt_encabezado_columna2 = workbook.add_format(
            {'bold': True, 'align': 'center', 'valign': 'vcenter', 'font': 'Arial', 'font_size': 10, 'border': 1, 'text_wrap': True})
        detail_emp_1 = workbook.add_format(
            { 'font': 'Arial', 'font_size': 10, 'border': 1 })
        detail_emp_2 = workbook.add_format(
            { 'bold': True, 'font': 'Arial', 'font_size': 10, 'border': 1 })
        # construir el libro en este espacio de trabajo
        x_nomina = self.env['hr.payslip'].search([
            ('date_from', '>=', self.date_start),
            ('date_to', '<=', self.date_end),
            ('company_id', '=', self.company_id.id),
            ('employee_id', '=', self.employee_id.id)
        ])
        # configuracion columnas
        worksheet.set_column('A:A', 6)
        worksheet.set_column('B:B', 11)
        worksheet.set_column('C:C', 11)
        worksheet.set_column('D:D', 12)
        worksheet.set_column('E:E', 30)
        worksheet.set_column('F:F', 15)
        worksheet.set_column('G:G', 13)
        worksheet.set_column('H:H', 11)
        worksheet.set_column('I:I', 11)
        worksheet.set_column('J:J', 20)
        worksheet.set_column('L:L', 10)
        worksheet.set_column('M:M', 10)
        worksheet.set_column('N:N', 10)
        worksheet.set_column('O:O', 10)
        # Encabezados
        x_rows = 0
        worksheet.write(x_rows, 0, 'Mes', frmt_encabezado_columna)
        worksheet.write(x_rows, 1, 'Fecha Del', frmt_encabezado_columna)
        worksheet.write(x_rows, 2, 'Fecha Al', frmt_encabezado_columna)
        worksheet.write(x_rows, 3, 'Referencia de Nómina', frmt_encabezado_columna)
        worksheet.write(x_rows, 4, 'Nombre de empleado', frmt_encabezado_columna)
        worksheet.write(x_rows, 5, 'Departamento', frmt_encabezado_columna)
        worksheet.write(x_rows, 6, 'Area', frmt_encabezado_columna)
        worksheet.write(x_rows, 7, 'Fecha de contrato', frmt_encabezado_columna)
        worksheet.write(x_rows, 8, 'Status', frmt_encabezado_columna)
        worksheet.write(x_rows, 9, 'Puesto', frmt_encabezado_columna)
        worksheet.write(x_rows, 10, 'Bono Anual', frmt_encabezado_columna)
        worksheet.write(x_rows, 11, 'Aguinaldo', frmt_encabezado_columna)
        worksheet.write(x_rows, 12, 'Indemnización', frmt_encabezado_columna)
        worksheet.write(x_rows, 13, 'Vacaciones', frmt_encabezado_columna)
        worksheet.write(x_rows, 14, 'Total de Prestaciones', frmt_encabezado_columna)
        x_rows += 1
        x_total_bono14 = 0
        x_total_aguinaldo = 0
        x_total_suma_indemnizacion = 0
        x_total_vacaciones = 0
        x_total_reserva_prestaciones = 0
        if x_nomina:
            for nomina in x_nomina:
                x_mes = nomina.date_from.month if nomina.date_from else ''
                x_del = nomina.date_from.strftime('%d-%m-%Y') if nomina.date_from else ''
                x_al = nomina.date_to.strftime('%d-%m-%Y') if nomina.date_to else ''
                x_referencia = nomina.number if nomina.number else ''
                x_fecha_contrato = nomina.employee_id.contract_id.date_start.strftime('%d-%m-%Y') if nomina.employee_id.contract_id.date_start else ''
                x_status = nomina.employee_id.contract_id.estado_contrato.name if nomina.employee_id.contract_id.estado_contrato.name else ''
                x_name = nomina.employee_id.name if nomina.employee_id.name else ''
                x_departamento = nomina.employee_id.contract_id.department_id.parent_id.name if nomina.employee_id.contract_id.department_id.parent_id.name else ''
                x_area = nomina.employee_id.department_id.name if nomina.employee_id.department_id.name else ''
                x_puesto = nomina.employee_id.job_id.name if nomina.employee_id.job_id.name else ''

                x_bono14 = 0
                x_bono14P = 0
                x_aguinaldo = 0
                x_aguinaldoP = 0
                x_suma_indemnizacion = 0
                x_suma_indemnizacionP = 0
                x_vacaciones = 0
                x_vacacionesP = 0
                x_reserva_prestaciones = 0
                for x_line in nomina.line_ids:
                    if x_line.code == 'BONO14':
                        x_bono14 += x_line.total
                    if x_line.code == 'BONO14P':
                        x_bono14P += x_line.total
                    elif x_line.code == 'AGUINALDO':
                        x_aguinaldo += x_line.total
                    elif x_line.code == 'AGUINALDOP':
                        x_aguinaldoP += x_line.total
                    elif x_line.code == 'INDM':
                        x_suma_indemnizacion += x_line.total
                    elif x_line.code == 'INDEMP':
                        x_suma_indemnizacionP += x_line.total
                    elif x_line.code == 'VACAC':
                        x_vacaciones += x_line.total
                    elif x_line.code == 'VACACPAG':
                        x_vacacionesP += x_line.total
                x_reserva_prestaciones = (x_bono14-x_bono14P) + (x_aguinaldo-x_aguinaldoP) + (x_suma_indemnizacion-x_suma_indemnizacionP) + (x_vacaciones-x_vacacionesP)
                worksheet.write(x_rows, 0, x_mes, detail_emp_1)
                worksheet.write(x_rows, 1, x_del, detail_emp_1)
                worksheet.write(x_rows, 2, x_al, detail_emp_1)
                worksheet.write(x_rows, 3, x_referencia, detail_emp_1)
                worksheet.write(x_rows, 4, x_name, detail_emp_1)
                worksheet.write(x_rows, 5, x_departamento, detail_emp_1)
                worksheet.write(x_rows, 6, x_area, detail_emp_1)
                worksheet.write(x_rows, 7, x_fecha_contrato, detail_emp_1)
                worksheet.write(x_rows, 8, x_status, detail_emp_1)
                worksheet.write(x_rows, 9, x_puesto, detail_emp_1)
                worksheet.write(x_rows, 10, x_bono14-x_bono14P, detail_emp_1)
                worksheet.write(x_rows, 11, x_aguinaldo-x_aguinaldoP, detail_emp_1)
                worksheet.write(x_rows, 12, x_suma_indemnizacion-x_suma_indemnizacionP, detail_emp_1)
                worksheet.write(x_rows, 13, x_vacaciones-x_vacacionesP, detail_emp_1)
                worksheet.write(x_rows, 14, x_reserva_prestaciones, detail_emp_1)
                x_total_bono14 += (x_bono14-x_bono14P)
                x_total_aguinaldo += (x_aguinaldo-x_aguinaldoP)
                x_total_suma_indemnizacion += (x_suma_indemnizacion-x_suma_indemnizacionP)
                x_total_vacaciones += (x_vacaciones-x_vacacionesP)
                x_total_reserva_prestaciones += x_reserva_prestaciones
                x_rows += 1

        worksheet.write(x_rows, 4, self.employee_id.name , frmt_encabezado_columna2)
        worksheet.write(x_rows, 10, x_total_bono14, detail_emp_2)
        worksheet.write(x_rows, 11, x_total_aguinaldo, detail_emp_2)
        worksheet.write(x_rows, 12, x_total_suma_indemnizacion, detail_emp_2)
        worksheet.write(x_rows, 13, x_total_vacaciones, detail_emp_2)
        worksheet.write(x_rows, 14, x_total_reserva_prestaciones, detail_emp_2)

        workbook.close()
        self.write(
            {
                'state': 'get',
                'name': xls_filename,
                'data': base64.b64encode(open(xls_path, 'rb').read())
            }
        )
        return {
            'name': 'Pasivo Laboral Empleado',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new',
        }

class WizardReporteLiquidacionEmpleados(models.TransientModel):
    _name = 'wizard.reporte.liquidacion.empleados'
    _description = "Wizard Reporte Liquidación Empleados"

    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id)
    date_start = fields.Date('Del', required=True)
    date_end = fields.Date('Al', required=True)
    employee_id = fields.Many2many(
        'hr.employee',
        string='Empleado',
        required=True,
        domain=[
            '|',
            ('active', '=', True),
            ('active', '=', False),
            ('contract_id.estado_contrato.name', 'not in', ['Proveedores', 'Practicante'])
        ],
        context={'active_test': False}
    )
    state = fields.Selection([('choose', 'choose'), ('get', 'get')], default='choose')
    name = fields.Char(string='File Name', readonly=True)
    data = fields.Binary(string='File', readonly=True)

    @api.onchange('company_id')
    def onchange_company_id(self):
        domain = [('company_id', '=', self.company_id.id)]
        return {'domain': {'company_id': domain}}

    def got_back(self):
        self.state = 'choose'
        return {
            'name': 'Reporte Liquidación Empleados',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def check_date(self):
        if self.date_start > self.date_end:
            raise ValidationError(_('La fecha de inicio no puede ser mayor que la fecha de finalización.'))
        #if self.date_start.year != self.date_end.year:
        #     #raise ValidationError(_('El rango de fechas debe estar dentro del mismo año.'))

    def get_selection_label(self, record, field_name):
        # Obtén la definición del campo
        field = record._fields[field_name]
        # Obtén el valor actual del campo
        value = getattr(record, field_name)
        # Busca la etiqueta correspondiente al valor
        label = dict(field.selection).get(value)
        return label
    def print_xls_reporte_liquidacion_empleados(self):
        self.check_date()
        xls_filename = 'Reporte Liquidación Empleados.xlsx'
        temp_dir = tempfile.gettempdir()
        xls_path = os.path.join(temp_dir, xls_filename)
        workbook = xlsxwriter.Workbook(xls_path)
        worksheet = workbook.add_worksheet("Reporte Liquidación Empleados")
        frmt_folio = workbook.add_format({'bold': True, 'align': 'right', 'font': 'Arial', 'font_size': 6})
        frmt_encabezado = workbook.add_format(
            {'bold': True, 'align': 'center', 'valign': 'vcenter', 'font': 'Arial', 'font_size': 6})
        frmt_encabezado_columna = workbook.add_format(
            {'bold': True, 'align': 'center', 'valign': 'vcenter', 'font': 'Arial', 'font_size': 10, 'border': 1,
             'bg_color': '#DDEBF7', 'text_wrap': True})
        frmt_encabezado_columna2 = workbook.add_format(
            {'bold': True, 'align': 'center', 'valign': 'vcenter', 'font': 'Arial', 'font_size': 10, 'border': 1, 'text_wrap': True})
        detail_emp_1 = workbook.add_format(
            { 'font': 'Arial', 'font_size': 10, 'border': 1 })
        detail_emp_2 = workbook.add_format(
            { 'bold': True, 'font': 'Arial', 'font_size': 10, 'border': 1 })
        # construir el libro en este espacio de trabajo

        # configuracion columnas
        worksheet.set_column('A:A', 8)
        worksheet.set_column('B:B', 14)
        worksheet.set_column('C:C', 30)
        worksheet.set_column('D:D', 25)
        worksheet.set_column('E:E', 12)
        worksheet.set_column('F:F', 12)
        worksheet.set_column('G:G', 12)
        worksheet.set_column('H:H', 12)
        worksheet.set_column('I:I', 14)
        worksheet.set_column('J:J', 12)
        worksheet.set_column('K:K', 12)
        worksheet.set_column('L:L', 12)
        worksheet.set_column('M:M', 15)
        worksheet.set_column('N:N', 12)
        worksheet.set_column('O:O', 12)
        worksheet.set_column('P:P', 12)
        worksheet.set_column('Q:Q', 12)

        # Encabezados
        x_rows = 0
        worksheet.write(x_rows, 0, 'Código', frmt_encabezado_columna)
        worksheet.write(x_rows, 1, 'NIT Empleado', frmt_encabezado_columna)
        worksheet.write(x_rows, 2, 'Nombre Empleado', frmt_encabezado_columna)
        worksheet.write(x_rows, 3, 'Puesto', frmt_encabezado_columna)
        worksheet.write(x_rows, 4, 'Fecha de Ingreso', frmt_encabezado_columna)
        worksheet.write(x_rows, 5, 'Fecha de Finalización', frmt_encabezado_columna)
        worksheet.write(x_rows, 6, 'Sumatoria total sueldo Base', frmt_encabezado_columna)
        worksheet.write(x_rows, 7, 'Sumatoria total de Horas Extras', frmt_encabezado_columna)
        worksheet.write(x_rows, 8, 'Sumatoria total de Bonificación Incentivo', frmt_encabezado_columna)
        worksheet.write(x_rows, 9, 'Sumatoria total de Otras Bonificaciones', frmt_encabezado_columna)
        worksheet.write(x_rows, 10, 'Sumatoria total de Aguinaldo', frmt_encabezado_columna)
        worksheet.write(x_rows, 11, 'Sumatoria total de Bono 14', frmt_encabezado_columna)
        worksheet.write(x_rows, 12, 'Sumatoria total de Gratificación', frmt_encabezado_columna)
        worksheet.write(x_rows, 13, 'Sumatoria total de Indemnización', frmt_encabezado_columna)
        worksheet.write(x_rows, 14, 'Sumatoria total de Vacaciones', frmt_encabezado_columna)
        worksheet.write(x_rows, 15, 'Sumatoria total de Cuota IGSS', frmt_encabezado_columna)
        worksheet.write(x_rows, 16, 'Monto Ultima Retención Realizada', frmt_encabezado_columna)
        x_rows += 1

        # x_employees = self.env['hr.employee'].search([
        #     ('company_id', '=', self.company_id.id),
        #     ('id', '=', self.employee_id.ids)
        # ])
        x_employees = self.env['hr.employee'].with_context(active_test=False).search([
            ('company_id', '=', self.company_id.id),
            ('id', 'in', self.employee_id.ids)
        ])
        if x_employees:
            for x_employee in x_employees:
                x_nominas = self.env['hr.payslip'].search([
                    ('date_to', '>=', self.date_start),
                    ('date_to', '<=', self.date_end),
                    ('company_id', '=', self.company_id.id),
                    ('employee_id', '=', x_employee.id)
                    # ('state','!=','draft')
                ],order='date_from desc')
                if x_nominas:
                    x_codigo = x_employee.registration_number if x_employee.registration_number else ''
                    x_nit = x_employee.work_contact_id.vat if x_employee.work_contact_id.vat else ''
                    x_name = x_employee.name if x_employee.name else ''
                    x_puesto = x_employee.job_id.name if x_employee.job_id.name else ''
                    x_fecha_ingreso = x_employee.first_contract_date.strftime('%d-%m-%Y') if x_employee.first_contract_date else ''
                    x_fecha_finalizacion = x_employee.contract_id.date_end.strftime('%d-%m-%Y') if x_employee.contract_id.date_end else ''
                    worksheet.write(x_rows, 0, x_codigo, detail_emp_1)
                    worksheet.write(x_rows, 1, x_nit, detail_emp_1)
                    worksheet.write(x_rows, 2, x_name, detail_emp_1)
                    worksheet.write(x_rows, 3, x_puesto, detail_emp_1)
                    worksheet.write(x_rows, 4, x_fecha_ingreso, detail_emp_1)
                    worksheet.write(x_rows, 5, x_fecha_finalizacion, detail_emp_1)
                    x_sueldo_base = 0
                    x_horas_extras = 0
                    x_bonificacion_incentivo = 0
                    x_otras_bonificaciones = 0
                    x_aguinaldo = 0
                    x_bono14 = 0
                    x_gratificacion = 0
                    x_indemnizacion = 0
                    x_vacaciones = 0
                    x_cuota_igss = 0
                    x_isr_Asalariado = 0
                    x_devolucion_isr = 0
                    ultimo_mes = 0
                    for nomina in x_nominas:
                        if nomina.date_from.month > ultimo_mes:
                            ultimo_mes = nomina.date_from.month

                    for x_nomina in x_nominas:
                        for x_line in x_nomina.line_ids:
                            if x_line.code == 'BASIC':
                                x_sueldo_base += x_line.total
                            elif x_line.code == 'VHEB':
                                x_horas_extras += x_line.total
                            elif x_line.code == 'BONIN':
                                x_bonificacion_incentivo += x_line.total
                            elif x_line.code == 'BOFIJ' or x_line.code == 'MDOA' or x_line.code =='MDOAS' or x_line.code == 'MDOP' or x_line.code == 'BONPRO' or x_line.code == 'MDOALIM' or x_line.code == 'BHE' or x_line.code == 'OTREN' :
                                x_otras_bonificaciones += x_line.total
                            elif x_line.code == 'AGUINALDOP':
                                x_aguinaldo += x_line.total
                            elif x_line.code == 'BONO14P':
                                x_bono14 += x_line.total
                            elif x_line.code == 'OTRGRATIF':
                                x_gratificacion += x_line.total
                            elif x_line.code == 'INDEMP':
                                x_indemnizacion += x_line.total
                            elif x_line.code == 'VACACPAG':
                                x_vacaciones += x_line.total
                            elif x_line.code == 'IGSSLABR':
                                x_cuota_igss += abs(x_line.total)
                            elif x_line.code == 'ISRASA' and x_nomina.date_from.month == ultimo_mes:
                                x_isr_Asalariado += abs(x_line.total)
                            elif x_line.code == 'DEVISR' and x_nomina.date_from.month == ultimo_mes:
                                x_devolucion_isr += abs(x_line.total)

                    worksheet.write(x_rows, 6, abs(x_sueldo_base), detail_emp_1)
                    worksheet.write(x_rows, 7, abs(x_horas_extras), detail_emp_1)
                    worksheet.write(x_rows, 8, abs(x_bonificacion_incentivo), detail_emp_1)
                    worksheet.write(x_rows, 9, abs(x_otras_bonificaciones), detail_emp_1)
                    worksheet.write(x_rows, 10, abs(x_aguinaldo), detail_emp_1)
                    worksheet.write(x_rows, 11, abs(x_bono14), detail_emp_1)
                    worksheet.write(x_rows, 12, abs(x_gratificacion), detail_emp_1)
                    worksheet.write(x_rows, 13, abs(x_indemnizacion), detail_emp_1)
                    worksheet.write(x_rows, 14, abs(x_vacaciones), detail_emp_1)
                    worksheet.write(x_rows, 15, abs(x_cuota_igss), detail_emp_1)
                    worksheet.write(x_rows, 16, x_isr_Asalariado-x_devolucion_isr, detail_emp_1)
                    x_rows += 1

        workbook.close()
        self.write(
            {
                'state': 'get',
                'name': xls_filename,
                'data': base64.b64encode(open(xls_path, 'rb').read())
            }
        )
        return {
            'name': 'Reporte Liquidación Empleados',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new',
        }



