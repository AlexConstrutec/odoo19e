# -*- coding: utf-8 -*-
##############################################################################
#
# Copyright 2023 SIESA
#
##############################################################################
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

import math
from odoo.tools.misc import formatLang

class wizard_inventory_valuation(models.TransientModel):
    _name = 'wizard.report.financial'
    _description = "Wizard Report Financial"
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id)
    warehouse_ids = fields.Many2many('stock.warehouse', string='Warehouse')
    location_ids = fields.Many2many('stock.location', string='Location')
    start_date = fields.Date(string="Start Date")
    end_date = fields.Date(string="End Date")

    anio = fields.Integer(string="Año")
    mes_de = fields.Selection([('1','Enero'),('2','Febrero'),('3','Marzo'),('4','Abril'),('5','Mayo'),('6','Junio'),('7','Julio'),('8','Agosto'),('9','Septiembre'),('10','Octubre'),('11','Noviembre'),('12','Diciembre')],string="De")
    mes_a = fields.Selection(
        [('1', 'Enero'), ('2', 'Febrero'), ('3', 'Marzo'), ('4', 'Abril'), ('5', 'Mayo'), ('6', 'Junio'),
         ('7', 'Julio'), ('8', 'Agosto'), ('9', 'Septiembre'), ('10', 'Octubre'), ('11', 'Noviembre'),
         ('12', 'Diciembre')], string="A")
    folio = fields.Integer(string="Folio")

    filter_by = fields.Selection([('product', 'Product'), ('category', 'Category')], string="Filter By")
    group_by_categ = fields.Boolean(string="Group By Category")
    state = fields.Selection([('choose', 'choose'), ('get', 'get')], default='choose')
    name = fields.Char(string='File Name', readonly=True)
    data = fields.Binary(string='File', readonly=True)
    product_ids = fields.Many2many('product.product', string="Products")
    category_ids = fields.Many2many('product.category', string="Categories")

    @api.onchange('company_id')
    def onchange_company_id(self):
        domain = [('id', 'in', self.env.user.company_ids.ids)]
        if self.company_id:
            self.warehouse_ids = False
            self.location_ids = False
        return {'domain':{'company_id':domain}}

    @api.onchange('warehouse_ids')
    def onchange_warehouse_ids(self):
        stock_location_obj = self.env['stock.location']
        location_ids = stock_location_obj.search([('usage', '=', 'internal'), ('company_id', '=', self.company_id.id)])
        addtional_ids = []
        if self.warehouse_ids:
            for warehouse in self.warehouse_ids:
                addtional_ids.extend([y.id for y in stock_location_obj.search([('location_id', 'child_of', warehouse.view_location_id.id), ('usage', '=', 'internal')])])
            self.location_ids = False
        return {'domain':{'location_ids':[('id', 'in', addtional_ids)]}}

    def check_date_range(self):
        if self.end_date < self.start_date:
            raise ValidationError(_('End Date should be greater than Start Date.'))

    def check_mes(self):
        if int(self.mes_de) > int(self.mes_a):
            raise ValidationError(_('Mes De debe ser anterior a mes A.'))

    @api.onchange('filter_by')
    def onchange_filter_by(self):
        self.product_ids = False
        self.category_ids = False

    def print_report(self):
        self.check_date_range()
        datas = {'form':
                    {
                        'company_id': self.company_id.id,
                        'warehouse_ids': [y.id for y in self.warehouse_ids],
                        'location_ids': self.location_ids.ids or False,
                        'start_date': self.start_date,
                        'end_date': self.end_date,
                        'id': self.id,
                        'product_ids': self.product_ids.ids,
                        'product_categ_ids': self.category_ids.ids
                    },
                }
        return self.env.ref('account_report_financial.action_report_financial_template').report_action(self, data=datas)

    def go_back(self):
        self.state = 'choose'
        return {
            'name': 'Report Financial',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new'
        }

    def go_back_mayor(self):
        self.state = 'choose'
        return {
            'name': 'Report Financial Mayor',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new'
        }

    def print_xls_report_financial(self):
        self.check_date_range()
        self.check_mes()
        #company_id = self.env['res.company'].browse(self._context.get('allowed_company_ids'))
        #Edvin 13-02-2024 automatizando la obtención del directorio temporal
        xls_filename = 'Libro Diario.xlsx'
        temp_dir = tempfile.gettempdir()
        xls_path = os.path.join(temp_dir, xls_filename)
        workbook = xlsxwriter.Workbook(xls_path)
        report_in_sql = self.env['report.account_report_financial.report_financial']

        header_merge_format = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                                   'font': 'Arial','font_size': 10})
        right_format = workbook.add_format({'bold': False, 'align': 'right', \
                                                   'font': 'Arial', 'font_size': 10})

        header_data_format = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                                  'font': 'Arial','font_size': 10, 'border': 1})
        header_data_format_dia = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                                  'font': 'Arial', 'font_size': 10, 'border': 1})

        detail_monetary_format = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'border': 1,
                                       'num_format': 'Q#,##0.00'})
        detail_monetary_format_bold = workbook.add_format({'bold' : True, 'align': 'right', 'font': 'Arial', 'font_size': 10, 'border': 1,
                                       'num_format': 'Q#,##0.00'})
        detail_monetary_format_bold_dia = workbook.add_format(
            {'bold': True, 'align': 'right', 'font': 'Arial', 'font_size': 10, 'border': 1,
                                       'num_format': 'Q#,##0.00'})
        detail_center_format = workbook.add_format({'align': 'center', 'font': 'Arial', 'font_size': 10, 'border': 1})

        detail_description_format = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 10, 'border': 1})
        detail_description_format_dia = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 10, 'border': 1})

        detail_description_format_dia.set_bottom(6)
        header_data_format_dia.set_bottom(6)
        detail_monetary_format_bold_dia.set_bottom(6)
        # Por cada bodega

        # --------------------------------------------------------------------------------------------------------------
        # -------------------------------------------------QUERY--------------------------------------------------------
        consulta = report_in_sql.get_libro_diario(self)
        # -------------------------------------------------QUERY--------------------------------------------------------
        worksheet = workbook.add_worksheet("Libro Diario")
        worksheet.set_portrait()
        worksheet.set_page_view()
        worksheet.set_paper(1)
        worksheet.set_margins(0.7,0.7,0.7,0.7)
        # Tamaños
        worksheet.set_column('A:A', 7)
        worksheet.set_column('B:B', 50)
        worksheet.set_column('C:C', 15)
        worksheet.set_column('D:D', 15)
        # Empieza detalle
        x_rows = 0 # Linea a imprimir
        x_page = 0 # Numero de pagina
        x_max_rows = 47 # Maximo de lineas por pagina
        x_row_page = 0 # Linea actual vrs maximo de lineas
        x_last_partida = 'vacio'
        x_suma_debe = 0
        x_suma_haber = 0
        x_iteracion = 0
        #Edvin desde aquí empieza la construcción del libro diario
        if consulta:
            x_total_row_count = len(consulta)
            #for aml in account_move_line:
            for linea in consulta: # resultado query
                x_iteracion += 1
                if x_row_page < x_max_rows:  # Estamos en ciclo
                    # ---------------------------- Encabezado ----------------------------------------------------------
                    if x_row_page == 0:  # Nueva pagina
                        worksheet.write(x_rows, 3, "Folio: " + str(self.folio + x_page), right_format)
                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3, self.company_id.name,
                                              header_merge_format)  # Encabezado
                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3, "NIT: " + self.company_id.partner_id.vat,
                                              header_merge_format)  # Encabezado
                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3, "Libro Diario", header_merge_format)  # Encabezado
                        num_days = monthrange(self.anio, int(self.mes_a))[1]
                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3, str("Del 01 de " + str(
                            dict(self._fields['mes_de'].selection).get(self.mes_de)) + " de " + str(
                            self.anio) + " Al " + str(
                            num_days) + " de " + str(
                            dict(self._fields['mes_a'].selection).get(self.mes_a)) + " de " + str(
                            self.anio)), header_merge_format)  # Encabezado
                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3, "(EXPRESADO EN QUETZALES)",
                                              header_merge_format)  # Encabezado
                        x_rows += 2
                        x_row_page += 2

                        worksheet.write(x_rows, 0, 'PDA', header_data_format)
                        worksheet.write(x_rows, 1, 'Cuenta', header_data_format)
                        worksheet.write(x_rows, 2, 'Debe', header_data_format)
                        worksheet.write(x_rows, 3, 'Haber', header_data_format)
                        x_row_page += 1
                    # ---------------------------- Fin Encabezado ----------------------------------------------------------
                    if x_last_partida == str(linea.get('partida')):  # estamos en la misma cuenta
                        if x_row_page == x_max_rows - 1:  # Estamos en la penultima linea
                            x_rows += 1
                            x_row_page = 0
                            worksheet.write(x_rows, 0, '', detail_description_format)
                            worksheet.write(x_rows, 1, 'VAN', header_data_format)
                            worksheet.write(x_rows, 2, float(x_suma_debe), detail_monetary_format_bold)
                            worksheet.write(x_rows, 3, float(x_suma_haber), detail_monetary_format_bold)

                            # Encabezado 1
                            x_rows += 1
                            x_row_page += 1
                            x_page += 1
                            worksheet.write(x_rows, 3, "Folio: " + str(self.folio + x_page), right_format)
                            x_rows += 1
                            x_row_page += 1
                            worksheet.merge_range(x_rows, 0, x_rows, 3, self.company_id.name,
                                                  header_merge_format)  # Encabezado
                            x_rows += 1
                            x_row_page += 1
                            worksheet.merge_range(x_rows, 0, x_rows, 3, "NIT: " + self.company_id.partner_id.vat,
                                                  header_merge_format)  # Encabezado
                            x_rows += 1
                            x_row_page += 1
                            worksheet.merge_range(x_rows, 0, x_rows, 3, "Libro Diario",
                                                  header_merge_format)  # Encabezado
                            num_days = monthrange(self.anio, int(self.mes_a))[1]
                            x_rows += 1
                            x_row_page += 1
                            worksheet.merge_range(x_rows, 0, x_rows, 3, str("Del 01 de " + str(
                                dict(self._fields['mes_de'].selection).get(self.mes_de)) + " de " + str(
                                self.anio) + " Al " + str(
                                num_days) + " de " + str(
                                dict(self._fields['mes_a'].selection).get(self.mes_a)) + " de " + str(
                                self.anio)), header_merge_format)  # Encabezado
                            x_rows += 1
                            x_row_page += 1
                            worksheet.merge_range(x_rows, 0, x_rows, 3, "(EXPRESADO EN QUETZALES)",
                                                  header_merge_format)  # Encabezado
                            x_rows += 2
                            x_row_page += 2
                            worksheet.write(x_rows, 0, 'PDA', header_data_format)
                            worksheet.write(x_rows, 1, 'Cuenta', header_data_format)
                            worksheet.write(x_rows, 2, 'Debe', header_data_format)
                            worksheet.write(x_rows, 3, 'Haber', header_data_format)

                            x_rows += 1
                            x_row_page += 1
                            worksheet.write(x_rows, 0, '', detail_description_format)
                            worksheet.write(x_rows, 1, 'VIENEN', header_data_format)
                            worksheet.write(x_rows, 2, float(x_suma_debe), detail_monetary_format_bold)
                            worksheet.write(x_rows, 3, float(x_suma_haber), detail_monetary_format_bold)

                            x_rows += 1
                            x_row_page += 1
                            worksheet.write(x_rows, 0, "", detail_description_format)
                            worksheet.write(x_rows, 1, str(linea.get('codigo')) + " " + str(linea.get('cuenta')),
                                            detail_description_format)
                            worksheet.write(x_rows, 2, float(linea.get('debe')), detail_monetary_format)
                            worksheet.write(x_rows, 3, float(linea.get('haber')), detail_monetary_format)
                            x_suma_debe += float(linea.get('debe'))
                            x_suma_haber += float(linea.get('haber'))
                        else: # No estamos en la ultima linea, estamos en la misma cuenta
                            x_rows += 1
                            x_row_page += 1
                            worksheet.write(x_rows, 0, "", detail_description_format)
                            worksheet.write(x_rows, 1, str(linea.get('codigo'))+" "+ str(linea.get('cuenta')),
                                            detail_description_format)
                            worksheet.write(x_rows, 2, float(linea.get('debe')), detail_monetary_format)
                            worksheet.write(x_rows, 3, float(linea.get('haber')), detail_monetary_format)
                            x_suma_debe += float(linea.get('debe'))
                            x_suma_haber += float(linea.get('haber'))
                    else: # no estamos en la misma cuenta
                        if x_row_page == x_max_rows - 1:  # Estamos en la penultima linea
                            x_rows += 1
                            x_row_page = 0

                            worksheet.write(x_rows, 0, '', detail_description_format_dia)
                            worksheet.write(x_rows, 1, 'V/Movimientos del dia', header_data_format_dia)
                            worksheet.write(x_rows, 2, float(x_suma_debe), detail_monetary_format_bold_dia)
                            worksheet.write(x_rows, 3, float(x_suma_haber), detail_monetary_format_bold_dia)

                            x_suma_haber = 0  # reseteamos el van y vienen
                            x_suma_debe = 0  # reseteamos el van y vienen
                            # imprimir encabezado porque cambia de cuenta y hay que imprimirlo en nueva pagina
                            # Encabezado 2
                            x_rows += 1
                            x_row_page += 1
                            x_page += 1
                            worksheet.write(x_rows, 3, "Folio: " + str(self.folio + x_page), right_format)
                            x_rows += 1
                            x_row_page += 1
                            worksheet.merge_range(x_rows, 0, x_rows, 3, self.company_id.name,
                                                  header_merge_format)  # Encabezado
                            x_rows += 1
                            x_row_page += 1
                            worksheet.merge_range(x_rows, 0, x_rows, 3, "NIT: " + self.company_id.partner_id.vat,
                                                  header_merge_format)  # Encabezado
                            x_rows += 1
                            x_row_page += 1
                            worksheet.merge_range(x_rows, 0, x_rows, 3, "Libro Diario",
                                                  header_merge_format)  # Encabezado
                            num_days = monthrange(self.anio, int(self.mes_a))[1]
                            x_rows += 1
                            x_row_page += 1
                            worksheet.merge_range(x_rows, 0, x_rows, 3, str("Del 01 de " + str(
                                dict(self._fields['mes_de'].selection).get(self.mes_de)) + " de " + str(
                                self.anio) + " Al " + str(
                                num_days) + " de " + str(
                                dict(self._fields['mes_a'].selection).get(self.mes_a)) + " de " + str(
                                self.anio)), header_merge_format)  # Encabezado
                            x_rows += 1
                            x_row_page += 1
                            worksheet.merge_range(x_rows, 0, x_rows, 3, "(EXPRESADO EN QUETZALES)",
                                                  header_merge_format)  # Encabezado
                            x_rows += 2
                            x_row_page += 2
                            worksheet.write(x_rows, 0, 'PDA', header_data_format)
                            worksheet.write(x_rows, 1, 'Cuenta', header_data_format)
                            worksheet.write(x_rows, 2, 'Debe', header_data_format)
                            worksheet.write(x_rows, 3, 'Haber', header_data_format)
                            # Fin encabezado 2
                            # Debemos iniciar nueva partida
                            x_rows += 1
                            x_row_page += 1
                            worksheet.write(x_rows, 0, str(linea.get('partida')), detail_description_format)
                            worksheet.write(x_rows, 1, str(linea.get('fecha').strftime("%d-%m-%Y")),
                                            detail_center_format)
                            worksheet.merge_range(x_rows, 2, x_rows, 3, '', detail_description_format)
                            # imprimir linea de partida
                            x_rows += 1
                            x_row_page += 1
                            worksheet.write(x_rows, 0, "", detail_description_format)
                            worksheet.write(x_rows, 1, str(linea.get('codigo')) + " " + str(linea.get('cuenta')),
                                            detail_description_format)
                            worksheet.write(x_rows, 2, float(linea.get('debe')), detail_monetary_format)
                            worksheet.write(x_rows, 3, float(linea.get('haber')), detail_monetary_format)
                            x_suma_debe += float(linea.get('debe'))
                            x_suma_haber += float(linea.get('haber'))
                        else: # No estamos en la ultima linea, No estamos en la misma partida, cerramos la anterior y apertramos la actual
                            # Cerramos partida
                            if x_last_partida !='vacio':
                                x_rows += 1
                                x_row_page += 1

                                worksheet.write(x_rows, 0, '', detail_description_format_dia)
                                worksheet.write(x_rows, 1, 'V/Movimientos del dia', header_data_format_dia)
                                worksheet.write(x_rows, 2, float(x_suma_debe), detail_monetary_format_bold_dia)
                                worksheet.write(x_rows, 3, float(x_suma_haber), detail_monetary_format_bold_dia)
                                detail_description_format.set_bottom(1)
                                header_data_format.set_bottom(1)
                                detail_monetary_format_bold.set_bottom(1)
                                x_suma_haber = 0  # reseteamos el van y vienen
                                x_suma_debe = 0  # reseteamos el van y vienen
                            # ultima linea
                            # Debemos iniciar nueva partida
                            if x_row_page == x_max_rows - 1:
                                # Van en 0
                                # Encabezado si
                                # Vienen en 0
                                # Nueva Partida si
                                # Primer detalle de partida si
                                # Encabezado 3

                                x_rows += 1
                                x_row_page = 0
                                worksheet.write(x_rows, 0, '', detail_description_format)
                                worksheet.write(x_rows, 1, 'VAN', header_data_format)
                                worksheet.write(x_rows, 2, float(x_suma_debe), detail_monetary_format_bold)
                                worksheet.write(x_rows, 3, float(x_suma_haber), detail_monetary_format_bold)

                                x_rows += 1
                                x_row_page += 1
                                x_page += 1
                                worksheet.write(x_rows, 3, "Folio: " + str(self.folio + x_page), right_format)
                                x_rows += 1
                                x_row_page += 1
                                worksheet.merge_range(x_rows, 0, x_rows, 3, self.company_id.name,
                                                      header_merge_format)  # Encabezado
                                x_rows += 1
                                x_row_page += 1
                                worksheet.merge_range(x_rows, 0, x_rows, 3, "NIT: " + self.company_id.partner_id.vat,
                                                      header_merge_format)  # Encabezado
                                x_rows += 1
                                x_row_page += 1
                                worksheet.merge_range(x_rows, 0, x_rows, 3, "Libro Diario",
                                                      header_merge_format)  # Encabezado
                                num_days = monthrange(self.anio, int(self.mes_a))[1]
                                x_rows += 1
                                x_row_page += 1
                                worksheet.merge_range(x_rows, 0, x_rows, 3, str("Del 01 de " + str(
                                    dict(self._fields['mes_de'].selection).get(self.mes_de)) + " de " + str(
                                    self.anio) + " Al " + str(
                                    num_days) + " de " + str(
                                    dict(self._fields['mes_a'].selection).get(self.mes_a)) + " de " + str(
                                    self.anio)), header_merge_format)  # Encabezado
                                x_rows += 1
                                x_row_page += 1
                                worksheet.merge_range(x_rows, 0, x_rows, 3, "(EXPRESADO EN QUETZALES)",
                                                      header_merge_format)  # Encabezado
                                x_rows += 2
                                x_row_page += 2
                                worksheet.write(x_rows, 0, 'PDA', header_data_format)
                                worksheet.write(x_rows, 1, 'Cuenta', header_data_format)
                                worksheet.write(x_rows, 2, 'Debe', header_data_format)
                                worksheet.write(x_rows, 3, 'Haber', header_data_format)
                                # Fin encabezado 2
                                # Vienen
                                x_rows += 1
                                x_row_page += 1
                                worksheet.write(x_rows, 0, '', detail_description_format)
                                worksheet.write(x_rows, 1, 'VIENEN', header_data_format)
                                worksheet.write(x_rows, 2, float(x_suma_debe), detail_monetary_format_bold)
                                worksheet.write(x_rows, 3, float(x_suma_haber), detail_monetary_format_bold)
                                # Debemos iniciar nueva partida
                                x_rows += 1
                                x_row_page += 1
                                worksheet.write(x_rows, 0, str(linea.get('partida')), detail_description_format)
                                worksheet.write(x_rows, 1, str(linea.get('fecha').strftime("%d-%m-%Y")),
                                                detail_center_format)
                                worksheet.merge_range(x_rows, 2, x_rows, 3, '', detail_description_format)
                                # imprimir linea de partida
                                x_rows += 1
                                x_row_page += 1
                                worksheet.write(x_rows, 0, "", detail_description_format)
                                worksheet.write(x_rows, 1,
                                                str(linea.get('codigo')) + " " + str(linea.get('cuenta')),
                                                detail_description_format)
                                worksheet.write(x_rows, 2, float(linea.get('debe')), detail_monetary_format)
                                worksheet.write(x_rows, 3, float(linea.get('haber')), detail_monetary_format)
                                x_suma_debe += float(linea.get('debe'))
                                x_suma_haber += float(linea.get('haber'))
                            else: # no estoy en ultima linea
                                x_rows += 1
                                x_row_page += 1
                                worksheet.write(x_rows, 0, str(linea.get('partida')), detail_description_format)
                                worksheet.write(x_rows, 1, str(linea.get('fecha').strftime("%d-%m-%Y")),
                                                detail_center_format)
                                worksheet.merge_range(x_rows, 2, x_rows, 3, '', detail_description_format)
                                # Ultima linea otra vez
                                if x_row_page == x_max_rows - 1:
                                    # Van
                                    # encabezado
                                    # Vienen
                                    # Detalle
                                    x_rows += 1
                                    x_row_page = 0
                                    worksheet.write(x_rows, 0, '', detail_description_format)
                                    worksheet.write(x_rows, 1, 'VAN', header_data_format)
                                    worksheet.write(x_rows, 2, float(x_suma_debe), detail_monetary_format_bold)
                                    worksheet.write(x_rows, 3, float(x_suma_haber), detail_monetary_format_bold)
                                    # Encabezado
                                    x_rows += 1
                                    x_row_page += 1
                                    x_page += 1
                                    worksheet.write(x_rows, 3, "Folio: " + str(self.folio + x_page), right_format)
                                    x_rows += 1
                                    x_row_page += 1
                                    worksheet.merge_range(x_rows, 0, x_rows, 3, self.company_id.name,
                                                          header_merge_format)  # Encabezado
                                    x_rows += 1
                                    x_row_page += 1
                                    worksheet.merge_range(x_rows, 0, x_rows, 3,
                                                          "NIT: " + self.company_id.partner_id.vat,
                                                          header_merge_format)  # Encabezado
                                    x_rows += 1
                                    x_row_page += 1
                                    worksheet.merge_range(x_rows, 0, x_rows, 3, "Libro Diario",
                                                          header_merge_format)  # Encabezado
                                    num_days = monthrange(self.anio, int(self.mes_a))[1]
                                    x_rows += 1
                                    x_row_page += 1
                                    worksheet.merge_range(x_rows, 0, x_rows, 3, str("Del 01 de " + str(
                                        dict(self._fields['mes_de'].selection).get(self.mes_de)) + " de " + str(
                                        self.anio) + " Al " + str(
                                        num_days) + " de " + str(
                                        dict(self._fields['mes_a'].selection).get(self.mes_a)) + " de " + str(
                                        self.anio)), header_merge_format)  # Encabezado
                                    x_rows += 1
                                    x_row_page += 1
                                    worksheet.merge_range(x_rows, 0, x_rows, 3, "(EXPRESADO EN QUETZALES)",
                                                          header_merge_format)  # Encabezado
                                    x_rows += 2
                                    x_row_page += 2
                                    worksheet.write(x_rows, 0, 'PDA', header_data_format)
                                    worksheet.write(x_rows, 1, 'Cuenta', header_data_format)
                                    worksheet.write(x_rows, 2, 'Debe', header_data_format)
                                    worksheet.write(x_rows, 3, 'Haber', header_data_format)
                                    # Fin encabezado 2
                                    # Vienen
                                    x_rows += 1
                                    x_row_page += 1
                                    worksheet.write(x_rows, 0, '', detail_description_format)
                                    worksheet.write(x_rows, 1, 'VIENEN', header_data_format)
                                    worksheet.write(x_rows, 2, float(x_suma_debe), detail_monetary_format_bold)
                                    worksheet.write(x_rows, 3, float(x_suma_haber), detail_monetary_format_bold)

                                    # Linea de partida
                                    x_rows += 1
                                    x_row_page += 1
                                    worksheet.write(x_rows, 0, "", detail_description_format)
                                    worksheet.write(x_rows, 1,
                                                    str(linea.get('codigo')) + " " + str(linea.get('cuenta')),
                                                    detail_description_format)
                                    worksheet.write(x_rows, 2, float(linea.get('debe')), detail_monetary_format)
                                    worksheet.write(x_rows, 3, float(linea.get('haber')), detail_monetary_format)
                                    x_suma_debe += float(linea.get('debe'))
                                    x_suma_haber += float(linea.get('haber'))

                                else:
                                    # imprimir linea de partida
                                    x_rows += 1
                                    x_row_page += 1
                                    worksheet.write(x_rows, 0, "", detail_description_format)
                                    worksheet.write(x_rows, 1,
                                                    str(linea.get('codigo')) + " " + str(linea.get('cuenta')),
                                                    detail_description_format)
                                    worksheet.write(x_rows, 2, float(linea.get('debe')), detail_monetary_format)
                                    worksheet.write(x_rows, 3, float(linea.get('haber')), detail_monetary_format)
                                    x_suma_debe += float(linea.get('debe'))
                                    x_suma_haber += float(linea.get('haber'))
                    x_last_partida = linea.get('partida')
                    if x_total_row_count == x_iteracion:
                        x_rows += 1
                        x_row_page += 1
                        worksheet.write(x_rows, 0, '', detail_description_format_dia)
                        worksheet.write(x_rows, 1, 'V/Movimientos del dia', header_data_format_dia)
                        worksheet.write(x_rows, 2, float(x_suma_debe), detail_monetary_format_bold_dia)
                        worksheet.write(x_rows, 3, float(x_suma_haber), detail_monetary_format_bold_dia)
                        detail_description_format.set_bottom(1)
                        header_data_format.set_bottom(1)
                        detail_monetary_format_bold.set_bottom(1)
                        x_suma_haber = 0  # reseteamos el van y vienen
                        x_suma_debe = 0  # reseteamos el van y vienen
                else:
                    x_rows += 1
                    x_page += 1
                    x_row_page = 0

        #agregar el nombre de las columnas posiblemente
        else:
            worksheet.write(x_rows, 3, "Folio: " + str(self.folio + x_page), right_format)
            x_rows += 1
            x_row_page += 1
            worksheet.merge_range(x_rows, 0, x_rows, 3, self.company_id.name,
                                  header_merge_format)  # Encabezado
            x_rows += 1
            x_row_page += 1
            worksheet.merge_range(x_rows, 0, x_rows, 3, "NIT: " + self.company_id.partner_id.vat,
                                  header_merge_format)  # Encabezado
            x_rows += 1
            x_row_page += 1
            worksheet.merge_range(x_rows, 0, x_rows, 3, "Libro Diario", header_merge_format)  # Encabezado
            num_days = monthrange(self.anio, int(self.mes_a))[1]
            x_rows += 1
            x_row_page += 1
            worksheet.merge_range(x_rows, 0, x_rows, 3, str("Del 01 de " + str(
                dict(self._fields['mes_de'].selection).get(self.mes_de)) + " de " + str(
                self.anio) + " Al " + str(
                num_days) + " de " + str(
                dict(self._fields['mes_a'].selection).get(self.mes_a)) + " de " + str(
                self.anio)), header_merge_format)  # Encabezado
            x_rows += 1
            x_row_page += 1
            worksheet.merge_range(x_rows, 0, x_rows, 3, "(EXPRESADO EN QUETZALES)",
                                  header_merge_format)  # Encabezado
            x_rows += 2
            x_row_page += 2

            worksheet.write(x_rows, 0, 'PDA', header_data_format)
            worksheet.write(x_rows, 1, 'Cuenta', header_data_format)
            worksheet.write(x_rows, 2, 'Debe', header_data_format)
            worksheet.write(x_rows, 3, 'Haber', header_data_format)
            x_row_page += 1
        workbook.close()
        self.write({
            'state': 'get',
            'data': base64.b64encode(open(xls_path, 'rb').read()),
            'name': xls_filename
        })
        return {
            'name': 'Report Financial',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new'
        }

class wizard_report_mayor_financial(models.TransientModel):
    _name = 'wizard.report.mayor.financial'
    _description = "Wizard Report Mayor Financial"
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id)
    anio = fields.Integer(string="Año")
    mes_de = fields.Selection([('1','Enero'),('2','Febrero'),('3','Marzo'),('4','Abril'),('5','Mayo'),('6','Junio'),('7','Julio'),('8','Agosto'),('9','Septiembre'),('10','Octubre'),('11','Noviembre'),('12','Diciembre')],string="De")
    mes_a = fields.Selection(
        [('1', 'Enero'), ('2', 'Febrero'), ('3', 'Marzo'), ('4', 'Abril'), ('5', 'Mayo'), ('6', 'Junio'),
         ('7', 'Julio'), ('8', 'Agosto'), ('9', 'Septiembre'), ('10', 'Octubre'), ('11', 'Noviembre'),
         ('12', 'Diciembre')], string="A")
    folio = fields.Integer(string="Folio")
    state = fields.Selection([('choose', 'choose'), ('get', 'get')], default='choose')
    name = fields.Char(string='File Name', readonly=True)
    data = fields.Binary(string='File', readonly=True)

    def check_mes(self):
        if int(self.mes_de) > int(self.mes_a):
            raise ValidationError(_('-Mes De- debe ser anterior a -Mes A-.'))

    def go_back_mayor(self):
        self.state = 'choose'
        return {
            'name': 'Report Financial MAyor',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new'
        }

    def print_xls_report_financial_mayor(self):
        self.check_mes()
        #company_id = self.env['res.company'].browse(self._context.get('allowed_company_ids'))
        xls_filename = 'Libro Mayor.xlsx'
        temp_dir = tempfile.gettempdir()
        xls_path = os.path.join(temp_dir, xls_filename)
        workbook = xlsxwriter.Workbook(xls_path)
        report_in_sql = self.env['report.account_report_financial.report_financial']
        back_gray_bold = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                                     'font_size': 10, 'bg_color': '#D3D3D3'})
        back_gray_bold_monetary = workbook.add_format({'bold': True, 'align': 'right', 'font': 'Arial', 'font_size': 10, 'bg_color': '#D3D3D3','num_format': 'Q#,##0.00'})
        border_back_gray_head_left = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                                   'font_size': 10, 'bg_color': '#D3D3D3'})
        border_back_gray_head_left.set_bottom(1)
        border_back_gray_head_left.set_top(1)
        border_back_gray_head_left.set_left(1)

        border_back_gray_head_center = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                                     'font_size': 10, 'bg_color': '#D3D3D3'})
        border_back_gray_head_center.set_bottom(1)
        border_back_gray_head_center.set_top(1)

        border_back_gray_head_right = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                                     'font_size': 10, 'bg_color': '#D3D3D3'})
        border_back_gray_head_right.set_bottom(1)
        border_back_gray_head_right.set_top(1)
        border_back_gray_head_right.set_right(1)


        header_merge_format = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                                   'font': 'Arial','font_size': 10})
        right_format = workbook.add_format({'bold': False, 'align': 'right', \
                                                   'font': 'Arial', 'font_size': 10})

        header_data_format = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                                  'font': 'Arial','font_size': 10, 'border': 1})
        header_data_format_dia = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                                  'font': 'Arial', 'font_size': 10})

        detail_monetary_format = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10,'num_format': 'Q#,##0.00'})
        detail_monetary_format_center = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10,'num_format': 'Q#,##0.00'})
        detail_monetary_format_center.set_right(6)
        detail_monetary_format_bold = workbook.add_format({'bold' : True, 'align': 'right', 'font': 'Arial', 'font_size': 10, 'border': 1})
        detail_monetary_format_bold_dia = workbook.add_format(
            {'bold': True, 'align': 'right', 'font': 'Arial', 'font_size': 10, 'num_format': 'Q#,##0.00'})
        detail_monetary_format_bold_dia_right = workbook.add_format(
            {'bold': True, 'align': 'right', 'font': 'Arial', 'font_size': 10, 'num_format': 'Q#,##0.00'})
        detail_monetary_format_bold_dia_right.set_right(6)
        detail_monetary_format_bold_dia_right.set_top(1)
        detail_monetary_format_bold_dia_right.set_bottom(6)
        detail_center_format = workbook.add_format({'align': 'center', 'font': 'Arial', 'font_size': 10, 'border': 1})

        detail_date_format = workbook.add_format({'align': 'center', 'font': 'Arial', 'font_size': 10, 'num_format': 'dd-mm-yyyy'})
        detail_no_border = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 10})
        detail_description_format_dia = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 10, 'border': 1})

        detail_description_format_dia.set_bottom(6)
        header_data_format_dia.set_bottom(6)
        detail_monetary_format_bold_dia.set_bottom(6)
        # Por cada bodega

        # --------------------------------------------------------------------------------------------------------------
        # -------------------------------------------------QUERY--------------------------------------------------------
        consulta = report_in_sql.get_libro_mayor(self)
        # -------------------------------------------------QUERY--------------------------------------------------------
        worksheet = workbook.add_worksheet("Libro Mayor")
        worksheet.set_landscape()
        worksheet.set_page_view()
        worksheet.set_paper(1)
        worksheet.set_margins(0.7,0.7,0.7,0.7)
        # Tamaños
        worksheet.set_column('A:A', 12)
        worksheet.set_column('B:B', 15)
        worksheet.set_column('C:C', 15)
        worksheet.set_column('D:D', 15)

        worksheet.set_column('E:E', 12)
        worksheet.set_column('F:F', 15)
        worksheet.set_column('G:G', 15)
        worksheet.set_column('H:H', 15)
        # Empieza detalle
        x_rows = 0 # Linea a imprimir
        x_page = 0 # Numero de pagina
        x_max_rows = 35 # Maximo de lineas por pagina
        x_row_page = 0 # Linea actual vrs maximo de lineas
        x_last_codigo_cuenta = 'vacio'
        x_suma_debe = 0
        x_suma_debe_saldo = 0
        x_suma_haber = 0
        x_suma_haber_saldo = 0
        x_iteracion = 0
        if consulta:
            x_total_row_count = len(consulta)
            #for aml in account_move_line:
            for linea in consulta: # resultado query
                x_iteracion += 1
                if x_row_page < x_max_rows:  # Estamos en ciclo
                    # ---------------------------- Encabezado ----------------------------------------------------------
                    if x_row_page == 0:  # Nueva pagina
                        worksheet.write(x_rows, 7, "Folio: " + str(self.folio + x_page), right_format)
                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 7, self.company_id.name,
                                              header_merge_format)  # Encabezado
                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 7, "NIT: " + self.company_id.partner_id.vat,
                                              header_merge_format)  # Encabezado
                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 7, "Libro Mayor", header_merge_format)  # Encabezado
                        num_days = monthrange(self.anio, int(self.mes_a))[1]
                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 7, str("Del 01 de " + str(
                            dict(self._fields['mes_de'].selection).get(self.mes_de)) + " de " + str(
                            self.anio) + " Al " + str(
                            num_days) + " de " + str(
                            dict(self._fields['mes_a'].selection).get(self.mes_a)) + " de " + str(
                            self.anio)), header_merge_format)  # Encabezado
                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 7, "(EXPRESADO EN QUETZALES)",
                                              header_merge_format)  # Encabezado
                        #x_rows += 1
                        x_row_page += 1

                    # ---------------------------- Fin Encabezado ----------------------------------------------------------
                    if x_last_codigo_cuenta == str(linea.get('codigodebe')+' '+linea.get('cuentadebe')):  # estamos en la misma cuenta
                        if x_row_page == x_max_rows - 1:  # Estamos en la penultima linea
                            x_rows += 1
                            x_row_page = 0
                            worksheet.merge_range(x_rows, 0, x_rows, 1, "VAN", back_gray_bold)
                            worksheet.write(x_rows, 2, float(x_suma_debe), back_gray_bold_monetary)
                            worksheet.write(x_rows, 3, float(x_suma_debe_saldo), back_gray_bold_monetary)
                            worksheet.write(x_rows, 4, "", back_gray_bold_monetary)
                            worksheet.write(x_rows, 5, "", back_gray_bold_monetary)
                            worksheet.write(x_rows, 6, float(x_suma_haber), back_gray_bold_monetary)
                            worksheet.write(x_rows, 7, float(x_suma_haber_saldo), back_gray_bold_monetary)

                            # Encabezado 1
                            x_rows += 1
                            x_row_page += 1
                            x_page += 1
                            worksheet.write(x_rows, 7, "Folio: " + str(self.folio + x_page), right_format)
                            x_rows += 1
                            x_row_page += 1
                            worksheet.merge_range(x_rows, 0, x_rows, 7, self.company_id.name,
                                                  header_merge_format)  # Encabezado
                            x_rows += 1
                            x_row_page += 1
                            worksheet.merge_range(x_rows, 0, x_rows, 7, "NIT: " + self.company_id.partner_id.vat,
                                                  header_merge_format)  # Encabezado
                            x_rows += 1
                            x_row_page += 1
                            worksheet.merge_range(x_rows, 0, x_rows, 7, "Libro Mayor",
                                                  header_merge_format)  # Encabezado
                            num_days = monthrange(self.anio, int(self.mes_a))[1]
                            x_rows += 1
                            x_row_page += 1
                            worksheet.merge_range(x_rows, 0, x_rows, 7, str("Del 01 de " + str(
                                dict(self._fields['mes_de'].selection).get(self.mes_de)) + " de " + str(
                                self.anio) + " Al " + str(
                                num_days) + " de " + str(
                                dict(self._fields['mes_a'].selection).get(self.mes_a)) + " de " + str(
                                self.anio)), header_merge_format)  # Encabezado
                            x_rows += 1
                            x_row_page += 1
                            worksheet.merge_range(x_rows, 0, x_rows, 7, "(EXPRESADO EN QUETZALES)",
                                                  header_merge_format)  # Encabezado
                            x_rows += 1
                            x_row_page += 1
                            worksheet.merge_range(x_rows, 0, x_rows, 1, "DEBE", border_back_gray_head_left)
                            worksheet.merge_range(x_rows, 2, x_rows, 5, str(linea.get('codigodebe') + ' ' + linea.get('cuentadebe')), border_back_gray_head_center)
                            worksheet.merge_range(x_rows, 6, x_rows, 7, "HABER", border_back_gray_head_right)

                            x_rows += 1
                            x_row_page += 1
                            worksheet.merge_range(x_rows, 0, x_rows, 1, "VIENEN", back_gray_bold)
                            worksheet.write(x_rows, 2, float(x_suma_debe), back_gray_bold_monetary)
                            worksheet.write(x_rows, 3, float(x_suma_debe_saldo), back_gray_bold_monetary)
                            worksheet.write(x_rows, 4, "", back_gray_bold_monetary)
                            worksheet.write(x_rows, 5, "", back_gray_bold_monetary)
                            worksheet.write(x_rows, 6, float(x_suma_haber), back_gray_bold_monetary)
                            worksheet.write(x_rows, 7, float(x_suma_haber_saldo), back_gray_bold_monetary)

                            x_rows += 1
                            x_row_page += 1
                            x_suma_debe += float(linea.get('debe'))
                            x_suma_debe_saldo += float(linea.get('debe'))
                            x_suma_haber += float(linea.get('haber'))
                            x_suma_haber_saldo += float(linea.get('haber'))
                            worksheet.write(x_rows, 0, str(linea.get('partidadebe')), detail_no_border)
                            worksheet.write(x_rows, 1, str(linea.get('fechadebe')), detail_date_format)
                            worksheet.write(x_rows, 2, float(linea.get('debe')), detail_monetary_format)
                            worksheet.write(x_rows, 3, x_suma_debe_saldo, detail_monetary_format_center)
                            worksheet.write(x_rows, 4, str(linea.get('partidahaber')), detail_no_border)
                            worksheet.write(x_rows, 5, str(linea.get('fechahaber')), detail_date_format)
                            worksheet.write(x_rows, 6, float(linea.get('haber')), detail_monetary_format)
                            worksheet.write(x_rows, 7, x_suma_haber_saldo, detail_monetary_format)


                        else: # No estamos en la ultima linea, estamos en la misma cuenta
                            x_rows += 1
                            x_row_page += 1
                            x_suma_debe += float(linea.get('debe'))
                            x_suma_debe_saldo += float(linea.get('debe'))
                            x_suma_haber += float(linea.get('haber'))
                            x_suma_haber_saldo += float(linea.get('haber'))
                            worksheet.write(x_rows, 0, str(linea.get('partidadebe')), detail_no_border)
                            worksheet.write(x_rows, 1, str(linea.get('fechadebe')), detail_date_format)
                            worksheet.write(x_rows, 2, float(linea.get('debe')), detail_monetary_format)
                            worksheet.write(x_rows, 3, x_suma_debe_saldo, detail_monetary_format_center)
                            worksheet.write(x_rows, 4, str(linea.get('partidahaber')), detail_no_border)
                            worksheet.write(x_rows, 5, str(linea.get('fechahaber')), detail_date_format)
                            worksheet.write(x_rows, 6, float(linea.get('haber')), detail_monetary_format)
                            worksheet.write(x_rows, 7, x_suma_haber_saldo, detail_monetary_format)

                    else: # no estamos en la misma cuenta
                        if x_row_page == x_max_rows - 1:  # Estamos en la penultima linea
                            x_rows += 1
                            x_row_page = 0
                            header_data_format_dia.set_top(1)
                            detail_monetary_format_bold_dia.set_top(1)
                            worksheet.merge_range(x_rows, 0, x_rows, 1, "TOTALES", header_data_format_dia)
                            worksheet.write(x_rows, 2, float(x_suma_debe), detail_monetary_format_bold_dia)
                            worksheet.write(x_rows, 3, float(x_suma_debe_saldo), detail_monetary_format_bold_dia_right)
                            worksheet.merge_range(x_rows, 4, x_rows, 5, "TOTALES", header_data_format_dia)
                            worksheet.write(x_rows, 6, float(x_suma_haber), detail_monetary_format_bold_dia)
                            worksheet.write(x_rows, 7, float(x_suma_haber_saldo), detail_monetary_format_bold_dia)

                            x_suma_debe = 0  # reseteamos el van y vienen
                            x_suma_haber_saldo = 0 # float(linea.get('saldohaber'))
                            x_suma_haber = 0 # reseteamos el van y vienen
                            x_suma_debe_saldo = 0 # float(linea.get('saldodebe'))

                            # imprimir encabezado porque cambia de cuenta y hay que imprimirlo en nueva pagina
                            # Encabezado 2
                            x_rows += 1
                            x_row_page += 1
                            x_page += 1
                            worksheet.write(x_rows, 7, "Folio: " + str(self.folio + x_page), right_format)
                            x_rows += 1
                            x_row_page += 1
                            worksheet.merge_range(x_rows, 0, x_rows, 7, self.company_id.name,
                                                  header_merge_format)  # Encabezado
                            x_rows += 1
                            x_row_page += 1
                            worksheet.merge_range(x_rows, 0, x_rows, 7, "NIT: " + self.company_id.partner_id.vat,
                                                  header_merge_format)  # Encabezado
                            x_rows += 1
                            x_row_page += 1
                            worksheet.merge_range(x_rows, 0, x_rows, 7, "Libro Mayor",
                                                  header_merge_format)  # Encabezado
                            num_days = monthrange(self.anio, int(self.mes_a))[1]
                            x_rows += 1
                            x_row_page += 1
                            worksheet.merge_range(x_rows, 0, x_rows, 7, str("Del 01 de " + str(
                                dict(self._fields['mes_de'].selection).get(self.mes_de)) + " de " + str(
                                self.anio) + " Al " + str(
                                num_days) + " de " + str(
                                dict(self._fields['mes_a'].selection).get(self.mes_a)) + " de " + str(
                                self.anio)), header_merge_format)  # Encabezado
                            x_rows += 1
                            x_row_page += 1
                            worksheet.merge_range(x_rows, 0, x_rows, 7, "(EXPRESADO EN QUETZALES)",
                                                  header_merge_format)  # Encabezado
                            x_rows += 1
                            x_row_page += 1
                            worksheet.merge_range(x_rows, 0, x_rows, 1, "DEBE", border_back_gray_head_left)
                            worksheet.merge_range(x_rows, 2, x_rows, 5,
                                                  str(linea.get('codigodebe') + ' ' + linea.get('cuentadebe')),
                                                  border_back_gray_head_center)
                            worksheet.merge_range(x_rows, 6, x_rows, 7, "HABER", border_back_gray_head_right)

                            x_rows += 1
                            x_row_page += 1
                            worksheet.merge_range(x_rows, 0, x_rows, 1, "Saldo inicial", detail_no_border)
                            worksheet.write(x_rows, 3, float(linea.get('saldodebe')), detail_monetary_format_center)
                            worksheet.write(x_rows, 7, float(linea.get('saldohaber')), detail_monetary_format)

                            # Fin encabezado 2
                            # Debemos iniciar nueva partida
                            # Aqui lo dejamos previo a que muestre la informacion
                            x_suma_debe = 0
                            x_suma_debe_saldo = 0
                            x_suma_haber = 0
                            x_suma_haber_saldo = 0

                            x_suma_debe += float(linea.get('debe'))
                            x_suma_debe_saldo += (float(linea.get('debe'))+float(linea.get('saldodebe')))
                            x_suma_haber += float(linea.get('haber'))
                            x_suma_haber_saldo += (float(linea.get('haber')) + float(linea.get('saldohaber')))

                            x_rows += 1
                            x_row_page += 1
                            worksheet.write(x_rows, 0, str(linea.get('partidadebe')), detail_no_border)
                            worksheet.write(x_rows, 1, str(linea.get('fechadebe')), detail_date_format)
                            worksheet.write(x_rows, 2, float(linea.get('debe')), detail_monetary_format)
                            worksheet.write(x_rows, 3, x_suma_debe_saldo, detail_monetary_format_center)
                            worksheet.write(x_rows, 4, str(linea.get('partidahaber')), detail_no_border)
                            worksheet.write(x_rows, 5, str(linea.get('fechahaber')), detail_date_format)
                            worksheet.write(x_rows, 6, float(linea.get('haber')), detail_monetary_format)
                            worksheet.write(x_rows, 7, x_suma_haber_saldo, detail_monetary_format)


                        else: # No estamos en la ultima linea, No estamos en la misma partida, cerramos la anterior y aperturamos la actual
                            # Cerramos partida
                            if x_last_codigo_cuenta !='vacio':
                                x_rows += 1
                                x_row_page += 1

                                header_data_format_dia.set_top(1)
                                detail_monetary_format_bold_dia.set_top(1)
                                worksheet.merge_range(x_rows, 0, x_rows, 1, "TOTALES", header_data_format_dia)
                                worksheet.write(x_rows, 2, float(x_suma_debe), detail_monetary_format_bold_dia)
                                worksheet.write(x_rows, 3, float(x_suma_debe_saldo), detail_monetary_format_bold_dia_right)
                                worksheet.merge_range(x_rows, 4, x_rows, 5, "TOTALES", header_data_format_dia)
                                worksheet.write(x_rows, 6, float(x_suma_haber), detail_monetary_format_bold_dia)
                                worksheet.write(x_rows, 7, float(x_suma_haber_saldo), detail_monetary_format_bold_dia)

                                x_suma_debe = 0  # reseteamos el van y vienen
                                x_suma_haber_saldo = 0  # reseteamos el van y vienen
                                x_suma_haber = 0 # float(linea.get('saldohaber'))
                                x_suma_debe_saldo = 0 # float(linea.get('saldodebe'))

                            # ultima linea
                            # Debemos iniciar nueva partida
                            if x_row_page == x_max_rows - 1:
                                # Van en 0
                                # Encabezado si
                                # Vienen en 0
                                # Nueva Partida si
                                # Primer detalle de partida si
                                # Encabezado 3

                                x_rows += 1
                                x_row_page = 0
                                worksheet.merge_range(x_rows, 0, x_rows, 1, "VAN", back_gray_bold)
                                worksheet.write(x_rows, 2, float(x_suma_debe), back_gray_bold_monetary)
                                worksheet.write(x_rows, 3, float(x_suma_debe_saldo), back_gray_bold_monetary)
                                worksheet.write(x_rows, 4, "", back_gray_bold_monetary)
                                worksheet.write(x_rows, 5, "", back_gray_bold_monetary)
                                worksheet.write(x_rows, 6, float(x_suma_haber), back_gray_bold_monetary)
                                worksheet.write(x_rows, 7, float(x_suma_haber_saldo), back_gray_bold_monetary)

                                x_rows += 1
                                x_row_page += 1
                                x_page += 1
                                worksheet.write(x_rows, 7, "Folio: " + str(self.folio + x_page), right_format)
                                x_rows += 1
                                x_row_page += 1
                                worksheet.merge_range(x_rows, 0, x_rows, 7, self.company_id.name,
                                                      header_merge_format)  # Encabezado
                                x_rows += 1
                                x_row_page += 1
                                worksheet.merge_range(x_rows, 0, x_rows, 7, "NIT: " + self.company_id.partner_id.vat,
                                                      header_merge_format)  # Encabezado
                                x_rows += 1
                                x_row_page += 1
                                worksheet.merge_range(x_rows, 0, x_rows, 7, "Libro Mayor",
                                                      header_merge_format)  # Encabezado
                                num_days = monthrange(self.anio, int(self.mes_a))[1]
                                x_rows += 1
                                x_row_page += 1
                                worksheet.merge_range(x_rows, 0, x_rows, 7, str("Del 01 de " + str(
                                    dict(self._fields['mes_de'].selection).get(self.mes_de)) + " de " + str(
                                    self.anio) + " Al " + str(
                                    num_days) + " de " + str(
                                    dict(self._fields['mes_a'].selection).get(self.mes_a)) + " de " + str(
                                    self.anio)), header_merge_format)  # Encabezado
                                x_rows += 1
                                x_row_page += 1
                                worksheet.merge_range(x_rows, 0, x_rows, 7, "(EXPRESADO EN QUETZALES)",
                                                      header_merge_format)  # Encabezado
                                x_rows += 1
                                x_row_page += 1
                                worksheet.merge_range(x_rows, 0, x_rows, 1, "DEBE", border_back_gray_head_left)
                                worksheet.merge_range(x_rows, 2, x_rows, 5, str(linea.get('codigodebe') + ' ' + linea.get('cuentadebe')),border_back_gray_head_center)
                                worksheet.merge_range(x_rows, 6, x_rows, 7, "HABER", border_back_gray_head_right)

                                x_rows += 1
                                x_row_page += 1

                                worksheet.merge_range(x_rows, 0, x_rows, 1, "VIENEN", back_gray_bold)
                                worksheet.write(x_rows, 2, float(x_suma_debe), back_gray_bold_monetary)
                                worksheet.write(x_rows, 3, float(x_suma_debe_saldo), back_gray_bold_monetary)
                                worksheet.write(x_rows, 4, "", back_gray_bold_monetary)
                                worksheet.write(x_rows, 5, "", back_gray_bold_monetary)
                                worksheet.write(x_rows, 6, float(x_suma_haber), back_gray_bold_monetary)
                                worksheet.write(x_rows, 7, float(x_suma_haber_saldo), back_gray_bold_monetary)

                                x_rows += 1
                                x_row_page += 1
                                worksheet.merge_range(x_rows, 0, x_rows, 1, "Saldo inicial", detail_no_border)
                                worksheet.write(x_rows, 3, float(linea.get('saldodebe')), detail_monetary_format_center)
                                worksheet.write(x_rows, 7, float(linea.get('saldohaber')), detail_monetary_format)

                                # Fin encabezado 2
                                # Debemos iniciar nueva partida
                                # Aqui lo dejamos previo a que muestre la informacion
                                x_suma_debe = 0
                                x_suma_debe_saldo = 0
                                x_suma_haber = 0
                                x_suma_haber_saldo = 0

                                x_suma_debe += float(linea.get('debe'))
                                x_suma_debe_saldo += (float(linea.get('debe')) + float(linea.get('saldodebe')))
                                x_suma_haber += float(linea.get('haber'))
                                x_suma_haber_saldo += (float(linea.get('haber')) + float(linea.get('saldohaber')))

                                x_rows += 1
                                x_row_page += 1
                                #x_suma_debe += float(linea.get('debe'))
                                #x_suma_debe_saldo += float(linea.get('debe'))
                                #x_suma_haber += float(linea.get('haber'))
                                #x_suma_haber_saldo += float(linea.get('haber'))

                                worksheet.write(x_rows, 0, str(linea.get('partidadebe')), detail_no_border)
                                worksheet.write(x_rows, 1, str(linea.get('fechadebe')), detail_date_format)
                                worksheet.write(x_rows, 2, float(linea.get('debe')), detail_monetary_format)
                                worksheet.write(x_rows, 3, x_suma_debe_saldo, detail_monetary_format_center)
                                worksheet.write(x_rows, 4, str(linea.get('partidahaber')), detail_no_border)
                                worksheet.write(x_rows, 5, str(linea.get('fechahaber')), detail_date_format)
                                worksheet.write(x_rows, 6, float(linea.get('haber')), detail_monetary_format)
                                worksheet.write(x_rows, 7, x_suma_haber_saldo, detail_monetary_format)


                            else: # no estoy en ultima linea iniciando nueva cuenta
                                x_rows += 1
                                x_row_page += 1
                                worksheet.merge_range(x_rows, 0, x_rows, 1, "DEBE", border_back_gray_head_left)
                                worksheet.merge_range(x_rows, 2, x_rows, 5, str(linea.get('codigodebe') + ' ' + linea.get('cuentadebe')), border_back_gray_head_center)
                                worksheet.merge_range(x_rows, 6, x_rows, 7, "HABER", border_back_gray_head_right)
                                if x_row_page == x_max_rows - 1: # Ultima linea otra vez
                                    # Van
                                    # encabezado
                                    # Vienen
                                    # Detalle
                                    x_rows += 1
                                    x_row_page = 0
                                    worksheet.merge_range(x_rows, 0, x_rows, 1, "VAN", back_gray_bold)
                                    worksheet.write(x_rows, 2, float(x_suma_debe), back_gray_bold_monetary)
                                    worksheet.write(x_rows, 3, float(x_suma_debe_saldo), back_gray_bold_monetary)
                                    worksheet.write(x_rows, 4, "", back_gray_bold_monetary)
                                    worksheet.write(x_rows, 5, "", back_gray_bold_monetary)
                                    worksheet.write(x_rows, 6, float(x_suma_haber), back_gray_bold_monetary)
                                    worksheet.write(x_rows, 7, float(x_suma_haber_saldo), back_gray_bold_monetary)
                                    # Encabezado
                                    x_rows += 1
                                    x_row_page += 1
                                    x_page += 1
                                    worksheet.write(x_rows, 7, "Folio: " + str(self.folio + x_page), right_format)
                                    x_rows += 1
                                    x_row_page += 1
                                    worksheet.merge_range(x_rows, 0, x_rows, 7, self.company_id.name,
                                                          header_merge_format)  # Encabezado
                                    x_rows += 1
                                    x_row_page += 1
                                    worksheet.merge_range(x_rows, 0, x_rows, 7,
                                                          "NIT: " + self.company_id.partner_id.vat,
                                                          header_merge_format)  # Encabezado
                                    x_rows += 1
                                    x_row_page += 1
                                    worksheet.merge_range(x_rows, 0, x_rows, 7, "Libro Mayor",
                                                          header_merge_format)  # Encabezado
                                    num_days = monthrange(self.anio, int(self.mes_a))[1]
                                    x_rows += 1
                                    x_row_page += 1
                                    worksheet.merge_range(x_rows, 0, x_rows, 7, str("Del 01 de " + str(
                                        dict(self._fields['mes_de'].selection).get(self.mes_de)) + " de " + str(
                                        self.anio) + " Al " + str(
                                        num_days) + " de " + str(
                                        dict(self._fields['mes_a'].selection).get(self.mes_a)) + " de " + str(
                                        self.anio)), header_merge_format)  # Encabezado
                                    x_rows += 1
                                    x_row_page += 1
                                    worksheet.merge_range(x_rows, 0, x_rows, 7, "(EXPRESADO EN QUETZALES)",
                                                          header_merge_format)  # Encabezado
                                    x_rows += 1
                                    x_row_page += 1
                                    worksheet.merge_range(x_rows, 0, x_rows, 1, "DEBE", border_back_gray_head_left)
                                    worksheet.merge_range(x_rows, 2, x_rows, 5,
                                                          str(linea.get('codigodebe') + ' ' + linea.get('cuentadebe')),
                                                          border_back_gray_head_center)
                                    worksheet.merge_range(x_rows, 6, x_rows, 7, "HABER", border_back_gray_head_right)
                                    # Fin encabezado 2
                                    # Vienen
                                    x_rows += 1
                                    x_row_page += 1
                                    worksheet.merge_range(x_rows, 0, x_rows, 1, "VIENEN", back_gray_bold)
                                    worksheet.write(x_rows, 2, float(x_suma_debe), back_gray_bold_monetary)
                                    worksheet.write(x_rows, 3, float(x_suma_debe_saldo), back_gray_bold_monetary)
                                    worksheet.write(x_rows, 4, "", back_gray_bold_monetary)
                                    worksheet.write(x_rows, 5, "", back_gray_bold_monetary)
                                    worksheet.write(x_rows, 6, float(x_suma_haber), back_gray_bold_monetary)
                                    worksheet.write(x_rows, 7, float(x_suma_haber_saldo), back_gray_bold_monetary)

                                    # Linea de partida
                                    # x_rows += 1
                                    # x_row_page += 1
                                    # x_suma_debe += float(linea.get('debe'))
                                    # x_suma_debe_saldo += float(linea.get('debe'))
                                    # x_suma_haber += float(linea.get('haber'))
                                    # x_suma_haber_saldo += float(linea.get('haber'))

                                    x_rows += 1
                                    x_row_page += 1
                                    worksheet.merge_range(x_rows, 0, x_rows, 1, "Saldo inicial",detail_no_border)
                                    worksheet.write(x_rows, 3, float(linea.get('saldodebe')), detail_monetary_format)
                                    worksheet.write(x_rows, 7, float(linea.get('saldohaber')), detail_monetary_format)

                                    # Fin encabezado 2
                                    # Debemos iniciar nueva partida
                                    # Aqui lo dejamos previo a que muestre la informacion
                                    x_suma_debe = 0
                                    x_suma_debe_saldo = 0
                                    x_suma_haber = 0
                                    x_suma_haber_saldo = 0

                                    x_suma_debe += float(linea.get('debe'))
                                    x_suma_debe_saldo += (float(linea.get('debe')) + float(linea.get('saldodebe')))
                                    x_suma_haber += float(linea.get('haber'))
                                    x_suma_haber_saldo += (float(linea.get('haber')) + float(linea.get('saldohaber')))
                                    x_rows += 1
                                    x_row_page += 1
                                    worksheet.write(x_rows, 0, str(linea.get('partidadebe')), detail_no_border)
                                    worksheet.write(x_rows, 1, str(linea.get('fechadebe')), detail_date_format)
                                    worksheet.write(x_rows, 2, float(linea.get('debe')), detail_monetary_format)
                                    worksheet.write(x_rows, 3, x_suma_debe_saldo, detail_monetary_format_center)
                                    worksheet.write(x_rows, 4, str(linea.get('partidahaber')), detail_no_border)
                                    worksheet.write(x_rows, 5, str(linea.get('fechahaber')), detail_date_format)
                                    worksheet.write(x_rows, 6, float(linea.get('haber')), detail_monetary_format)
                                    worksheet.write(x_rows, 7, x_suma_haber_saldo, detail_monetary_format)
                                    # x_suma_debe += float(linea.get('debe'))
                                    # x_suma_debe_saldo += float(linea.get('debe'))
                                    # x_suma_haber += float(linea.get('haber'))
                                    # x_suma_haber_saldo += float(linea.get('haber'))
                                    # --------------------------------------------------------------------------------------------------------------- Aqui voy ---------------------------------------------------------------------------------------------------------------

                                else:
                                    # imprimimos saldo y volvemos a corroborar ultima linea
                                    # imprimir linea de partida
                                    x_rows += 1
                                    x_row_page += 1
                                    worksheet.merge_range(x_rows, 0, x_rows, 1, "Saldo inicial", detail_no_border)
                                    worksheet.write(x_rows, 3, float(linea.get('saldodebe')), detail_monetary_format_center)
                                    worksheet.write(x_rows, 7, float(linea.get('saldohaber')), detail_monetary_format)

                                    # Fin encabezado 2
                                    # Debemos iniciar nueva partida
                                    # Aqui lo dejamos previo a que muestre la informacion
                                    x_suma_debe = 0
                                    x_suma_debe_saldo = 0
                                    x_suma_haber = 0
                                    x_suma_haber_saldo = 0

                                    if x_row_page == x_max_rows - 1:  # Ultima linea otra vez
                                        # Van
                                        # encabezado
                                        # Vienen
                                        # Detalle
                                        x_suma_debe_saldo += float(linea.get('saldodebe'))
                                        x_suma_haber_saldo += float(linea.get('saldohaber'))
                                        x_rows += 1
                                        x_row_page = 0
                                        worksheet.merge_range(x_rows, 0, x_rows, 1, "VAN", back_gray_bold)
                                        worksheet.write(x_rows, 2, float(x_suma_debe), back_gray_bold_monetary)
                                        worksheet.write(x_rows, 3, float(x_suma_debe_saldo), back_gray_bold_monetary)
                                        worksheet.write(x_rows, 4, "", back_gray_bold_monetary)
                                        worksheet.write(x_rows, 5, "", back_gray_bold_monetary)
                                        worksheet.write(x_rows, 6, float(x_suma_haber), back_gray_bold_monetary)
                                        worksheet.write(x_rows, 7, float(x_suma_haber_saldo), back_gray_bold_monetary)
                                        # Encabezado
                                        x_rows += 1
                                        x_row_page += 1
                                        x_page += 1
                                        worksheet.write(x_rows, 7, "Folio: " + str(self.folio + x_page), right_format)
                                        x_rows += 1
                                        x_row_page += 1
                                        worksheet.merge_range(x_rows, 0, x_rows, 7, self.company_id.name,
                                                              header_merge_format)  # Encabezado
                                        x_rows += 1
                                        x_row_page += 1
                                        worksheet.merge_range(x_rows, 0, x_rows, 7,
                                                              "NIT: " + self.company_id.partner_id.vat,
                                                              header_merge_format)  # Encabezado
                                        x_rows += 1
                                        x_row_page += 1
                                        worksheet.merge_range(x_rows, 0, x_rows, 7, "Libro Mayor",
                                                              header_merge_format)  # Encabezado
                                        num_days = monthrange(self.anio, int(self.mes_a))[1]
                                        x_rows += 1
                                        x_row_page += 1
                                        worksheet.merge_range(x_rows, 0, x_rows, 7, str("Del 01 de " + str(
                                            dict(self._fields['mes_de'].selection).get(self.mes_de)) + " de " + str(
                                            self.anio) + " Al " + str(
                                            num_days) + " de " + str(
                                            dict(self._fields['mes_a'].selection).get(self.mes_a)) + " de " + str(
                                            self.anio)), header_merge_format)  # Encabezado
                                        x_rows += 1
                                        x_row_page += 1
                                        worksheet.merge_range(x_rows, 0, x_rows, 7, "(EXPRESADO EN QUETZALES)",
                                                              header_merge_format)  # Encabezado
                                        x_rows += 1
                                        x_row_page += 1
                                        worksheet.merge_range(x_rows, 0, x_rows, 1, "DEBE",
                                                              border_back_gray_head_left)
                                        worksheet.merge_range(x_rows, 2, x_rows, 5,
                                                              str(linea.get('codigodebe') + ' ' + linea.get(
                                                                  'cuentadebe')),
                                                              border_back_gray_head_center)
                                        worksheet.merge_range(x_rows, 6, x_rows, 7, "HABER",
                                                              border_back_gray_head_right)
                                        # Fin encabezado 2
                                        # Vienen
                                        x_rows += 1
                                        x_row_page += 1
                                        worksheet.merge_range(x_rows, 0, x_rows, 1, "VIENEN", back_gray_bold)
                                        worksheet.write(x_rows, 2, float(x_suma_debe), back_gray_bold_monetary)
                                        worksheet.write(x_rows, 3, float(x_suma_debe_saldo), back_gray_bold_monetary)
                                        worksheet.write(x_rows, 4, "", back_gray_bold_monetary)
                                        worksheet.write(x_rows, 5, "", back_gray_bold_monetary)
                                        worksheet.write(x_rows, 6, float(x_suma_haber), back_gray_bold_monetary)
                                        worksheet.write(x_rows, 7, float(x_suma_haber_saldo), back_gray_bold_monetary)
                                    else:
                                        x_suma_debe += float(linea.get('debe'))
                                        x_suma_debe_saldo += (float(linea.get('debe')) + float(linea.get('saldodebe')))
                                        x_suma_haber += float(linea.get('haber'))
                                        x_suma_haber_saldo += (float(linea.get('haber')) + float(linea.get('saldohaber')))

                                        x_rows += 1
                                        x_row_page += 1
                                        worksheet.write(x_rows, 0, str(linea.get('partidadebe')), detail_no_border)
                                        worksheet.write(x_rows, 1, str(linea.get('fechadebe')),
                                                        detail_date_format)
                                        worksheet.write(x_rows, 2, float(linea.get('debe')), detail_monetary_format)
                                        worksheet.write(x_rows, 3, x_suma_debe_saldo, detail_monetary_format_center)
                                        worksheet.write(x_rows, 4, str(linea.get('partidahaber')), detail_no_border)
                                        worksheet.write(x_rows, 5, str(linea.get('fechahaber')),
                                                        detail_date_format)
                                        worksheet.write(x_rows, 6, float(linea.get('haber')), detail_monetary_format)
                                        worksheet.write(x_rows, 7, x_suma_haber_saldo, detail_monetary_format)
                                    # x_suma_debe += float(linea.get('debe'))
                                    # x_suma_debe_saldo += float(linea.get('debe'))
                                    # x_suma_haber += float(linea.get('haber'))
                                    # x_suma_haber_saldo += float(linea.get('haber'))

                    x_last_codigo_cuenta = str(linea.get('codigodebe') + ' ' + linea.get('cuentadebe'))
                    if x_total_row_count == x_iteracion:
                        x_rows += 1
                        x_row_page = 0
                        header_data_format_dia.set_top(1)
                        detail_monetary_format_bold_dia.set_top(1)
                        worksheet.merge_range(x_rows, 0, x_rows, 1, "TOTALES", header_data_format_dia)
                        worksheet.write(x_rows, 2, float(x_suma_debe), detail_monetary_format_bold_dia)
                        worksheet.write(x_rows, 3, float(x_suma_debe_saldo), detail_monetary_format_bold_dia_right)
                        worksheet.merge_range(x_rows, 4, x_rows, 5, "TOTALES", header_data_format_dia)
                        worksheet.write(x_rows, 6, float(x_suma_haber), detail_monetary_format_bold_dia)
                        worksheet.write(x_rows, 7, float(x_suma_haber_saldo), detail_monetary_format_bold_dia)

                        x_suma_debe = 0  # reseteamos el van y vienen
                        x_suma_haber_saldo = 0 # reseteamos el van y vienen
                        x_suma_haber = 0  # reseteamos el van y vienen
                        x_suma_debe_saldo = 0 # reseteamos el van y vienen


                else:
                    x_rows += 1
                    x_page += 1
                    x_row_page = 0

        #imprimiendo solo la consulta
        else:
            worksheet.write(x_rows, 7, "Folio: " + str(self.folio + x_page), right_format)
            x_rows += 1
            x_row_page += 1
            worksheet.merge_range(x_rows, 0, x_rows, 7, self.company_id.name,
                                  header_merge_format)  # Encabezado
            x_rows += 1
            x_row_page += 1
            worksheet.merge_range(x_rows, 0, x_rows, 7, "NIT: " + self.company_id.partner_id.vat,
                                  header_merge_format)  # Encabezado
            x_rows += 1
            x_row_page += 1
            worksheet.merge_range(x_rows, 0, x_rows, 7, "Libro Mayor", header_merge_format)  # Encabezado
            num_days = monthrange(self.anio, int(self.mes_a))[1]
            x_rows += 1
            x_row_page += 1
            worksheet.merge_range(x_rows, 0, x_rows, 7, str("Del 01 de " + str(
                dict(self._fields['mes_de'].selection).get(self.mes_de)) + " de " + str(
                self.anio) + " Al " + str(
                num_days) + " de " + str(
                dict(self._fields['mes_a'].selection).get(self.mes_a)) + " de " + str(
                self.anio)), header_merge_format)  # Encabezado
            x_rows += 1
            x_row_page += 1
            worksheet.merge_range(x_rows, 0, x_rows, 7, "(EXPRESADO EN QUETZALES)",
                                  header_merge_format)  # Encabezado
            # x_rows += 1
            x_row_page += 1
        workbook.close()
        self.write({
            'state': 'get',
            'data': base64.b64encode(open(xls_path, 'rb').read()),
            'name': xls_filename
        })
        return {
            'name': 'Report Financial MAYor',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new'
        }

class wizard_report_balance_saldo(models.TransientModel):
    _name = 'wizard.report.balance.saldo'
    _description = "Wizard Report Balance Saldo"
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id)
    anio = fields.Integer(string="Año")
    # mes_de = fields.Selection([('1','Enero'),('2','Febrero'),('3','Marzo'),('4','Abril'),('5','Mayo'),('6','Junio'),('7','Julio'),('8','Agosto'),('9','Septiembre'),('10','Octubre'),('11','Noviembre'),('12','Diciembre')],string="De")
    mes_a = fields.Selection(
        [('1', 'Enero'), ('2', 'Febrero'), ('3', 'Marzo'), ('4', 'Abril'), ('5', 'Mayo'), ('6', 'Junio'),
         ('7', 'Julio'), ('8', 'Agosto'), ('9', 'Septiembre'), ('10', 'Octubre'), ('11', 'Noviembre'),
         ('12', 'Diciembre')], string="A")
    folio = fields.Integer(string="Folio")
    state = fields.Selection([('choose', 'choose'), ('get', 'get')], default='choose')
    name = fields.Char(string='File Name', readonly=True)
    data = fields.Binary(string='File', readonly=True)

    #def check_mes(self):
     #   if int(self.mes_de) > int(self.mes_a):
      #      raise ValidationError(_('-Mes De- debe ser anterior a -Mes A-.'))

    def go_back_balance_saldo(self):
        self.state = 'choose'
        return {
            'name': 'Report Financial Balance Saldo',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new'
        }

    def print_xls_report_balance_saldo(self):
        # self.check_mes()
        #company_id = self.env['res.company'].browse(self._context.get('allowed_company_ids'))
        xls_filename = 'Balance de Saldos.xlsx'
        temp_dir = tempfile.gettempdir()
        xls_path = os.path.join(temp_dir, xls_filename)
        workbook = xlsxwriter.Workbook(xls_path)
        # report_in_sql = self.env['report.account_report_financial.report_financial']
        cuentas = self.env['account.account'].search([('company_id', '=', self.company_id.id)
                                                         #,('code', 'in', ['1.0.01.03','1010201','1010202','1010301','1010302','1010403'])
                                                      ], order='code asc')

        sign_format = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                                     'font_size': 10})
        sign_format.set_top(1)
        folio_format = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                           'font_size': 10})

        header_merge_format = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                                   'font': 'Arial','font_size': 10})
        right_format = workbook.add_format({'bold': False, 'align': 'right', \
                                                   'font': 'Arial', 'font_size': 10, 'border': 1})

        header_data_format = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                                  'font': 'Arial','font_size': 10, 'border': 1})
        header_data_format_dia = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                                  'font': 'Arial', 'font_size': 10})

        detail_monetary_format = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'border': 1, 'num_format': 'Q#,##0.00'})
        detail_monetary_format_bold = workbook.add_format({'bold' : True, 'align': 'right', 'font': 'Arial', 'font_size': 10, 'border': 1, 'num_format': 'Q#,##0.00'})
        detail_monetary_format_bold_dia = workbook.add_format(
            {'bold': True, 'align': 'right', 'font': 'Arial', 'font_size': 10, 'num_format': 'Q#,##0.00'})
        detail_monetary_format_bold_dia_right = workbook.add_format(
            {'bold': True, 'align': 'right', 'font': 'Arial', 'font_size': 10, 'num_format': 'Q#,##0.00'})
        detail_monetary_format_bold_dia_right.set_right(6)
        detail_monetary_format_bold_dia_right.set_top(1)
        detail_monetary_format_bold_dia_right.set_bottom(6)
        detail_center_format = workbook.add_format({'align': 'center', 'font': 'Arial', 'font_size': 10, 'border': 1})

        detail_description_format = workbook.add_format({'align': 'center', 'font': 'Arial', 'font_size': 10})
        detail_border = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 10, 'border': 1})
        header_data_format_dia.set_bottom(6)
        detail_monetary_format_bold_dia.set_bottom(6)
        # Por cada bodega

        # --------------------------------------------------------------------------------------------------------------
        # -------------------------------------------------QUERY--------------------------------------------------------
        # consulta = report_in_sql.get_libro_mayor(self)

        # -------------------------------------------------QUERY--------------------------------------------------------
        worksheet = workbook.add_worksheet("Balance de Saldos")
        worksheet.set_landscape()
        worksheet.set_page_view()
        worksheet.set_paper(1)
        worksheet.set_margins(0.7,0.7,0.7,0.7)
        # Tamaños Mayor
        worksheet.set_column('A:A', 10) # Primer Codigo
        worksheet.set_column('B:B', 46) # Primer Cuenta
        worksheet.set_column('C:C', 10) # Primer Debe
        worksheet.set_column('D:D', 10) # Primer Haber
        worksheet.set_column('E:E', 10) # Segundo Debe
        worksheet.set_column('F:F', 10) # Segundo Haber
        worksheet.set_column('G:G', 10) # Tercer Debe
        worksheet.set_column('H:H', 10) # Tercer Haber
        worksheet.set_column('I:I', 10) # Segundo Codigo
        worksheet.set_column('J:J', 46) # Segunda Cuenta
        worksheet.set_column('K:K', 10) # Cuarto Debe
        worksheet.set_column('L:L', 10) # Cuarto Haber
        worksheet.set_column('M:M', 10) # Quinto Debe
        worksheet.set_column('N:N', 10) # Quinto Haber
        worksheet.set_column('O:O', 10) # Sexto Debe
        worksheet.set_column('P:P', 10) # Sexto Haber
        worksheet.set_column('Q:Q', 10) # Tercer Codigo
        worksheet.set_column('R:R', 46) # Tercera Cuenta
        worksheet.set_column('S:S', 10) # Septimo Debe
        worksheet.set_column('T:T', 10) # Septimo Haber
        worksheet.set_column('U:U', 10) # Octavo Debe
        worksheet.set_column('V:V', 10) # Octavo Haber
        worksheet.set_column('W:W', 10) # Noveno Debe
        worksheet.set_column('X:X', 10) # Noveno Haber
        worksheet.set_column('Y:Y', 10) # Cuarto Codigo
        worksheet.set_column('Z:Z', 46) # Cuarta Cuenta
        worksheet.set_column('AA:AA', 10) # Decimo Debe
        worksheet.set_column('AB:AB', 10) # Decimo Haber
        worksheet.set_column('AC:AC', 10) # Onceavo Debe
        worksheet.set_column('AD:AD', 10) # Onceavo Haber
        worksheet.set_column('AE:AE', 10) # Doceavo Debe
        worksheet.set_column('AF:AF', 10) # Doceavo Haber
        worksheet.set_column('AG:AG', 10) # Quinto Codigo
        worksheet.set_column('AH:AH', 46) # Quinta Cuenta
        worksheet.set_column('AI:AI', 10) # Treceavo Debe
        worksheet.set_column('AJ:AJ', 10) # Treceavo Haber

        # Empieza detalle
        x_rows = 0 # Linea a imprimir
        x_cols = 0 # Columna a imprimir
        x_page = 0 # Numero de pagina
        x_max_rows = 35 # Maximo de lineas por pagina
        x_max_cols = 8 # Maximo de columnas por pagina
        x_row_page = 0 # Linea actual vrs maximo de lineas
        x_col_page = 0 # Columna actual vrs maximo de columnas
        x_total_col_count = 0 # Total de columnas
        x_cant_meses = int(self.mes_a)
        if x_cant_meses == 1:
            x_total_col_count = 6
        elif x_cant_meses == 2:
            x_total_col_count = 8
        elif x_cant_meses == 3:
            x_total_col_count = 12
        elif x_cant_meses == 4:
            x_total_col_count = 14
        elif x_cant_meses == 5:
            x_total_col_count = 16
        elif x_cant_meses == 6:
            x_total_col_count = 20
        elif x_cant_meses == 7:
            x_total_col_count = 22
        elif x_cant_meses == 8:
            x_total_col_count = 24
        elif x_cant_meses == 9:
            x_total_col_count = 28
        elif x_cant_meses == 10:
            x_total_col_count = 30
        elif x_cant_meses == 11:
            x_total_col_count = 32
        elif x_cant_meses == 12:
            x_total_col_count = 36

        x_debe_haber = [   0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                           0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                           0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                           0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                           0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                           0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                           0.0, 0.0, 0.0, 0.0, 0.0, 0.0,]

        x_thDebe = 0.0
        x_thHaber = 0.0
        x_last_codigo_cuenta = 'vacio'
        x_suma_debe = 0
        x_suma_debe_saldo = 0
        x_suma_haber = 0
        x_suma_haber_saldo = 0
        x_iteracion = 0
        x_itera_mes = 0

        if cuentas:
            x_rows = 0
            x_row_page = 0
            thMes = int(self.mes_a)
            num_days = monthrange(self.anio, int(self.mes_a))[1]
            datos = 0
            for cuenta in cuentas:
                x_mes_actual = 0
                if cuenta.code == '1010403':
                    x_aux = 1
                x_thHaber = 0.0
                x_thDebe = 0.0
                saldos = self.env["account.move.line"].search(
                    [('account_id', '=', cuenta.id),
                     ('move_id.date', '>=', datetime.strptime(str(self.anio)+'-01-01', '%Y-%m-%d').date()),
                     ('move_id.date', '<=', datetime.strptime(str(self.anio) + "-" + str(self.mes_a) + "-" + str(monthrange(self.anio, int(self.mes_a))[1]), '%Y-%m-%d').date()),
                     ('move_id.state', '=', 'posted'),
                     ('move_id.company_id.id', '=', self.env.company.id)])

                if len(saldos) > 0:
                    datos +=1
                    # Esta es la ultima linea de la pagina
                    if x_row_page >= 8 and x_row_page == (x_max_rows-1):
                        x_cols = 0
                        while x_cols < x_total_col_count:  # Columnas por reporte
                            if x_cols in [0, 8, 16, 24, 32]: # Columna vacia por VAN
                                worksheet.write(x_rows, x_cols, '', header_data_format)
                            if x_cols > 0:
                                if x_cols in [1, 9, 17, 25, 33]:  # Columna de Codigos
                                    worksheet.write(x_rows, x_cols, 'VAN', header_data_format)
                                else:
                                    if x_cols not in [0, 8, 16, 24, 32]:
                                        worksheet.write(x_rows, x_cols, x_debe_haber[x_cols], detail_monetary_format_bold)
                            x_cols += 1
                        x_rows += 1
                        x_row_page = 0

                        # Encabezado
                        # Encabezado
                        # 17-02-2024 Edvin aqui agregar el folio de la pagina

                        folio2 = self.folio + 5
                        if x_row_page == 0:  # Folio
                            if x_total_col_count > 0:
                                x_cols = 0
                                while x_cols < x_total_col_count:  # Columnas por reporte
                                    if x_cols == 0:
                                        x_cols += 6
                                        worksheet.write(x_rows, x_cols, "Folio: " + str(folio2 + x_cols // 8),
                                                        folio_format)
                                        if x_total_col_count in [6, 8]:
                                            x_cols += 2
                                    else:
                                        x_cols += 8
                                        worksheet.write(x_rows, x_cols, "Folio: " + str(folio2 + x_cols // 8),
                                                        folio_format)
                            x_rows += 1
                            x_row_page += 1

                        if x_row_page == 1:  # Empresa
                            if x_total_col_count > 0:
                                x_cols = 0
                                while x_cols < x_total_col_count:  # Columnas por reporte
                                    worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 7, self.company_id.name,
                                                          header_merge_format)
                                    x_cols += 8
                                x_rows += 1
                                x_row_page += 1

                        if x_row_page == 2:  # Nit
                            if x_total_col_count > 0:
                                x_cols = 0
                                while x_cols < x_total_col_count:  # Columnas por reporte
                                    worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 7, "NIT: "+ self.company_id.vat,
                                                          header_merge_format)
                                    x_cols += 8
                                x_rows += 1
                                x_row_page += 1

                        if x_row_page == 3:  # Balance de Saldos
                            if x_total_col_count > 0:
                                x_cols = 0
                                while x_cols < x_total_col_count:  # Columnas por reporte
                                    worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 7, "Balance de Saldos",
                                                          header_merge_format)
                                    x_cols += 8
                            x_rows += 1
                            x_row_page += 1

                        if x_row_page == 4:  # Fecha
                            if x_total_col_count > 0:
                                x_cols = 0
                                while x_cols < x_total_col_count:  # Columnas por reporte
                                    worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 7,
                                                          str("Del 01 de Enero de " + str(self.anio) + " Al " + str(
                                                              monthrange(self.anio, int(self.mes_a))[1]) + " de " + str(
                                                              dict(self._fields['mes_a'].selection).get(
                                                                  self.mes_a)) + " de " + str(self.anio)),
                                                          header_merge_format)
                                    x_cols += 8
                            x_rows += 1
                            x_row_page += 1

                        if x_row_page == 5:  # Expresado en Quetzales
                            if x_total_col_count > 0:
                                x_cols = 0
                                while x_cols < x_total_col_count:  # Columnas por reporte
                                    worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 7, "(Expresado en Quetzales)", header_merge_format)
                                    x_cols += 8
                            x_rows += 2
                            x_row_page += 2

                        if x_row_page == 7:  # Meses
                            if x_total_col_count > 0:
                                x_cols = 0
                                while x_cols < x_total_col_count:  # Columnas por reporte
                                    if x_cols == 2:
                                        worksheet.merge_range(x_rows, x_cols, x_rows, x_cols+1, "Saldo Inicial", header_data_format)  # Saldo Inicial
                                    elif x_cols == 4:
                                        worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Enero", header_data_format)
                                    elif x_cols == 6:
                                        worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Febrero", header_data_format)
                                    elif x_cols == 10:
                                        worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Marzo", header_data_format)
                                    elif x_cols == 12:
                                        worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Abril", header_data_format)
                                    elif x_cols == 14:
                                        worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Mayo", header_data_format)
                                    elif x_cols == 18:
                                        worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Junio", header_data_format)
                                    elif x_cols == 20:
                                        worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Julio", header_data_format)
                                    elif x_cols == 22:
                                        worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Agosto", header_data_format)
                                    elif x_cols == 26:
                                        worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Septiembre", header_data_format)
                                    elif x_cols == 28:
                                        worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Octubre", header_data_format)
                                    elif x_cols == 30:
                                        worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Noviembre", header_data_format)
                                    elif x_cols == 34:
                                        worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Diciembre", header_data_format)
                                    x_cols += 2
                            x_rows += 1
                            x_row_page += 1

                        if x_row_page == 8:  # Debe Haber
                            if x_total_col_count > 0:
                                x_cols = 0
                                while x_cols < x_total_col_count:  # Columnas por reporte
                                    if x_cols in [0, 8, 16, 24, 32, 40]:
                                        worksheet.write(x_rows, x_cols, "Código", header_data_format)
                                    if x_cols in [1, 9, 17, 25, 33, 41]:
                                        worksheet.write(x_rows, x_cols, "Cuenta", header_data_format)
                                    if x_cols in [2, 4, 6, 10, 12, 14, 18, 20, 22, 26, 28, 30, 34, 36, 38]:
                                        worksheet.write(x_rows, x_cols, "Debe", header_data_format)
                                    elif x_cols in [3, 5, 7, 11, 13, 15, 19, 21, 23, 27, 29, 31, 35, 37]:
                                        worksheet.write(x_rows, x_cols, "Haber", header_data_format)
                                    x_cols += 1
                        x_rows += 1
                        x_row_page += 1

                        if x_rows > 8:
                            x_cols = 0
                            while x_cols < x_total_col_count:  # Columnas por reporte
                                if x_cols in [0, 8, 16, 24, 32]:  # Columna vacia por VIENEN
                                    worksheet.write(x_rows, x_cols, ' ', header_data_format)
                                if x_cols > 0:
                                    if x_cols in [1, 9, 17, 25, 33]:
                                        worksheet.write(x_rows, x_cols, 'VIENEN', header_data_format)
                                    else:
                                        worksheet.write(x_rows, x_cols, x_debe_haber[x_cols],
                                                        detail_monetary_format_bold)
                                x_cols += 1

                            x_rows += 1
                            x_row_page += 1

                        # imprimir linea normal
                        if x_cant_meses == 1:
                            x_mes_actual = 0
                        else:
                            x_mes_actual = 1
                        x_cols = 0

                        # Control de meses, se controla para imprimir las columnas de saldos iniciales
                        # La complejidad esta en que el saldo inicial se toma como un mes en el ciclo for y se debe sumar un ciclo
                        while x_mes_actual < x_cant_meses:
                            if x_cant_meses == 1:
                                x_mes_actual = 1
                            while x_cols < x_total_col_count:
                                num_days = monthrange(self.anio, x_mes_actual)[1]
                                if x_cols in [0, 8, 16, 24, 32]:  # Columna de Codigos
                                    worksheet.write(x_rows, x_cols, str(saldos.account_id.code), right_format)
                                elif x_cols in [1, 9, 17, 25, 33]:  # Columna de Cuentas
                                    worksheet.write(x_rows, x_cols, str(saldos.account_id.name), detail_border)
                                elif x_cols in [2, 10, 18, 26, 34]:  # Columna de Primer Debe
                                    if x_cols == 2 and x_mes_actual == 1:  # estamos en el primer debe para saldo inicial
                                        x_thDebe += sum((line.move_id.date == datetime.strptime(str(self.anio) + '-01-01', '%Y-%m-%d').date() and line.balance) for line in saldos if line.move_id.journal_id.name == 'Partida de Apertura')
                                        if x_thDebe > 0:
                                            worksheet.write(x_rows, x_cols, x_thDebe, detail_monetary_format)
                                            x_debe_haber[x_cols] += x_thDebe
                                        else:
                                            worksheet.write(x_rows, x_cols, 0, detail_monetary_format)
                                    else:
                                        x_thDebe += sum((line.move_id.date >= datetime.strptime(str(self.anio) + '-' + str(x_mes_actual) + '-01','%Y-%m-%d').date() and line.move_id.date <= datetime.strptime(str(self.anio) + '-' + str(x_mes_actual) + '-' + str(num_days),'%Y-%m-%d').date() and line.balance) for line in saldos)
                                        if x_thDebe > 0:
                                            worksheet.write(x_rows, x_cols, x_thDebe, detail_monetary_format)
                                            x_debe_haber[x_cols] += x_thDebe
                                        else:
                                            worksheet.write(x_rows, x_cols, 0, detail_monetary_format)
                                elif x_cols in [3, 11, 19, 27, 35]:  # Columna de Primer Haber
                                    if x_cols == 3 and x_mes_actual == 1:  # estamos en el primer haber para saldo inicial
                                        # Ojo aca
                                        x_thHaber += sum((line.move_id.date == datetime.strptime(str(self.anio) + '-01-01','%Y-%m-%d').date() and line.balance)for line in saldos if line.move_id.journal_id.name == 'Partida de Apertura')
                                        if x_thHaber < 0:
                                            worksheet.write(x_rows, x_cols, x_thHaber * -1, detail_monetary_format)
                                            x_debe_haber[x_cols] += x_thHaber * -1
                                        else:
                                            worksheet.write(x_rows, x_cols, 0, detail_monetary_format)
                                    else:
                                        x_thHaber += sum((line.move_id.date >= datetime.strptime(str(self.anio) + '-'+ str(x_mes_actual) +'-01','%Y-%m-%d').date() and line.move_id.date <= datetime.strptime(str(self.anio) + '-' + str(x_mes_actual) + '-' + str(num_days),'%Y-%m-%d').date() and line.balance) for line in saldos)
                                        if x_thHaber < 0:
                                            worksheet.write(x_rows, x_cols, x_thHaber * -1, detail_monetary_format)
                                            x_debe_haber[x_cols] += x_thHaber * -1
                                        else:
                                            worksheet.write(x_rows, x_cols, 0, detail_monetary_format)
                                elif x_cols in [4, 12, 20, 28, 36]:  # Columna de segundo Debe
                                    if x_cols == 4:
                                        x_thDebe = 0
                                    x_thDebe += sum((line.move_id.date >= datetime.strptime(
                                            str(self.anio) + '-' + str(x_mes_actual) + '-01',
                                            '%Y-%m-%d').date() and line.move_id.date <= datetime.strptime(
                                        str(self.anio) + '-' + str(x_mes_actual) + '-' + str(num_days),
                                        '%Y-%m-%d').date() and line.balance) for line in saldos)
                                    if x_thDebe > 0:
                                        worksheet.write(x_rows, x_cols, x_thDebe, detail_monetary_format)
                                        x_debe_haber[x_cols] += x_thDebe
                                    else:
                                        worksheet.write(x_rows, x_cols, 0, detail_monetary_format)
                                elif x_cols in [5, 13, 21, 29, 37]:  # Columna de segundo Haber
                                    if x_cols == 5:
                                        x_thHaber = 0
                                    x_thHaber += sum((line.move_id.date >= datetime.strptime(
                                            str(self.anio) + '-' + str(x_mes_actual) + '-01',
                                            '%Y-%m-%d').date() and line.move_id.date <= datetime.strptime(
                                        str(self.anio) + '-' + str(x_mes_actual) + '-' + str(num_days),
                                        '%Y-%m-%d').date() and line.balance) for line in saldos)
                                    if x_thHaber < 0:
                                        worksheet.write(x_rows, x_cols, x_thHaber * -1, detail_monetary_format)
                                        x_debe_haber[x_cols] += x_thHaber * -1
                                    else:
                                        worksheet.write(x_rows, x_cols, 0, detail_monetary_format)
                                elif x_cols in [6, 14, 22, 30, 38]:  # Columna tercer debe
                                    x_thDebe += sum((line.move_id.date >= datetime.strptime(
                                            str(self.anio) + '-' + str(x_mes_actual) + '-01',
                                            '%Y-%m-%d').date() and line.move_id.date <= datetime.strptime(
                                        str(self.anio) + '-' + str(x_mes_actual) + '-' + str(num_days),
                                        '%Y-%m-%d').date() and line.balance) for line in saldos)
                                    if x_thDebe > 0:
                                        worksheet.write(x_rows, x_cols, x_thDebe, detail_monetary_format)
                                        x_debe_haber[x_cols] += x_thDebe
                                    else:
                                        worksheet.write(x_rows, x_cols, 0, detail_monetary_format)
                                elif x_cols in [7, 15, 23, 31, 39]:  # Columna tercer haber
                                    x_thHaber += sum((line.move_id.date >= datetime.strptime(
                                            str(self.anio) + '-' + str(x_mes_actual) + '-01',
                                            '%Y-%m-%d').date() and line.move_id.date <= datetime.strptime(
                                        str(self.anio) + '-' + str(x_mes_actual) + '-' + str(num_days),
                                        '%Y-%m-%d').date() and line.balance) for line in saldos)
                                    if x_thHaber < 0:
                                        worksheet.write(x_rows, x_cols, x_thHaber * -1, detail_monetary_format)
                                        x_debe_haber[x_cols] += x_thHaber * -1
                                    else:
                                        worksheet.write(x_rows, x_cols, 0, detail_monetary_format)
                                if x_cols not in [0, 1, 3, 8, 16, 24, 32, 9, 17, 25, 33] and x_cols % 2 == 1 and (
                                        x_mes_actual < x_cant_meses):
                                    x_mes_actual += 1
                                x_cols += 1
                        x_rows += 1
                        x_row_page += 1

                    elif x_row_page >= 8 and x_row_page < x_max_rows - 1:
                        if x_cant_meses == 1:
                            x_mes_actual = 0
                        else:
                            x_mes_actual = 1
                        x_cols = 0
                        while x_mes_actual < x_cant_meses:
                            if x_cant_meses == 1:
                                x_mes_actual = 1

                            while x_cols < x_total_col_count:  # Columnas por reporte
                                num_days = monthrange(self.anio, x_mes_actual)[1]
                                if x_cols in [0, 8, 16, 24, 32]:  # Columna de Codigos
                                    worksheet.write(x_rows, x_cols, str(saldos.account_id.code), right_format)
                                elif x_cols in [1, 9, 17, 25, 33]:  # Columna de Cuentas
                                    worksheet.write(x_rows, x_cols, str(saldos.account_id.name), detail_border)
                                elif x_cols in [2, 10, 18, 26, 34]:  # Columna de Primer Debe
                                    if x_cols == 2 and x_mes_actual == 1:  # estamos en el primer debe para saldo inicial
                                        x_thDebe += sum((line.move_id.date == datetime.strptime(str(self.anio) + '-01-01',
                                                                                       '%Y-%m-%d').date() and line.balance)
                                               for line in saldos if line.move_id.journal_id.name == 'Partida de Apertura')
                                        if x_thDebe > 0:
                                            worksheet.write(x_rows, x_cols, x_thDebe, detail_monetary_format)
                                            x_debe_haber[x_cols] += x_thDebe
                                        else:
                                            worksheet.write(x_rows, x_cols, 0, detail_monetary_format)
                                    else:
                                        x_thDebe += sum((line.move_id.date >= datetime.strptime(
                                                str(self.anio) + '-' + str(x_mes_actual) + '-01',
                                                '%Y-%m-%d').date() and line.move_id.date <= datetime.strptime(
                                            str(self.anio) + '-' + str(x_mes_actual) + '-' + str(num_days),
                                            '%Y-%m-%d').date() and line.balance) for line in saldos)
                                        if x_thDebe > 0:
                                            worksheet.write(x_rows, x_cols, x_thDebe, detail_monetary_format)
                                            x_debe_haber[x_cols] += x_thDebe
                                        else:
                                            worksheet.write(x_rows, x_cols, 0, detail_monetary_format)
                                elif x_cols in [3, 11, 19, 27, 35]:  # Columna de Primer Haber
                                    if x_cols == 3 and x_mes_actual == 1:  # estamos en el primer haber para saldo inicial
                                        x_thHaber += sum((line.move_id.date == datetime.strptime(str(self.anio) + '-01-01',
                                                                                       '%Y-%m-%d').date() and line.balance)
                                               for line in saldos if line.move_id.journal_id.name == 'Partida de Apertura')
                                        if x_thHaber < 0:
                                            worksheet.write(x_rows, x_cols, x_thHaber * -1, detail_monetary_format)
                                            x_debe_haber[x_cols] += x_thHaber * -1
                                        else:
                                            worksheet.write(x_rows, x_cols, 0, detail_monetary_format)
                                    else:
                                        x_thHaber += sum((line.move_id.date >= datetime.strptime(str(self.anio) + '-'+ str(x_mes_actual) +'-01',
                                                                                       '%Y-%m-%d').date() and line.move_id.date <= datetime.strptime(
                                            str(self.anio) + '-' + str(x_mes_actual) + '-' + str(num_days),
                                            '%Y-%m-%d').date() and line.balance) for line in saldos)
                                        if x_thHaber < 0:
                                            worksheet.write(x_rows, x_cols, x_thHaber * -1, detail_monetary_format)
                                            x_debe_haber[x_cols] += x_thHaber * -1
                                        else:
                                            worksheet.write(x_rows, x_cols, 0, detail_monetary_format)
                                elif x_cols in [4, 12, 20, 28, 36]:  # Columna de segundo Debe
                                    if x_cols == 4:
                                        x_thDebe = 0
                                    x_thDebe += sum((line.move_id.date >= datetime.strptime(
                                            str(self.anio) + '-' + str(x_mes_actual) + '-01',
                                            '%Y-%m-%d').date() and line.move_id.date <= datetime.strptime(
                                        str(self.anio) + '-' + str(x_mes_actual) + '-' + str(num_days),
                                        '%Y-%m-%d').date() and line.balance) for line in saldos)
                                    if x_thDebe > 0:
                                        worksheet.write(x_rows, x_cols, x_thDebe, detail_monetary_format)
                                        x_debe_haber[x_cols] += x_thDebe
                                    else:
                                        worksheet.write(x_rows, x_cols, 0, detail_monetary_format)
                                elif x_cols in [5, 13, 21, 29, 37]:  # Columna de segundo Haber
                                    if x_cols == 5:
                                        x_thHaber = 0
                                    x_thHaber += sum((line.move_id.date >= datetime.strptime(
                                            str(self.anio) + '-' + str(x_mes_actual) + '-01',
                                            '%Y-%m-%d').date() and line.move_id.date <= datetime.strptime(
                                        str(self.anio) + '-' + str(x_mes_actual) + '-' + str(num_days),
                                        '%Y-%m-%d').date() and line.balance) for line in saldos)
                                    if x_thHaber < 0:
                                        worksheet.write(x_rows, x_cols, x_thHaber * -1, detail_monetary_format)
                                        x_debe_haber[x_cols] += x_thHaber * -1
                                    else:
                                        worksheet.write(x_rows, x_cols, 0, detail_monetary_format)
                                elif x_cols in [6, 14, 22, 30, 38]:  # Columna tercer debe
                                    x_thDebe += sum((line.move_id.date >= datetime.strptime(
                                            str(self.anio) + '-' + str(x_mes_actual) + '-01',
                                            '%Y-%m-%d').date() and line.move_id.date <= datetime.strptime(
                                        str(self.anio) + '-' + str(x_mes_actual) + '-' + str(num_days),
                                        '%Y-%m-%d').date() and line.balance) for line in saldos)
                                    if x_thDebe > 0:
                                        worksheet.write(x_rows, x_cols, x_thDebe, detail_monetary_format)
                                        x_debe_haber[x_cols] += x_thDebe
                                    else:
                                        worksheet.write(x_rows, x_cols, 0, detail_monetary_format)
                                elif x_cols in [7, 15, 23, 31, 39]:  # Columna tercer haber
                                    x_thHaber += sum((line.move_id.date >= datetime.strptime(
                                            str(self.anio) + '-' + str(x_mes_actual) + '-01',
                                            '%Y-%m-%d').date() and line.move_id.date <= datetime.strptime(
                                        str(self.anio) + '-' + str(x_mes_actual) + '-' + str(num_days),
                                        '%Y-%m-%d').date() and line.balance) for line in saldos)
                                    if x_thHaber < 0:
                                        worksheet.write(x_rows, x_cols, x_thHaber * -1, detail_monetary_format)
                                        x_debe_haber[x_cols] += x_thHaber * -1
                                    else:
                                        worksheet.write(x_rows, x_cols, 0, detail_monetary_format)
                                if x_cols not in [0, 1, 3, 8, 16, 24, 32, 9, 17, 25, 33] and x_cols % 2 == 1 and (
                                        x_mes_actual < x_cant_meses):
                                    x_mes_actual += 1
                                x_cols += 1

                        x_rows += 1
                        x_row_page += 1
                    # ---------------------------- Encabezado ----------------------------------------------------------
                    elif x_row_page == 0 and x_rows == 0:  # Nueva pagina
                        # Encabezado
                        # # Primer encabezado de la pagina
                        # if x_row_page == 0:  # Folio
                        #     if x_total_col_count > 0:
                        #         x_cols = 0
                        #         while x_cols < x_total_col_count:  # Columnas por reporte
                        #             if x_cols == 0:
                        #                 x_cols += 6
                        #                 worksheet.write(x_rows, x_cols, "Folio: ", folio_format)
                        #                 if x_total_col_count in [6, 8]:
                        #                     x_cols += 2
                        #             else:
                        #                 x_cols += 8
                        #                 worksheet.write(x_rows, x_cols, "Folio: ",
                        #                                     folio_format)
                        if x_row_page == 0:  # Folio
                            if x_total_col_count > 0:
                                x_cols = 0
                                while x_cols < x_total_col_count:  # Columnas por reporte
                                    if x_cols == 0:
                                        x_cols += 6
                                        worksheet.write(x_rows, x_cols, "Folio: " + str(self.folio + x_cols // 8),
                                                        folio_format)
                                        if x_total_col_count in [6, 8]:
                                            x_cols += 2
                                    else:
                                        x_cols += 8
                                        worksheet.write(x_rows, x_cols, "Folio: " + str(self.folio + x_cols // 8),
                                                        folio_format)

                            x_rows += 1
                            x_row_page += 1

                        if x_row_page == 1:  # Empresa
                            if x_total_col_count > 0:
                                x_cols = 0
                                while x_cols < x_total_col_count:  # Columnas por reporte
                                    worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 7, self.company_id.name, header_merge_format)
                                    x_cols += 8
                                x_rows += 1
                                x_row_page += 1

                        if x_row_page == 2:  # Nit
                            if x_total_col_count > 0:
                                x_cols = 0
                                while x_cols < x_total_col_count:  # Columnas por reporte
                                    worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 7, 'NIT: '+ self.company_id.vat,
                                                          header_merge_format)
                                    x_cols += 8
                                x_rows += 1
                                x_row_page += 1

                        if x_row_page == 3:  # Balance de Saldos
                            if x_total_col_count > 0:
                                x_cols = 0
                                while x_cols < x_total_col_count:  # Columnas por reporte
                                    worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 7, "Balance de Saldos",
                                                          header_merge_format)
                                    x_cols += 8
                            x_rows += 1
                            x_row_page += 1

                        if x_row_page == 4:  # Fecha
                            if x_total_col_count > 0:
                                x_cols = 0
                                while x_cols < x_total_col_count:  # Columnas por reporte
                                    worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 7,
                                                          str("Del 01 de Enero de " + str(self.anio) + " Al " + str(
                                                              monthrange(self.anio, int(self.mes_a))[1]) + " de " + str(
                                                              dict(self._fields['mes_a'].selection).get(
                                                                  self.mes_a)) + " de " + str(self.anio)),
                                                          header_merge_format)
                                    x_cols += 8
                            x_rows += 1
                            x_row_page += 1

                        if x_row_page == 5:  # Expresado en Quetzales
                            if x_total_col_count > 0:
                                x_cols = 0
                                while x_cols < x_total_col_count:  # Columnas por reporte
                                    worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 7, "(Expresado en Quetzales)",
                                                          header_merge_format)
                                    x_cols += 8
                            x_rows += 2
                            x_row_page += 2

                        if x_row_page == 7:  # Meses
                            if x_total_col_count > 0:
                                x_cols = 0
                                while x_cols < x_total_col_count:  # Columnas por reporte
                                    if x_cols == 2:
                                        worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Saldo Inicial",
                                                              header_data_format)  # Saldo Inicial
                                    elif x_cols == 4:
                                        worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Enero",
                                                              header_data_format)
                                    elif x_cols == 6:
                                        worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Febrero",
                                                              header_data_format)
                                    elif x_cols == 10:
                                        worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Marzo",
                                                              header_data_format)
                                    elif x_cols == 12:
                                        worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Abril",
                                                              header_data_format)
                                    elif x_cols == 14:
                                        worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Mayo",
                                                              header_data_format)
                                    elif x_cols == 18:
                                        worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Junio",
                                                              header_data_format)
                                    elif x_cols == 20:
                                        worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Julio",
                                                              header_data_format)
                                    elif x_cols == 22:
                                        worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Agosto",
                                                              header_data_format)
                                    elif x_cols == 26:
                                        worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Septiembre",
                                                              header_data_format)
                                    elif x_cols == 28:
                                        worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Octubre",
                                                              header_data_format)
                                    elif x_cols == 30:
                                        worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Noviembre",
                                                              header_data_format)
                                    elif x_cols == 34:
                                        worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Diciembre",
                                                              header_data_format)
                                    x_cols += 2
                            x_rows += 1
                            x_row_page += 1

                        if x_row_page == 8:  # Debe Haber
                            if x_total_col_count > 0:
                                x_cols = 0
                                while x_cols < x_total_col_count:  # Columnas por reporte
                                    if x_cols in [0, 8, 16, 24, 32, 40]:
                                        worksheet.write(x_rows, x_cols, "Código", header_data_format)
                                    if x_cols in [1, 9, 17, 25, 33, 41]:
                                        worksheet.write(x_rows, x_cols, "Cuenta", header_data_format)
                                    if x_cols in [2, 4, 6, 10, 12, 14, 18, 20, 22, 26, 28, 30, 34, 36, 38]:
                                        worksheet.write(x_rows, x_cols, "Debe", header_data_format)
                                    elif x_cols in [3, 5, 7, 11, 13, 15, 19, 21, 23, 27, 29, 31, 35, 37]:
                                        worksheet.write(x_rows, x_cols, "Haber", header_data_format)
                                    x_cols += 1
                        x_rows+=1
                        x_row_page+=1
                        if x_cant_meses == 1:
                            x_mes_actual = 0
                        else:
                            x_mes_actual = 1
                        x_cols = 0
                        while x_mes_actual < x_cant_meses:
                            if x_cant_meses == 1:
                                x_mes_actual = 1
                            while x_cols < x_total_col_count:  # Columnas por reporte
                                num_days = monthrange(self.anio, x_mes_actual)[1]
                                if x_cols in [0, 8, 16, 24, 32]:  # Columna de Codigos
                                    worksheet.write(x_rows, x_cols, str(saldos.account_id.code), right_format)
                                elif x_cols in [1, 9, 17, 25, 33]:  # Columna de Cuentas
                                    worksheet.write(x_rows, x_cols, str(saldos.account_id.name), detail_border)
                                elif x_cols in [2, 10, 18, 26, 34]:  # Columna de Primer Debe
                                    if x_cols == 2 and x_mes_actual == 1:  # estamos en el primer debe para saldo inicial
                                        x_thDebe += sum(
                                            (line.move_id.date == datetime.strptime(str(self.anio) + '-01-01',
                                                                                    '%Y-%m-%d').date() and line.balance)
                                            for line in saldos if line.move_id.journal_id.name == 'Partida de Apertura')
                                        if x_thDebe > 0:
                                            worksheet.write(x_rows, x_cols, x_thDebe, detail_monetary_format)
                                            x_debe_haber[x_cols] += x_thDebe
                                        else:
                                            worksheet.write(x_rows, x_cols, 0, detail_monetary_format)
                                    else:
                                        x_thDebe += sum((line.move_id.date >= datetime.strptime(
                                                str(self.anio) + '-' + str(x_mes_actual) + '-01',
                                                '%Y-%m-%d').date() and line.move_id.date <= datetime.strptime(
                                            str(self.anio) + '-' + str(x_mes_actual) + '-' + str(num_days),
                                            '%Y-%m-%d').date() and line.balance) for line in saldos)
                                        if x_thDebe > 0:
                                            worksheet.write(x_rows, x_cols, x_thDebe, detail_monetary_format)
                                            x_debe_haber[x_cols] += x_thDebe
                                        else:
                                            worksheet.write(x_rows, x_cols, 0, detail_monetary_format)
                                elif x_cols in [3, 11, 19, 27, 35]:  # Columna de Primer Haber
                                    if x_cols == 3 and x_mes_actual == 1:  # estamos en el primer haber para saldo inicial
                                        x_thHaber += sum(
                                            (line.move_id.date == datetime.strptime(str(self.anio) + '-01-01',
                                                                                    '%Y-%m-%d').date() and line.balance) for line in saldos if line.move_id.journal_id.name == 'Partida de Apertura')
                                        if x_thHaber < 0:
                                            worksheet.write(x_rows, x_cols, x_thHaber * -1, detail_monetary_format)
                                            #x_debe_haber[x_cols] += x_thHaber * -1
                                        else:
                                            worksheet.write(x_rows, x_cols, 0, detail_monetary_format)
                                    else:
                                        x_thHaber += sum((line.move_id.date >= datetime.strptime(str(self.anio) + '-' + str(x_mes_actual) +'-01',
                                                                                       '%Y-%m-%d').date() and line.move_id.date <= datetime.strptime(
                                            str(self.anio) + '-' + str(x_mes_actual) + '-' + str(num_days),
                                            '%Y-%m-%d').date() and line.balance) for line in saldos)
                                        if x_thHaber < 0:
                                            worksheet.write(x_rows, x_cols, x_thHaber * -1, detail_monetary_format)
                                            x_debe_haber[x_cols] += x_thHaber * -1
                                        else:
                                            worksheet.write(x_rows, x_cols, 0, detail_monetary_format)
                                elif x_cols in [4, 12, 20, 28, 36]:  # Columna de segundo Debe
                                    if x_cols == 4:
                                        x_thDebe = 0
                                    x_thDebe += sum((line.move_id.date >= datetime.strptime(
                                            str(self.anio) + '-' + str(x_mes_actual) + '-01',
                                            '%Y-%m-%d').date() and line.move_id.date <= datetime.strptime(
                                        str(self.anio) + '-' + str(x_mes_actual) + '-' + str(num_days),
                                        '%Y-%m-%d').date() and line.balance) for line in saldos)
                                    if x_thDebe > 0:
                                        worksheet.write(x_rows, x_cols, x_thDebe, detail_monetary_format)
                                        x_debe_haber[x_cols] += x_thDebe
                                    else:
                                        worksheet.write(x_rows, x_cols, 0, detail_monetary_format)
                                elif x_cols in [5, 13, 21, 29, 37]:  # Columna de segundo Haber
                                    if x_cols == 5:
                                        x_thHaber = 0
                                    x_thHaber += sum((line.move_id.date >= datetime.strptime(
                                            str(self.anio) + '-' + str(x_mes_actual) + '-01',
                                            '%Y-%m-%d').date() and line.move_id.date <= datetime.strptime(
                                        str(self.anio) + '-' + str(x_mes_actual) + '-' + str(num_days),
                                        '%Y-%m-%d').date() and line.balance) for line in saldos)
                                    if x_thHaber < 0:
                                        worksheet.write(x_rows, x_cols, x_thHaber * -1, detail_monetary_format)
                                        x_debe_haber[x_cols] += x_thHaber * -1
                                    else:
                                        worksheet.write(x_rows, x_cols, 0, detail_monetary_format)
                                elif x_cols in [6, 14, 22, 30, 38]:  # Columna tercer debe
                                    x_thDebe += sum((line.move_id.date >= datetime.strptime(
                                            str(self.anio) + '-' + str(x_mes_actual) + '-01',
                                            '%Y-%m-%d').date() and line.move_id.date <= datetime.strptime(
                                        str(self.anio) + '-' + str(x_mes_actual) + '-' + str(num_days),
                                        '%Y-%m-%d').date() and line.balance) for line in saldos)
                                    if x_thDebe > 0:
                                        worksheet.write(x_rows, x_cols, x_thDebe, detail_monetary_format)
                                        x_debe_haber[x_cols] += x_thDebe
                                    else:
                                        worksheet.write(x_rows, x_cols, 0, detail_monetary_format)
                                elif x_cols in [7, 15, 23, 31, 39]:  # Columna tercer haber
                                    x_thHaber += sum((line.move_id.date >= datetime.strptime(
                                            str(self.anio) + '-' + str(x_mes_actual) + '-01',
                                            '%Y-%m-%d').date() and line.move_id.date <= datetime.strptime(
                                        str(self.anio) + '-' + str(x_mes_actual) + '-' + str(num_days),
                                        '%Y-%m-%d').date() and line.balance) for line in saldos)
                                    if x_thHaber < 0:
                                        worksheet.write(x_rows, x_cols, x_thHaber * -1, detail_monetary_format)
                                        x_debe_haber[x_cols] += x_thHaber * -1
                                    else:
                                        worksheet.write(x_rows, x_cols, 0, detail_monetary_format)
                                if x_cols not in [0, 1, 3, 8, 16, 24, 32, 9, 17, 25, 33] and x_cols % 2 == 1 and (
                                        x_mes_actual < x_cant_meses):
                                    x_mes_actual += 1
                                x_cols += 1
                        x_rows += 1
                        x_row_page += 1
                    x_cols = 0

            if datos <= 0:
                x_row_page = 0
                x_rows = 0
                if x_row_page == 0:  # Folio
                    if x_total_col_count > 0:
                        x_cols = 0
                        while x_cols < x_total_col_count:  # Columnas por reporte
                            if x_cols == 0:
                                x_cols += 6
                                worksheet.write(x_rows, x_cols, "Folio: " + str(self.folio + x_cols // 8),
                                                folio_format)
                                if x_total_col_count in [6, 8]:
                                    x_cols += 2
                            else:
                                x_cols += 8
                                worksheet.write(x_rows, x_cols, "Folio: " + str(self.folio + x_cols // 8),
                                                folio_format)
                        x_rows += 1
                        x_row_page += 1

                if x_row_page == 1:  # Empresa
                    if x_total_col_count > 0:
                        x_cols = 0
                        while x_cols < x_total_col_count:  # Columnas por reporte
                            worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 7, self.company_id.name,
                                                  header_merge_format)
                            x_cols += 8
                        x_rows += 1
                        x_row_page += 1

                if x_row_page == 2:  # Nit
                    if x_total_col_count > 0:
                        x_cols = 0
                        while x_cols < x_total_col_count:  # Columnas por reporte
                            worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 7, 'NIT: ' + self.company_id.vat,
                                                  header_merge_format)
                            x_cols += 8
                        x_rows += 1
                        x_row_page += 1

                if x_row_page == 3:  # Balance de Saldos
                    if x_total_col_count > 0:
                        x_cols = 0
                        while x_cols < x_total_col_count:  # Columnas por reporte
                            worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 7, "Balance de Saldos",
                                                  header_merge_format)
                            x_cols += 8
                    x_rows += 1
                    x_row_page += 1

                if x_row_page == 4:  # Fecha
                    if x_total_col_count > 0:
                        x_cols = 0
                        while x_cols < x_total_col_count:  # Columnas por reporte
                            worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 7,
                                                  str("Del 01 de Enero de " + str(self.anio) + " Al " + str(
                                                      monthrange(self.anio, int(self.mes_a))[1]) + " de " + str(
                                                      dict(self._fields['mes_a'].selection).get(
                                                          self.mes_a)) + " de " + str(self.anio)),
                                                  header_merge_format)
                            x_cols += 8
                    x_rows += 1
                    x_row_page += 1

                if x_row_page == 5:  # Expresado en Quetzales
                    if x_total_col_count > 0:
                        x_cols = 0
                        while x_cols < x_total_col_count:  # Columnas por reporte
                            worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 7, "(Expresado en Quetzales)",
                                                  header_merge_format)
                            x_cols += 8
                    x_rows += 2
                    x_row_page += 2

                if x_row_page == 7:  # Meses
                    if x_total_col_count > 0:
                        x_cols = 0
                        while x_cols < x_total_col_count:  # Columnas por reporte
                            if x_cols == 2:
                                worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Saldo Inicial",
                                                      header_data_format)  # Saldo Inicial
                            elif x_cols == 4:
                                worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Enero",
                                                      header_data_format)
                            elif x_cols == 6:
                                worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Febrero",
                                                      header_data_format)
                            elif x_cols == 10:
                                worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Marzo",
                                                      header_data_format)
                            elif x_cols == 12:
                                worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Abril",
                                                      header_data_format)
                            elif x_cols == 14:
                                worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Mayo",
                                                      header_data_format)
                            elif x_cols == 18:
                                worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Junio",
                                                      header_data_format)
                            elif x_cols == 20:
                                worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Julio",
                                                      header_data_format)
                            elif x_cols == 22:
                                worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Agosto",
                                                      header_data_format)
                            elif x_cols == 26:
                                worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Septiembre",
                                                      header_data_format)
                            elif x_cols == 28:
                                worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Octubre",
                                                      header_data_format)
                            elif x_cols == 30:
                                worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Noviembre",
                                                      header_data_format)
                            elif x_cols == 34:
                                worksheet.merge_range(x_rows, x_cols, x_rows, x_cols + 1, "Diciembre",
                                                      header_data_format)
                            x_cols += 2
                    x_rows += 1
                    x_row_page += 1

                if x_row_page == 8:  # Debe Haber
                    if x_total_col_count > 0:
                        x_cols = 0
                        while x_cols < x_total_col_count:  # Columnas por reporte
                            if x_cols in [0, 8, 16, 24, 32, 40]:
                                worksheet.write(x_rows, x_cols, "Código", header_data_format)
                            if x_cols in [1, 9, 17, 25, 33, 41]:
                                worksheet.write(x_rows, x_cols, "Cuenta", header_data_format)
                            if x_cols in [2, 4, 6, 10, 12, 14, 18, 20, 22, 26, 28, 30, 34, 36, 38]:
                                worksheet.write(x_rows, x_cols, "Debe", header_data_format)
                            elif x_cols in [3, 5, 7, 11, 13, 15, 19, 21, 23, 27, 29, 31, 35, 37]:
                                worksheet.write(x_rows, x_cols, "Haber", header_data_format)
                            x_cols += 1
                    x_rows += 1
                    x_row_page += 1
            # ---------------------------- Sumas Iguales ----------------------------------------------------------


            x_cols = 0
            while x_cols < x_total_col_count:  # Columnas por reporte
                if x_cols in [0, 8, 16, 24, 32]:  # Columna vacia para sumas iguales
                    worksheet.write(x_rows, x_cols, '', header_data_format)
                if x_cols > 0:
                    if x_cols in [1, 9, 17, 25, 33]:  # Sumas iguales
                        worksheet.write(x_rows, x_cols, 'SUMAS IGUALES', header_data_format)
                    else:
                        if x_cols not in [0, 8, 16, 24, 32]:
                            worksheet.write(x_rows, x_cols, x_debe_haber[x_cols], detail_monetary_format_bold)
                x_cols += 1
            x_rows += 3



        workbook.close()
        self.write({
            'state': 'get',
            'data': base64.b64encode(open(xls_path, 'rb').read()),
            'name': xls_filename
        })
        return {
            'name': 'Balance de Saldos',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new'
        }

class wizard_estado_resultados(models.TransientModel):
    _name = 'wizard.estado.resultados'
    _description = "Wizard Estado de Resultados"
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id)
    start_date = fields.Date(string="Fecha Inicio")
    end_date = fields.Date(string="Fecha Fin")

    anio = fields.Integer(string="Año")
    mes_de = fields.Selection([('1','Enero'),('2','Febrero'),('3','Marzo'),('4','Abril'),('5','Mayo'),('6','Junio'),('7','Julio'),('8','Agosto'),('9','Septiembre'),('10','Octubre'),('11','Noviembre'),('12','Diciembre')],string="De")
    mes_a = fields.Selection(
        [('1', 'Enero'), ('2', 'Febrero'), ('3', 'Marzo'), ('4', 'Abril'), ('5', 'Mayo'), ('6', 'Junio'),
         ('7', 'Julio'), ('8', 'Agosto'), ('9', 'Septiembre'), ('10', 'Octubre'), ('11', 'Noviembre'),
         ('12', 'Diciembre')], string="A")
    folio = fields.Integer(string="Folio")
    certificacion = fields.Char(string="Certificación")
    representante = fields.Char(string="Representante Legal")
    contador = fields.Char(string="Contador")
    filter_by = fields.Selection([('product', 'Product'), ('category', 'Category')], string="Filter By")
    group_by_categ = fields.Boolean(string="Group By Category")
    state = fields.Selection([('choose', 'choose'), ('get', 'get')], default='choose')
    name = fields.Char(string='File Name', readonly=True)
    data = fields.Binary(string='File', readonly=True)
    product_ids = fields.Many2many('product.product', string="Products")
    category_ids = fields.Many2many('product.category', string="Categories")
    # Columnas para el reporte


    @api.onchange('company_id')
    def onchange_company_id(self):
        domain = [('id', 'in', self.env.user.company_ids.ids)]
        # if self.company_id:
            # self.warehouse_ids = False
            # self.location_ids = False
        return {'domain':{'company_id':domain}}

    def check_date_range(self):
        if self.end_date < self.start_date:
            raise ValidationError(_('Fecha fin ser posterior a fecha inicio.'))

    def check_mes(self):
        if int(self.mes_de) > int(self.mes_a):
            raise ValidationError(_('Mes De debe ser anterior a mes A.'))

    @api.onchange('filter_by')
    def onchange_filter_by(self):
        self.product_ids = False
        self.category_ids = False

    def print_report(self):
        self.check_date_range()
        datas = {'form':
                    {
                        'company_id': self.company_id.id,
                        'warehouse_ids': [y.id for y in self.warehouse_ids],
                        'location_ids': self.location_ids.ids or False,
                        'start_date': self.start_date,
                        'end_date': self.end_date,
                        'id': self.id,
                        'product_ids': self.product_ids.ids,
                        'product_categ_ids': self.category_ids.ids
                    },
                }
        return self.env.ref('account_report_financial.action_report_financial_template').report_action(self, data=datas)

    def go_back(self):
        self.state = 'choose'
        return {
            'name': 'Report Financial Estado Resultados',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new'
        }

    def print_xls_estado_resultados(self):

        thMes = ""
        thMesa = ""
        if self.start_date.month == 1:
            thMes = "Enero"
        elif self.start_date.month == 2:
            thMes = "Febrero"
        elif self.start_date.month == 3:
            thMes = "Marzo"
        elif self.start_date.month == 4:
            thMes = "Abril"
        elif self.start_date.month == 5:
            thMes = "Mayo"
        elif self.start_date.month == 6:
            thMes = "Junio"
        elif self.start_date.month == 7:
            thMes = "Julio"
        elif self.start_date.month == 8:
            thMes = "Agosto"
        elif self.start_date.month == 9:
            thMes = "Septiembre"
        elif self.start_date.month == 10:
            thMes = "Octubre"
        elif self.start_date.month == 11:
            thMes = "Noviembre"
        else:
            thMes = "Diciembre"

        if self.end_date.month == 1:
            thMesa = "Enero"
        elif self.end_date.month == 2:
            thMesa = "Febrero"
        elif self.end_date.month == 3:
            thMesa = "Marzo"
        elif self.end_date.month == 4:
            thMesa = "Abril"
        elif self.end_date.month == 5:
            thMesa = "Mayo"
        elif self.end_date.month == 6:
            thMesa = "Junio"
        elif self.end_date.month == 7:
            thMesa = "Julio"
        elif self.end_date.month == 8:
            thMesa = "Agosto"
        elif self.end_date.month == 9:
            thMesa = "Septiembre"
        elif self.end_date.month == 10:
            thMesa = "Octubre"
        elif self.end_date.month == 11:
            thMesa = "Noviembre"
        else:
            thMesa = "Diciembre"

        self.check_date_range()
        #self.check_mes()
        #company_id = self.env['res.company'].browse(self._context.get('allowed_company_ids'))
        xls_filename = 'Estado de Resultados.xlsx'
        temp_dir = tempfile.gettempdir()
        xls_path = os.path.join(temp_dir, xls_filename)
        workbook = xlsxwriter.Workbook(xls_path)

        frmt_folio = workbook.add_format({'bold': False, 'align': 'right', \
                                          'font': 'Arial', 'font_size': 10})
        frmt_encabezado = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                               'font': 'Arial', 'font_size': 10})
        frmt_borde_superior = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                                   'font': 'Arial', 'font_size': 10})
        frmt_cuenta_head_foot = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 10, 'bold' : True})
        frmt_cuenta = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 10})
        frmt_van_vacio = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 10, 'border': 1})
        frmt_codigo = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'bold': True})
        frmt_codigo_utilidad_ejercicio = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'bold': True})
        frmt_utilidad_ejercicio = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 10, 'bold': True})
        debe_utilidad_ejercicio = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'border': 1, 'bold': True, 'num_format': 'Q#,##0.00'})
        haber_utilidad_ejercicio = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'border': 1, 'bold': True, 'num_format': 'Q#,##0.00'})
        debe_haber_vacio = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10})
        debe_haber = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'border':1, 'num_format': 'Q#,##0.00'})
        debe_haber_nivel_ii = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'border' : 1, 'num_format': 'Q#,##0.00'})
        debe_haber_nivel_i = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'bold' : True, 'num_format': 'Q#,##0.00'})
        debe_haber_van_vienen = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'bold' : True, 'border' : 1, 'num_format': 'Q#,##0.00'})

        frmt_van = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                                      'font': 'Arial', 'font_size': 10, 'num_format': 'Q#,##0.00'})
        frmt_firma = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                               'font': 'Arial', 'font_size': 10})
        frmt_codigo_utilidad_ejercicio.set_bottom(1)
        frmt_codigo_utilidad_ejercicio.set_left(1)
        frmt_utilidad_ejercicio.set_bottom(1)
        haber_utilidad_ejercicio.set_bottom(6)

        frmt_borde_superior.set_bottom(1)

        frmt_codigo.set_left(1)

        frmt_cuenta.set_right(1)
        frmt_cuenta_head_foot.set_right(1)

        debe_haber_vacio.set_left(1)
        debe_haber_vacio.set_right(1)

        debe_haber_nivel_i.set_right(1)
        debe_haber_nivel_i.set_left(1)
        debe_haber_nivel_i.set_bottom(6)

        worksheet = workbook.add_worksheet("Estado de Resultados")
        worksheet.set_portrait()
        worksheet.set_page_view()
        worksheet.set_paper(1)
        worksheet.set_margins(0.7,0.7,0.7,0.7)
        # Tamaños
        worksheet.set_column('A:A', 10)
        worksheet.set_column('B:B', 45)
        worksheet.set_column('C:C', 15)
        worksheet.set_column('D:D', 15)
        # Empieza detalle
        x_rows = 0 # Linea a imprimir
        x_page = 0 # Numero de pagina
        x_max_rows = 47 # Maximo de lineas por pagina
        x_row_page = 0 # Linea actual vrs maximo de lineas
        x_ctrl_nivel_i = ''
        x_ctrl_nivel_ii = ''
        x_altura = 0
        x_recorre = 0
        x_suma_debe = 0
        x_suma_haber = 0
        x_iteracion = 0
        x_NiveliInicial = 4 # Aca empezamos desde los ingresos
        x_NiveliFinal = int(self.env['account.group'].search([
                                                            ('company_id.id', '=', self.company_id.id),
                                                            ('parent_id', '=', False),
                                                            ], order="code_prefix_start desc", limit=1).mapped('code_prefix_start')[0])
        a_imprimir = []
        while x_NiveliInicial <= x_NiveliFinal: # Principal ciclo para saber que grupos van a ser tomados en cuenta en este caso 4 ingresos 5 cotos 6 gastos
            # Buscamos el id de grupo de la raiz nivel i
            NivelI = self.env['account.group'].search(
            [('company_id.id', '=', self.company_id.id),
             ('parent_id', '=', False),
             ('code_prefix_start', '=', x_NiveliInicial)],
                order="code_prefix_start asc", limit =1)

            if NivelI:
                for x_NivelI in NivelI:
                    x_control = 0
                    x_control = sum(self.env['account.move.line'].search([
                        ('account_id.group_id.parent_id.parent_id.id', 'in', x_NivelI.ids),
                        ('move_id.state', '=', 'posted'),
                        ('date', '>=', self.start_date),
                        ('date', '<=', self.end_date),
                        ('balance', '!=', 0),
                        ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
                    if x_control != 0:
                        a_imprimir.append([])
                        a_imprimir[x_altura].append(x_NivelI.code_prefix_start)
                        a_imprimir[x_altura].append('')
                        a_imprimir[x_altura].append('head_nivel_i')
                        a_imprimir[x_altura].append(x_NivelI.code_prefix_start)
                        a_imprimir[x_altura].append(x_NivelI.name)
                        a_imprimir[x_altura].append(0)
                        a_imprimir[x_altura].append(0)

                        x_altura += 1
                        # Buscamos el id de grupo del nivel ii que pertenezcan a nivel i
                        NivelII = self.env['account.group'].search([('parent_id.id', 'in', x_NivelI.ids)],
                                                                   order="code_prefix_start asc")

                        if NivelII:
                            for x_NivelII in NivelII:
                                x_control = 0
                                x_control = sum(self.env['account.move.line'].search([
                                    ('account_id.group_id.parent_id.id', 'in', x_NivelII.ids),
                                    ('move_id.state', '=', 'posted'),
                                    ('date', '>=', self.start_date),
                                    ('date', '<=', self.end_date),
                                    ('balance', '!=', 0),
                                    ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
                                if x_control != 0:
                                    a_imprimir.append([])
                                    a_imprimir[x_altura].append(x_NivelI.code_prefix_start)
                                    a_imprimir[x_altura].append(x_NivelII.code_prefix_start)
                                    a_imprimir[x_altura].append('head_nivel_ii')
                                    a_imprimir[x_altura].append(x_NivelII.code_prefix_start)
                                    a_imprimir[x_altura].append(x_NivelII.name)
                                    a_imprimir[x_altura].append(0)
                                    a_imprimir[x_altura].append(0)
                                    x_altura += 1
                                    # Buscamos el id de grupo de cuenta que pertenezca a nivel ii
                                    NivelGrupoCuenta = self.env['account.group'].search(
                                        [('parent_id.id', 'in', x_NivelII.ids)],
                                        order="code_prefix_start asc")
                                    if NivelGrupoCuenta:
                                        for x_NivelGrupoCuenta in NivelGrupoCuenta:
                                            x_balance = sum(self.env['account.move.line'].search([
                                                ('account_id.group_id.id', 'in', x_NivelGrupoCuenta.ids),
                                                ('move_id.state', '=', 'posted'),
                                                ('date', '>=', self.start_date),
                                                ('date', '<=', self.end_date),
                                                ('balance', '!=', 0),
                                                ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
                                            if x_balance != 0:
                                                a_imprimir.append([])
                                                a_imprimir[x_altura].append(x_NivelI.code_prefix_start)
                                                a_imprimir[x_altura].append(x_NivelII.code_prefix_start)
                                                a_imprimir[x_altura].append('nivel_gc')
                                                a_imprimir[x_altura].append(x_NivelGrupoCuenta.code_prefix_start)
                                                a_imprimir[x_altura].append(x_NivelGrupoCuenta.name)
                                                # 10-05-2024 Edvin aqui se agrega la condicion de cuando x_NivelI.code_prefix_start == '7'
                                                # Que multipleque por -1
                                                if x_NivelI.code_prefix_start == '4' or x_NivelI.code_prefix_start == '7':  # 4 Ingresos
                                                    a_imprimir[x_altura].append(x_balance * -1)
                                                else:
                                                    a_imprimir[x_altura].append(x_balance)
                                                a_imprimir[x_altura].append(0)
                                                x_altura += 1
                                    a_imprimir.append([])
                                    a_imprimir[x_altura].append(x_NivelI.code_prefix_start)
                                    a_imprimir[x_altura].append(x_NivelII.code_prefix_start)
                                    a_imprimir[x_altura].append('foot_nivel_ii')
                                    a_imprimir[x_altura].append('')
                                    a_imprimir[x_altura].append('   Suma ' + x_NivelII.name)
                                    a_imprimir[x_altura].append(0)
                                    x_balance = sum(self.env['account.move.line'].search([
                                        ('account_id.group_id.parent_id.id', 'in', x_NivelII.ids),
                                        ('move_id.state', '=', 'posted'),
                                        ('date', '>=', self.start_date),
                                        ('date', '<=', self.end_date),
                                        ('balance', '!=', 0),
                                        ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
                                    if x_NivelI.code_prefix_start == '4' or x_NivelI.code_prefix_start == '7':  # 4 Ingresos
                                        a_imprimir[x_altura].append(x_balance * -1)
                                    else:
                                        a_imprimir[x_altura].append(x_balance)
                                    x_altura += 1
                        a_imprimir.append([])
                        a_imprimir[x_altura].append(x_NivelI.code_prefix_start)
                        a_imprimir[x_altura].append(x_NivelII.code_prefix_start)
                        a_imprimir[x_altura].append('foot_nivel_i')
                        a_imprimir[x_altura].append('')
                        a_imprimir[x_altura].append('   TOTAL DE ' + x_NivelI.name)
                        a_imprimir[x_altura].append(0)
                        x_balance = sum(self.env['account.move.line'].search([
                            ('account_id.group_id.parent_id.parent_id.id', 'in', x_NivelI.ids),
                            ('move_id.state', '=', 'posted'),
                            ('date', '>=', self.start_date),
                            ('date', '<=', self.end_date),
                            ('balance', '!=', 0),
                            ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
                        if x_NivelI.code_prefix_start == '4' or  x_NivelI.code_prefix_start == '7':  # 4 Ingresos
                            a_imprimir[x_altura].append(x_balance * -1)
                        else:
                            a_imprimir[x_altura].append(x_balance)
                        # Coloca utilidad bruta despues de categoria 5
                        if x_NivelI.code_prefix_start == '5' or x_NivelI.code_prefix_start == '6':
                            x_balance_4 = 0
                            x_balance_4 = sum(self.env['account.move.line'].search([
                                ('account_id.group_id.parent_id.parent_id.code_prefix_start', '=', '4'),
                                ('move_id.state', '=', 'posted'),
                                ('date', '>=', self.start_date),
                                ('date', '<=', self.end_date),
                                ('balance', '!=', 0),
                                ('company_id.id', '=', self.company_id.id)]).mapped('balance')) *-1
                            x_balance_5 = 0
                            x_balance_5 = sum(self.env['account.move.line'].search([
                                ('account_id.group_id.parent_id.parent_id.code_prefix_start', '=', '5'),
                                ('move_id.state', '=', 'posted'),
                                ('date', '>=', self.start_date),
                                ('date', '<=', self.end_date),
                                ('balance', '!=', 0),
                                ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
                            x_balance_6 = 0
                            x_balance_6 = sum(self.env['account.move.line'].search([
                                ('account_id.group_id.parent_id.parent_id.code_prefix_start', '=', '6'),
                                ('move_id.state', '=', 'posted'),
                                ('date', '>=', self.start_date),
                                ('date', '<=', self.end_date),
                                ('balance', '!=', 0),
                                ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
                            if x_NivelI.code_prefix_start == '5':
                                x_altura += 1
                                a_imprimir.append([])
                                a_imprimir[x_altura].append('')
                                a_imprimir[x_altura].append('')
                                a_imprimir[x_altura].append('utilidad_bruta')
                                a_imprimir[x_altura].append('')
                                a_imprimir[x_altura].append('   UTILIDAD BRUTA')
                                a_imprimir[x_altura].append(0)
                                a_imprimir[x_altura].append(x_balance_4 - x_balance_5)

                            if x_NivelI.code_prefix_start == '6' or (x_NivelI.code_prefix_start == '5' and x_balance_6 == 0):
                                x_altura += 1
                                a_imprimir.append([])
                                a_imprimir[x_altura].append('')
                                a_imprimir[x_altura].append('')
                                a_imprimir[x_altura].append('resultado_operacion')
                                a_imprimir[x_altura].append('')
                                a_imprimir[x_altura].append('   RESULTADO EN OPERACION')
                                a_imprimir[x_altura].append(0)
                                a_imprimir[x_altura].append(x_balance_4 - x_balance_5 - x_balance_6)
                        x_altura += 1
            x_NiveliInicial += 1
        # Calculo de la utilidad del ejercicio
        x_balance_4 = 0
        x_balance_4 = sum(self.env['account.move.line'].search([
            ('account_id.group_id.parent_id.parent_id.code_prefix_start', '=', '4'),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', self.start_date),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id)]).mapped('balance')) * -1
        x_balance_5 = 0
        x_balance_5 = sum(self.env['account.move.line'].search([
            ('account_id.group_id.parent_id.parent_id.code_prefix_start', '=', '5'),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', self.start_date),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
        x_balance_6 = 0
        x_balance_6 = sum(self.env['account.move.line'].search([
            ('account_id.group_id.parent_id.parent_id.code_prefix_start', '=', '6'),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', self.start_date),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
        x_balance_7 = 0
        x_balance_7 = sum(self.env['account.move.line'].search([
            ('account_id.group_id.parent_id.parent_id.code_prefix_start', '=', '7'),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', self.start_date),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id)]).mapped('balance')) * -1
        x_balance_8 = 0
        x_balance_8 = sum(self.env['account.move.line'].search([
            ('account_id.group_id.parent_id.parent_id.code_prefix_start', '=', '8'),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', self.start_date),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
        a_imprimir.append([])
        a_imprimir[x_altura].append('')
        a_imprimir[x_altura].append('')
        a_imprimir[x_altura].append('utilidad_ejercicio')
        a_imprimir[x_altura].append('')
        a_imprimir[x_altura].append('   RESULTADO DEL EJERCICIO')
        a_imprimir[x_altura].append(0)
        #Edvin aqui se hace el calculot del resultado del ejercicio y corregirlo aqúi
        a_imprimir[x_altura].append((x_balance_4 - x_balance_5 - x_balance_6)+x_balance_7-x_balance_8)


        if a_imprimir:
            while x_recorre < len(a_imprimir):
                x_iteracion += 1
                if x_ctrl_nivel_i == a_imprimir[x_recorre][0] and x_ctrl_nivel_ii == a_imprimir[x_recorre][1]:
                    x_suma_debe += float(a_imprimir[x_recorre][5])
                    x_suma_haber += float(a_imprimir[x_recorre][6])
                elif x_ctrl_nivel_i == a_imprimir[x_recorre][0] and x_ctrl_nivel_ii != a_imprimir[x_recorre][1]:
                    x_suma_debe = 0
                    x_suma_haber += float(a_imprimir[x_recorre][6])
                else:
                    x_suma_debe = 0
                    x_suma_haber = 0
                x_ctrl_nivel_i = a_imprimir[x_recorre][0]
                x_ctrl_nivel_ii = a_imprimir[x_recorre][1]

                if x_row_page < x_max_rows:  # Estamos en ciclo
                    # ---------------------------- Encabezado ----------------------------------------------------------
                    if x_row_page == 0:  # Nueva pagina

                        worksheet.write(x_rows, 3, "Folio: " + str(self.folio + x_page), frmt_folio)

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3, self.company_id.name,
                                              frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3, "NIT: " + self.company_id.partner_id.vat,
                                              frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3, "Estado de Resultados", frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3,
                                              str("Del " + str(self.start_date.day) + " de " + thMes + " de " + str(
                                                  self.start_date.year) + " Al " + str(
                                                  self.end_date.day) + " de " + thMesa + " de " + str(
                                                  self.end_date.year)), frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3, "(EXPRESADO EN QUETZALES)",
                                              frmt_encabezado)  # Encabezado
                        # Aca es solo para cerrar el marco
                        x_rows += 1
                        x_row_page += 1
                        worksheet.write(x_rows, 0, '', frmt_borde_superior)
                        worksheet.write(x_rows, 1, '', frmt_borde_superior)
                        worksheet.write(x_rows, 2, '', frmt_borde_superior)
                        worksheet.write(x_rows, 3, '', frmt_borde_superior)

                        x_rows += 1
                        x_row_page += 1
                        if a_imprimir[x_recorre][2] == 'head_nivel_i' or a_imprimir[x_recorre][2] == 'head_nivel_ii':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber_vacio)
                            worksheet.write(x_rows, 3, '', debe_haber_vacio)
                        elif a_imprimir[x_recorre][2] == 'nivel_gc':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][5], debe_haber)
                            worksheet.write(x_rows, 3, '', debe_haber)
                        elif a_imprimir[x_recorre][2] == 'foot_nivel_ii':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber_nivel_ii)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber_nivel_ii)
                        elif a_imprimir[x_recorre][2] == 'foot_nivel_i':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber_nivel_i)
                        elif a_imprimir[x_recorre][2] == 'utilidad_ejercicio': # utilidad ejercicio
                            worksheet.write(x_rows, 0, '', frmt_codigo_utilidad_ejercicio)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_utilidad_ejercicio)
                            worksheet.write(x_rows, 2, '', debe_utilidad_ejercicio)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], haber_utilidad_ejercicio)
                        else: # utilidad bruta
                            worksheet.write(x_rows, 0, '', frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber)

                    # ---------------------------- Fin Encabezado ----------------------------------------------------------
                    elif x_row_page > 0 and x_row_page == x_max_rows - 1:  # Estamos en la penultima linea

                        x_rows += 1
                        x_row_page = 0
                        worksheet.write(x_rows, 0, '', frmt_van_vacio)
                        worksheet.write(x_rows, 1, 'VAN', frmt_van)
                        worksheet.write(x_rows, 2, float(x_suma_debe), debe_haber_van_vienen)
                        worksheet.write(x_rows, 3, float(x_suma_haber), debe_haber_van_vienen)
                        # Encabezado 1

                        x_rows += 1
                        x_row_page += 1
                        x_page += 1
                        worksheet.write(x_rows, 3, "Folio: " + str(self.folio + x_page), frmt_folio)

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3, self.company_id.name,
                                              frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3, "NIT: " + self.company_id.partner_id.vat,
                                              frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3, "Estado de Resultados",
                                              frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3,
                                              str("Del " + str(self.start_date.day) + " de " + thMes + " de " + str(
                                                  self.start_date.year) + " Al " + str(
                                                  self.end_date.day) + " de " + thMesa + " de " + str(
                                                  self.end_date.year)), frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3, "(EXPRESADO EN QUETZALES)",
                                              frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.write(x_rows, 0, '', frmt_borde_superior)
                        worksheet.write(x_rows, 1, '', frmt_borde_superior)
                        worksheet.write(x_rows, 2, '', frmt_borde_superior)
                        worksheet.write(x_rows, 3, '', frmt_borde_superior)

                        x_rows += 1
                        x_row_page += 1
                        worksheet.write(x_rows, 0, '', frmt_van_vacio)
                        worksheet.write(x_rows, 1, 'VIENEN', frmt_van)
                        worksheet.write(x_rows, 2, float(x_suma_debe), debe_haber_van_vienen)
                        worksheet.write(x_rows, 3, float(x_suma_haber), debe_haber_van_vienen)

                        x_rows += 1
                        x_row_page += 1
                        if a_imprimir[x_recorre][2] == 'head_nivel_i' or a_imprimir[x_recorre][2] == 'head_nivel_ii':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber_vacio)
                            worksheet.write(x_rows, 3, '', debe_haber_vacio)
                        elif a_imprimir[x_recorre][2] == 'nivel_gc':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][5], debe_haber)
                            worksheet.write(x_rows, 3, '', debe_haber)
                        elif a_imprimir[x_recorre][2] == 'foot_nivel_ii':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber_nivel_ii)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber_nivel_ii)
                        elif a_imprimir[x_recorre][2] == 'foot_nivel_i':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber_nivel_i)
                        elif a_imprimir[x_recorre][2] == 'utilidad_ejercicio':  # utilidad ejercicio
                            worksheet.write(x_rows, 0, '', frmt_codigo_utilidad_ejercicio)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_utilidad_ejercicio)
                            worksheet.write(x_rows, 2, '', debe_utilidad_ejercicio)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], haber_utilidad_ejercicio)
                        else:  # utilidad bruta
                            worksheet.write(x_rows, 0, '', frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber)

                    else:  # No estamos en la ultima linea, estamos en la misma cuenta
                        x_rows += 1
                        x_row_page += 1
                        if a_imprimir[x_recorre][2] == 'head_nivel_i' or a_imprimir[x_recorre][2] == 'head_nivel_ii':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber_vacio)
                            worksheet.write(x_rows, 3, '', debe_haber_vacio)
                        elif a_imprimir[x_recorre][2] == 'nivel_gc':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][5], debe_haber)
                            worksheet.write(x_rows, 3, '', debe_haber)
                        elif a_imprimir[x_recorre][2] == 'foot_nivel_ii':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber_nivel_ii)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber_nivel_ii)
                        elif a_imprimir[x_recorre][2] == 'foot_nivel_i':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber_nivel_i)
                        elif a_imprimir[x_recorre][2] == 'utilidad_ejercicio':  # utilidad ejercicio
                            worksheet.write(x_rows, 0, '', frmt_codigo_utilidad_ejercicio)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_utilidad_ejercicio)
                            worksheet.write(x_rows, 2, '', debe_utilidad_ejercicio)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], haber_utilidad_ejercicio)
                        else:  # utilidad bruta
                            worksheet.write(x_rows, 0, '', frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber)

                x_recorre += 1
            certifica = str(self.certificacion)
            text1 = '______________________' \
                   '\n'+self.representante +\
                '\nRepresentante Legal'
            text2 = '______________________' \
                    '\n'+self.contador + \
                    '\nContador'

            options1 = {
                'width': 205,
                'height': 100,
                'x_offset': 0,
                'y_offset': 0,

                'font': {'color': 'black',
                         'font': 'Arial',
                         'size': 10,
                         'bold': True,
                         },
                'align': {'vertical': 'bottom',
                          'horizontal': 'center'
                          },

            }
            options2 = {
                'width': 205,
                'height': 100,
                'x_offset': 0,
                'y_offset': 0,

                'font': {'color': 'black',
                         'font': 'Arial',
                         'size': 10,
                         'bold': True,
                         },
                'align': {'vertical': 'bottom',
                          'horizontal': 'center'
                          },

            }
            cert_options = {
                'width': 615,
                'height': 100,
                'x_offset': 0,
                'y_offset': 0,

                'font': {'color': 'black',
                         'font': 'Arial',
                         'size': 10,
                         'bold': True,
                         },
                'align': {'vertical': 'top',
                          'horizontal': 'left'
                          },

            }
            cell = xl_rowcol_to_cell(x_rows+2, 0)
            worksheet.insert_textbox(cell, certifica, cert_options)
            cell = xl_rowcol_to_cell(x_rows + 7, 0)
            worksheet.insert_textbox(cell, text1, options1)
            cell = xl_rowcol_to_cell(x_rows + 7, 2)
            worksheet.insert_textbox(cell, text2, options2)


        workbook.close()
        self.write({
            'state': 'get',
            'data': base64.b64encode(open(xls_path, 'rb').read()),
            'name': xls_filename
        })
        return {
            'name': 'Estado de Resultados',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new'
        }

class wizard_costo_ventas(models.TransientModel):
    _name = 'wizard.costo.ventas'
    _description = "Wizard Costo de Ventas"
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id)
    start_date = fields.Date(string="Fecha Inicio")
    end_date = fields.Date(string="Fecha Fin")

    anio = fields.Integer(string="Año")
    mes_de = fields.Selection([('1', 'Enero'), ('2', 'Febrero'), ('3', 'Marzo'), ('4', 'Abril'), ('5', 'Mayo'), ('6', 'Junio'), ('7', 'Julio'), ('8', 'Agosto'), ('9', 'Septiembre'), ('10', 'Octubre'), ('11', 'Noviembre'), ('12', 'Diciembre')], string="De")
    mes_a = fields.Selection(
        [('1', 'Enero'), ('2', 'Febrero'), ('3', 'Marzo'), ('4', 'Abril'), ('5', 'Mayo'), ('6', 'Junio'),
         ('7', 'Julio'), ('8', 'Agosto'), ('9', 'Septiembre'), ('10', 'Octubre'), ('11', 'Noviembre'),
         ('12', 'Diciembre')], string="A")
    folio = fields.Integer(string="Folio")
    certificacion = fields.Char(string="Certificación")
    representante = fields.Char(string="Representante Legal")
    contador = fields.Char(string="Contador")
    filter_by = fields.Selection([('product', 'Product'), ('category', 'Category')], string="Filter By")
    group_by_categ = fields.Boolean(string="Group By Category")
    state = fields.Selection([('choose', 'choose'), ('get', 'get')], default='choose')
    name = fields.Char(string='File Name', readonly=True)
    data = fields.Binary(string='File', readonly=True)
    product_ids = fields.Many2many('product.product', string="Products")
    category_ids = fields.Many2many('product.category', string="Categories")
    # Columnas para el reporte

    @api.onchange('company_id')
    def onchange_company_id(self):
        domain = [('id', 'in', self.env.user.company_ids.ids)]
        # if self.company_id:
            # self.warehouse_ids = False
            # self.location_ids = False
        return {'domain' : {'company_id' : domain}}

    def check_date_range(self):
        if self.end_date < self.start_date:
            raise ValidationError(_('Fecha fin ser posterior a fecha inicio.'))

    def check_mes(self):
        if int(self.mes_de) > int(self.mes_a):
            raise ValidationError(_('Mes De debe ser anterior a mes A.'))

    @api.onchange('filter_by')
    def onchange_filter_by(self):
        self.product_ids = False
        self.category_ids = False

    def print_report(self):
        self.check_date_range()
        datas = {'form':
                    {
                        'company_id': self.company_id.id,
                        'warehouse_ids': [y.id for y in self.warehouse_ids],
                        'location_ids': self.location_ids.ids or False,
                        'start_date': self.start_date,
                        'end_date': self.end_date,
                        'id': self.id,
                        'product_ids': self.product_ids.ids,
                        'product_categ_ids': self.category_ids.ids
                    },
                }
        return self.env.ref('account_report_financial.action_report_financial_template').report_action(self, data=datas)

    def go_back(self):
        self.state = 'choose'
        return {
            'name': 'Costo de Ventas',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new'
        }

    def print_xls_costo_ventas(self):

        thMes = ""
        thMesa = ""
        if self.start_date.month == 1:
            thMes = "Enero"
        elif self.start_date.month == 2:
            thMes = "Febrero"
        elif self.start_date.month == 3:
            thMes = "Marzo"
        elif self.start_date.month == 4:
            thMes = "Abril"
        elif self.start_date.month == 5:
            thMes = "Mayo"
        elif self.start_date.month == 6:
            thMes = "Junio"
        elif self.start_date.month == 7:
            thMes = "Julio"
        elif self.start_date.month == 8:
            thMes = "Agosto"
        elif self.start_date.month == 9:
            thMes = "Septiembre"
        elif self.start_date.month == 10:
            thMes = "Octubre"
        elif self.start_date.month == 11:
            thMes = "Noviembre"
        else:
            thMes = "Diciembre"

        if self.end_date.month == 1:
            thMesa = "Enero"
        elif self.end_date.month == 2:
            thMesa = "Febrero"
        elif self.end_date.month == 3:
            thMesa = "Marzo"
        elif self.end_date.month == 4:
            thMesa = "Abril"
        elif self.end_date.month == 5:
            thMesa = "Mayo"
        elif self.end_date.month == 6:
            thMesa = "Junio"
        elif self.end_date.month == 7:
            thMesa = "Julio"
        elif self.end_date.month == 8:
            thMesa = "Agosto"
        elif self.end_date.month == 9:
            thMesa = "Septiembre"
        elif self.end_date.month == 10:
            thMesa = "Octubre"
        elif self.end_date.month == 11:
            thMesa = "Noviembre"
        else:
            thMesa = "Diciembre"

        self.check_date_range()
        #self.check_mes()
        #company_id = self.env['res.company'].browse(self._context.get('allowed_company_ids'))
        xls_filename = 'Costo de Ventas.xlsx'
        temp_dir = tempfile.gettempdir()
        xls_path = os.path.join(temp_dir, xls_filename)
        workbook = xlsxwriter.Workbook(xls_path)

        frmt_folio = workbook.add_format({'bold': False, 'align': 'right', \
                                          'font': 'Arial', 'font_size': 10})
        frmt_encabezado = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                               'font': 'Arial', 'font_size': 10})
        frmt_borde_superior = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                                   'font': 'Arial', 'font_size': 10})
        frmt_cuenta_head_foot = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 10, 'bold' : True})
        frmt_cuenta = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 10})
        frmt_van_vacio = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 10, 'border': 1})
        frmt_codigo = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'bold': True})
        frmt_codigo_utilidad_ejercicio = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'bold': True})
        frmt_utilidad_ejercicio = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 10, 'bold': True})
        debe_utilidad_ejercicio = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'border': 1, 'bold': True, 'num_format': 'Q#,##0.00'})
        haber_utilidad_ejercicio = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'border': 1, 'bold': True, 'num_format': 'Q#,##0.00'})
        debe_haber_vacio = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10})
        debe_haber = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'border':1, 'num_format': 'Q#,##0.00'})
        debe_haber_nivel_ii = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'border' : 1, 'num_format': 'Q#,##0.00'})
        debe_haber_nivel_i = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'bold' : True, 'num_format': 'Q#,##0.00'})
        debe_haber_van_vienen = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'bold' : True, 'border' : 1, 'num_format': 'Q#,##0.00'})

        frmt_van = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                                      'font': 'Arial', 'font_size': 10, 'num_format': 'Q#,##0.00'})
        frmt_firma = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                               'font': 'Arial', 'font_size': 10})
        frmt_codigo_utilidad_ejercicio.set_bottom(1)
        frmt_codigo_utilidad_ejercicio.set_left(1)
        frmt_utilidad_ejercicio.set_bottom(1)
        haber_utilidad_ejercicio.set_bottom(6)

        frmt_borde_superior.set_bottom(1)

        frmt_codigo.set_left(1)

        frmt_cuenta.set_right(1)
        frmt_cuenta_head_foot.set_right(1)

        debe_haber_vacio.set_left(1)
        debe_haber_vacio.set_right(1)

        debe_haber_nivel_i.set_right(1)
        debe_haber_nivel_i.set_left(1)
        debe_haber_nivel_i.set_bottom(6)

        worksheet = workbook.add_worksheet("Costo de Ventas")
        worksheet.set_portrait()
        worksheet.set_page_view()
        worksheet.set_paper(1)
        worksheet.set_margins(0.7,0.7,0.7,0.7)
        # Tamaños
        worksheet.set_column('A:A', 10)
        worksheet.set_column('B:B', 45)
        worksheet.set_column('C:C', 15)
        worksheet.set_column('D:D', 15)
        # Empieza detalle
        x_rows = 0 # Linea a imprimir
        x_page = 0 # Numero de pagina
        x_max_rows = 47 # Maximo de lineas por pagina
        x_row_page = 0 # Linea actual vrs maximo de lineas
        x_ctrl_nivel_i = ''
        x_ctrl_nivel_ii = ''
        x_altura = 0
        x_recorre = 0
        x_suma_debe = 0
        x_suma_haber = 0
        x_iteracion = 0
        x_NiveliInicial = 5 # Aca empezamos desde los ingresos
        x_NiveliFinal = 5
        #x_NiveliFinal = int(self.env['account.group'].search([
         #                                                   ('company_id.id', '=', self.company_id.id),
          #                                                  ('parent_id', '=', False),
           #                                                 ], order="code_prefix_start desc", limit=1).mapped('code_prefix_start')[0])

        a_imprimir = []
        while x_NiveliInicial <= x_NiveliFinal: # Principal ciclo para saber que grupos van a ser tomados en cuenta en este caso 4 ingresos 5 cotos 6 gastos
            # Buscamos el id de grupo de la raiz nivel i
            NivelI = self.env['account.group'].search(
            [('company_id.id', '=', self.company_id.id),
             ('parent_id', '=', False),
             ('code_prefix_start', '=', x_NiveliInicial)],
                order="code_prefix_start asc", limit=1)

            if NivelI:
                for x_NivelI in NivelI:
                    x_control = 0
                    x_control = sum(self.env['account.move.line'].search([
                        ('account_id.group_id.parent_id.parent_id.id', 'in', x_NivelI.ids),
                        ('move_id.state', '=', 'posted'),
                        ('date', '>=', self.start_date),
                        ('date', '<=', self.end_date),
                        ('balance', '!=', 0),
                        ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
                    if x_control != 0:
                        a_imprimir.append([])
                        a_imprimir[x_altura].append(x_NivelI.code_prefix_start)
                        a_imprimir[x_altura].append('')
                        a_imprimir[x_altura].append('head_nivel_i')
                        a_imprimir[x_altura].append(x_NivelI.code_prefix_start)
                        a_imprimir[x_altura].append(x_NivelI.name)
                        a_imprimir[x_altura].append(0)
                        a_imprimir[x_altura].append(0)

                        x_altura += 1
                        # Buscamos el id de grupo del nivel ii que pertenezcan a nivel i
                        NivelII = self.env['account.group'].search([('parent_id.id', 'in', x_NivelI.ids)],
                                                                   order="code_prefix_start asc")
                        if NivelII:
                            for x_NivelII in NivelII:
                                x_control = 0
                                x_control = sum(self.env['account.move.line'].search([
                                    ('account_id.group_id.parent_id.id', 'in', x_NivelII.ids),
                                    ('move_id.state', '=', 'posted'),
                                    ('date', '>=', self.start_date),
                                    ('date', '<=', self.end_date),
                                    ('balance', '!=', 0),
                                    ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
                                if x_control != 0:
                                    if x_NivelII.code_prefix_start == '501':
                                        a_imprimir.append([])
                                        a_imprimir[x_altura].append(x_NivelI.code_prefix_start)
                                        a_imprimir[x_altura].append(x_NivelII.code_prefix_start)
                                        a_imprimir[x_altura].append('head_nivel_ii')
                                        a_imprimir[x_altura].append(x_NivelII.code_prefix_start)
                                        a_imprimir[x_altura].append(x_NivelII.name)
                                        a_imprimir[x_altura].append(0)
                                        a_imprimir[x_altura].append(x_control)
                                        x_altura += 1
                                    else:
                                        a_imprimir.append([])
                                        a_imprimir[x_altura].append(x_NivelI.code_prefix_start)
                                        a_imprimir[x_altura].append(x_NivelII.code_prefix_start)
                                        a_imprimir[x_altura].append('head_nivel_ii')
                                        a_imprimir[x_altura].append(x_NivelII.code_prefix_start)
                                        a_imprimir[x_altura].append(x_NivelII.name)
                                        a_imprimir[x_altura].append(0)
                                        a_imprimir[x_altura].append(0)
                                        x_altura += 1
                                        # Buscamos el id de grupo de cuenta que pertenezca a nivel ii
                                        NivelGrupoCuenta = self.env['account.group'].search(
                                            [('parent_id.id', 'in', x_NivelII.ids)],
                                            order="code_prefix_start asc")
                                        if NivelGrupoCuenta:
                                            for x_NivelGrupoCuenta in NivelGrupoCuenta:
                                                x_balance = sum(self.env['account.move.line'].search([
                                                    ('account_id.group_id.id', 'in', x_NivelGrupoCuenta.ids),
                                                    ('move_id.state', '=', 'posted'),
                                                    ('date', '>=', self.start_date),
                                                    ('date', '<=', self.end_date),
                                                    ('balance', '!=', 0),
                                                    ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
                                                if x_balance != 0:
                                                    a_imprimir.append([])
                                                    a_imprimir[x_altura].append(x_NivelI.code_prefix_start)
                                                    a_imprimir[x_altura].append(x_NivelII.code_prefix_start)
                                                    a_imprimir[x_altura].append('nivel_gc')
                                                    a_imprimir[x_altura].append(x_NivelGrupoCuenta.code_prefix_start)
                                                    a_imprimir[x_altura].append(x_NivelGrupoCuenta.name)

                                                    if x_NivelI.code_prefix_start == '4':  # 4 Ingresos
                                                        a_imprimir[x_altura].append(x_balance * -1)
                                                    else:
                                                        a_imprimir[x_altura].append(x_balance)
                                                    a_imprimir[x_altura].append(0)
                                                    x_altura += 1
                                        a_imprimir.append([])
                                        a_imprimir[x_altura].append(x_NivelI.code_prefix_start)
                                        a_imprimir[x_altura].append(x_NivelII.code_prefix_start)
                                        a_imprimir[x_altura].append('foot_nivel_ii')
                                        a_imprimir[x_altura].append('')
                                        a_imprimir[x_altura].append('   Suma ' + x_NivelII.name)
                                        a_imprimir[x_altura].append(0)
                                        x_balance = sum(self.env['account.move.line'].search([
                                            ('account_id.group_id.parent_id.id', 'in', x_NivelII.ids),
                                            ('move_id.state', '=', 'posted'),
                                            ('date', '>=', self.start_date),
                                            ('date', '<=', self.end_date),
                                            ('balance', '!=', 0),
                                            ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
                                        if x_NivelI.code_prefix_start == '4':  # 4 Ingresos
                                            a_imprimir[x_altura].append(x_balance * -1)
                                        else:
                                            a_imprimir[x_altura].append(x_balance)
                                        x_altura += 1
                        a_imprimir.append([])
                        a_imprimir[x_altura].append(x_NivelI.code_prefix_start)
                        a_imprimir[x_altura].append(x_NivelII.code_prefix_start)
                        a_imprimir[x_altura].append('foot_nivel_i')
                        a_imprimir[x_altura].append('')
                        a_imprimir[x_altura].append('   TOTAL DE ' + x_NivelI.name)
                        a_imprimir[x_altura].append(0)
                        x_balance = sum(self.env['account.move.line'].search([
                            ('account_id.group_id.parent_id.parent_id.id', 'in', x_NivelI.ids),
                            ('move_id.state', '=', 'posted'),
                            ('date', '>=', self.start_date),
                            ('date', '<=', self.end_date),
                            ('balance', '!=', 0),
                            ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
                        if x_NivelI.code_prefix_start == '4':  # 4 Ingresos
                            a_imprimir[x_altura].append(x_balance * -1)
                        else:
                            a_imprimir[x_altura].append(x_balance)
                        x_altura += 1
            x_NiveliInicial += 1
        if a_imprimir:
            while x_recorre < len(a_imprimir):
                x_iteracion += 1
                if x_ctrl_nivel_i == a_imprimir[x_recorre][0] and x_ctrl_nivel_ii == a_imprimir[x_recorre][1]:
                    x_suma_debe += float(a_imprimir[x_recorre][5])
                    x_suma_haber += float(a_imprimir[x_recorre][6])
                elif x_ctrl_nivel_i == a_imprimir[x_recorre][0] and x_ctrl_nivel_ii != a_imprimir[x_recorre][1]:
                    x_suma_debe = 0
                    x_suma_haber += float(a_imprimir[x_recorre][6])
                else:
                    x_suma_debe = 0
                    x_suma_haber = 0
                x_ctrl_nivel_i = a_imprimir[x_recorre][0]
                x_ctrl_nivel_ii = a_imprimir[x_recorre][1]

                if x_row_page < x_max_rows:  # Estamos en ciclo
                    # ---------------------------- Encabezado ----------------------------------------------------------
                    if x_row_page == 0:  # Nueva pagina

                        worksheet.write(x_rows, 3, "Folio: " + str(self.folio + x_page), frmt_folio)

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3, self.company_id.name,
                                              frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3, "NIT: " + self.company_id.partner_id.vat,
                                              frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3, "Costo de Ventas", frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3,
                                              str("Del " + str(self.start_date.day) + " de " + thMes + " de " + str(
                                                  self.start_date.year) + " Al " + str(
                                                  self.end_date.day) + " de " + thMesa + " de " + str(
                                                  self.end_date.year)), frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3, "(EXPRESADO EN QUETZALES)",
                                              frmt_encabezado)  # Encabezado
                        # Aca es solo para cerrar el marco
                        x_rows += 1
                        x_row_page += 1
                        worksheet.write(x_rows, 0, '', frmt_borde_superior)
                        worksheet.write(x_rows, 1, '', frmt_borde_superior)
                        worksheet.write(x_rows, 2, '', frmt_borde_superior)
                        worksheet.write(x_rows, 3, '', frmt_borde_superior)

                        x_rows += 1
                        x_row_page += 1
                        if a_imprimir[x_recorre][2] == 'head_nivel_i' or a_imprimir[x_recorre][2] == 'head_nivel_ii':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)

                            if a_imprimir[x_recorre][2] == 'head_nivel_ii' and a_imprimir[x_recorre][3] == '501':
                                worksheet.write(x_rows, 2, '', debe_haber_nivel_ii)
                                worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber_nivel_ii)
                            else:
                                worksheet.write(x_rows, 2, '', debe_haber_vacio)
                                worksheet.write(x_rows, 3, '', debe_haber_vacio)
                        elif a_imprimir[x_recorre][2] == 'nivel_gc':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][5], debe_haber)
                            worksheet.write(x_rows, 3, '', debe_haber)
                        elif a_imprimir[x_recorre][2] == 'foot_nivel_ii':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber_nivel_ii)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber_nivel_ii)
                        elif a_imprimir[x_recorre][2] == 'foot_nivel_i':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber_nivel_i)
                        elif a_imprimir[x_recorre][2] == 'utilidad_ejercicio': # utilidad ejercicio
                            worksheet.write(x_rows, 0, '', frmt_codigo_utilidad_ejercicio)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_utilidad_ejercicio)
                            worksheet.write(x_rows, 2, '', debe_utilidad_ejercicio)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], haber_utilidad_ejercicio)
                        else: # utilidad bruta
                            worksheet.write(x_rows, 0, '', frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber)

                    # ---------------------------- Fin Encabezado ----------------------------------------------------------
                    elif x_row_page > 0 and x_row_page == x_max_rows - 1:  # Estamos en la penultima linea

                        x_rows += 1
                        x_row_page = 0
                        worksheet.write(x_rows, 0, '', frmt_van_vacio)
                        worksheet.write(x_rows, 1, 'VAN', frmt_van)
                        worksheet.write(x_rows, 2, float(x_suma_debe), debe_haber_van_vienen)
                        worksheet.write(x_rows, 3, float(x_suma_haber), debe_haber_van_vienen)
                        # Encabezado 1

                        x_rows += 1
                        x_row_page += 1
                        x_page += 1
                        worksheet.write(x_rows, 3, "Folio: " + str(self.folio + x_page), frmt_folio)

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3, self.company_id.name,
                                              frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3, "NIT: " + self.company_id.partner_id.vat,
                                              frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3, "Costo de Ventas",
                                              frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3,
                                              str("Del " + str(self.start_date.day) + " de " + thMes + " de " + str(
                                                  self.start_date.year) + " Al " + str(
                                                  self.end_date.day) + " de " + thMesa + " de " + str(
                                                  self.end_date.year)), frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3, "(EXPRESADO EN QUETZALES)",
                                              frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.write(x_rows, 0, '', frmt_borde_superior)
                        worksheet.write(x_rows, 1, '', frmt_borde_superior)
                        worksheet.write(x_rows, 2, '', frmt_borde_superior)
                        worksheet.write(x_rows, 3, '', frmt_borde_superior)

                        x_rows += 1
                        x_row_page += 1
                        worksheet.write(x_rows, 0, '', frmt_van_vacio)
                        worksheet.write(x_rows, 1, 'VIENEN', frmt_van)
                        worksheet.write(x_rows, 2, float(x_suma_debe), debe_haber_van_vienen)
                        worksheet.write(x_rows, 3, float(x_suma_haber), debe_haber_van_vienen)

                        x_rows += 1
                        x_row_page += 1
                        if a_imprimir[x_recorre][2] == 'head_nivel_i' or a_imprimir[x_recorre][2] == 'head_nivel_ii':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            if a_imprimir[x_recorre][2] == 'head_nivel_ii' and a_imprimir[x_recorre][3] == '501':
                                worksheet.write(x_rows, 2, '', debe_haber_nivel_ii)
                                worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber_nivel_ii)
                            else:
                                worksheet.write(x_rows, 2, '', debe_haber_vacio)
                                worksheet.write(x_rows, 3, '', debe_haber_vacio)
                        elif a_imprimir[x_recorre][2] == 'nivel_gc':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][5], debe_haber)
                            worksheet.write(x_rows, 3, '', debe_haber)
                        elif a_imprimir[x_recorre][2] == 'foot_nivel_ii':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber_nivel_ii)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber_nivel_ii)
                        elif a_imprimir[x_recorre][2] == 'foot_nivel_i':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber_nivel_i)
                        elif a_imprimir[x_recorre][2] == 'utilidad_ejercicio':  # utilidad ejercicio
                            worksheet.write(x_rows, 0, '', frmt_codigo_utilidad_ejercicio)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_utilidad_ejercicio)
                            worksheet.write(x_rows, 2, '', debe_utilidad_ejercicio)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], haber_utilidad_ejercicio)
                        else:  # utilidad bruta
                            worksheet.write(x_rows, 0, '', frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber)

                    else:  # No estamos en la ultima linea, estamos en la misma cuenta
                        x_rows += 1
                        x_row_page += 1
                        if a_imprimir[x_recorre][2] == 'head_nivel_i' or a_imprimir[x_recorre][2] == 'head_nivel_ii':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            if a_imprimir[x_recorre][2] == 'head_nivel_ii' and a_imprimir[x_recorre][3] == '501':
                                worksheet.write(x_rows, 2, '', debe_haber_nivel_ii)
                                worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber_nivel_ii)
                            else:
                                worksheet.write(x_rows, 2, '', debe_haber_vacio)
                                worksheet.write(x_rows, 3, '', debe_haber_vacio)
                        elif a_imprimir[x_recorre][2] == 'nivel_gc':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][5], debe_haber)
                            worksheet.write(x_rows, 3, '', debe_haber)
                        elif a_imprimir[x_recorre][2] == 'foot_nivel_ii':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber_nivel_ii)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber_nivel_ii)
                        elif a_imprimir[x_recorre][2] == 'foot_nivel_i':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber_nivel_i)
                        elif a_imprimir[x_recorre][2] == 'utilidad_ejercicio':  # utilidad ejercicio
                            worksheet.write(x_rows, 0, '', frmt_codigo_utilidad_ejercicio)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_utilidad_ejercicio)
                            worksheet.write(x_rows, 2, '', debe_utilidad_ejercicio)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], haber_utilidad_ejercicio)
                        else:  # utilidad bruta
                            worksheet.write(x_rows, 0, '', frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber)
                x_recorre += 1
            certifica = str(self.certificacion)
            text1 = '______________________' \
                   '\n'+self.representante +\
                '\nRepresentante Legal'
            text2 = '______________________' \
                    '\n'+self.contador + \
                    '\nContador'
            options1 = {
                'width': 205,
                'height': 100,
                'x_offset': 0,
                'y_offset': 0,

                'font': {'color': 'black',
                         'font': 'Arial',
                         'size': 10,
                         'bold': True,
                         },
                'align': {'vertical': 'bottom',
                          'horizontal': 'center'
                          },

            }
            options2 = {
                'width': 205,
                'height': 100,
                'x_offset': 0,
                'y_offset': 0,

                'font': {'color': 'black',
                         'font': 'Arial',
                         'size': 10,
                         'bold': True,
                         },
                'align': {'vertical': 'bottom',
                          'horizontal': 'center'
                          },

            }
            cert_options = {
                'width': 615,
                'height': 100,
                'x_offset': 0,
                'y_offset': 0,

                'font': {'color': 'black',
                         'font': 'Arial',
                         'size': 10,
                         'bold': True,
                         },
                'align': {'vertical': 'top',
                          'horizontal': 'left'
                          },

            }
            cell = xl_rowcol_to_cell(x_rows+2, 0)
            worksheet.insert_textbox(cell, certifica, cert_options)
            cell = xl_rowcol_to_cell(x_rows + 7, 0)
            worksheet.insert_textbox(cell, text1, options1)
            cell = xl_rowcol_to_cell(x_rows + 7, 2)
            worksheet.insert_textbox(cell, text2, options2)

        else:
            if x_row_page == 0:  # Nueva pagina
                worksheet.write(x_rows, 3, "Folio: " + str(self.folio + x_page), frmt_folio)
                x_rows += 1
                x_row_page += 1
                worksheet.merge_range(x_rows, 0, x_rows, 3, self.company_id.name,
                                      frmt_encabezado)  # Encabezado
                x_rows += 1
                x_row_page += 1
                worksheet.merge_range(x_rows, 0, x_rows, 3, "NIT: " + self.company_id.partner_id.vat,
                                      frmt_encabezado)  # Encabezado
                x_rows += 1
                x_row_page += 1
                worksheet.merge_range(x_rows, 0, x_rows, 3, "Costo de Ventas", frmt_encabezado)  # Encabezado
                x_rows += 1
                x_row_page += 1
                worksheet.merge_range(x_rows, 0, x_rows, 3,
                                      str("Del " + str(self.start_date.day) + " de " + thMes + " de " + str(
                                          self.start_date.year) + " Al " + str(
                                          self.end_date.day) + " de " + thMesa + " de " + str(
                                          self.end_date.year)), frmt_encabezado)  # Encabezado

                x_rows += 1
                x_row_page += 1
                worksheet.merge_range(x_rows, 0, x_rows, 3, "(EXPRESADO EN QUETZALES)",
                                      frmt_encabezado)  # Encabezado
                # Aca es solo para cerrar el marco
                x_rows += 1
                x_row_page += 1
                worksheet.write(x_rows, 0, '', frmt_borde_superior)
                worksheet.write(x_rows, 1, '', frmt_borde_superior)
                worksheet.write(x_rows, 2, '', frmt_borde_superior)
                worksheet.write(x_rows, 3, '', frmt_borde_superior)

                x_rows += 1
                x_row_page += 1
                worksheet.write(x_rows, 0, "5", frmt_codigo)
                worksheet.write(x_rows, 1, "COSTO DE VENTAS", frmt_cuenta_head_foot)

                x_rows += 1
                x_row_page += 1
                worksheet.write(x_rows, 0, "501", frmt_codigo)
                worksheet.write(x_rows, 1, "COSTO DE PRODUCCION", frmt_cuenta_head_foot)
                worksheet.write(x_rows, 2, "", debe_haber_nivel_ii)
                worksheet.write(x_rows, 3, 0, debe_haber_nivel_ii)

                x_rows += 1
                x_row_page += 1
                worksheet.write(x_rows, 0, "", frmt_codigo)
                worksheet.write(x_rows, 1, "TOTAL DE COSTOS", frmt_cuenta_head_foot)
                worksheet.write(x_rows, 2, "", debe_haber_nivel_ii)
                worksheet.write(x_rows, 3, 0, debe_haber_nivel_ii)

                x_recorre += 1
                certifica = str(self.certificacion)
                text1 = '______________________' \
                        '\n' + self.representante + \
                        '\nRepresentante Legal'
                text2 = '______________________' \
                        '\n' + self.contador + \
                        '\nContador'
                options1 = {
                    'width': 205,
                    'height': 100,
                    'x_offset': 0,
                    'y_offset': 0,

                    'font': {'color': 'black',
                             'font': 'Arial',
                             'size': 10,
                             'bold': True,
                             },
                    'align': {'vertical': 'bottom',
                              'horizontal': 'center'
                              },

                }
                options2 = {
                    'width': 205,
                    'height': 100,
                    'x_offset': 0,
                    'y_offset': 0,

                    'font': {'color': 'black',
                             'font': 'Arial',
                             'size': 10,
                             'bold': True,
                             },
                    'align': {'vertical': 'bottom',
                              'horizontal': 'center'
                              },

                }
                cert_options = {
                    'width': 615,
                    'height': 100,
                    'x_offset': 0,
                    'y_offset': 0,

                    'font': {'color': 'black',
                             'font': 'Arial',
                             'size': 10,
                             'bold': True,
                             },
                    'align': {'vertical': 'top',
                              'horizontal': 'left'
                              },

                }
                cell = xl_rowcol_to_cell(x_rows + 2, 0)
                worksheet.insert_textbox(cell, certifica, cert_options)
                cell = xl_rowcol_to_cell(x_rows + 7, 0)
                worksheet.insert_textbox(cell, text1, options1)
                cell = xl_rowcol_to_cell(x_rows + 7, 2)
                worksheet.insert_textbox(cell, text2, options2)


        workbook.close()
        self.write({
            'state': 'get',
            'data': base64.b64encode(open(xls_path, 'rb').read()),
            'name': xls_filename
        })
        return {
            'name': 'Costo de Producción',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new'
        }

class wizard_costo_produccion(models.TransientModel):
    _name = 'wizard.costo.produccion'
    _description = "Wizard Costo de Produccion"
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id)
    start_date = fields.Date(string="Fecha Inicio")
    end_date = fields.Date(string="Fecha Fin")

    anio = fields.Integer(string="Año")
    mes_de = fields.Selection([('1', 'Enero'), ('2', 'Febrero'), ('3', 'Marzo'), ('4', 'Abril'), ('5', 'Mayo'), ('6', 'Junio'), ('7', 'Julio'), ('8', 'Agosto'), ('9', 'Septiembre'), ('10', 'Octubre'), ('11', 'Noviembre'), ('12', 'Diciembre')], string="De")
    mes_a = fields.Selection(
        [('1', 'Enero'), ('2', 'Febrero'), ('3', 'Marzo'), ('4', 'Abril'), ('5', 'Mayo'), ('6', 'Junio'),
         ('7', 'Julio'), ('8', 'Agosto'), ('9', 'Septiembre'), ('10', 'Octubre'), ('11', 'Noviembre'),
         ('12', 'Diciembre')], string="A")
    folio = fields.Integer(string="Folio")
    certificacion = fields.Char(string="Certificación")
    representante = fields.Char(string="Representante Legal")
    contador = fields.Char(string="Contador")
    filter_by = fields.Selection([('product', 'Product'), ('category', 'Category')], string="Filter By")
    group_by_categ = fields.Boolean(string="Group By Category")
    state = fields.Selection([('choose', 'choose'), ('get', 'get')], default='choose')
    name = fields.Char(string='File Name', readonly=True)
    data = fields.Binary(string='File', readonly=True)
    product_ids = fields.Many2many('product.product', string="Products")
    category_ids = fields.Many2many('product.category', string="Categories")
    # Columnas para el reporte

    @api.onchange('company_id')
    def onchange_company_id(self):
        domain = [('id', 'in', self.env.user.company_ids.ids)]
        # if self.company_id:
            # self.warehouse_ids = False
            # self.location_ids = False
        return {'domain' : {'company_id' : domain}}

    def check_date_range(self):
        if self.end_date < self.start_date:
            raise ValidationError(_('Fecha fin ser posterior a fecha inicio.'))

    def check_mes(self):
        if int(self.mes_de) > int(self.mes_a):
            raise ValidationError(_('Mes De debe ser anterior a mes A.'))

    @api.onchange('filter_by')
    def onchange_filter_by(self):
        self.product_ids = False
        self.category_ids = False

    def print_report(self):
        self.check_date_range()
        datas = {'form':
                    {
                        'company_id': self.company_id.id,
                        'warehouse_ids': [y.id for y in self.warehouse_ids],
                        'location_ids': self.location_ids.ids or False,
                        'start_date': self.start_date,
                        'end_date': self.end_date,
                        'id': self.id,
                        'product_ids': self.product_ids.ids,
                        'product_categ_ids': self.category_ids.ids
                    },
                }
        return self.env.ref('account_report_financial.action_report_financial_template').report_action(self, data=datas)

    def go_back(self):
        self.state = 'choose'
        return {
            'name': 'Costo de Produccion',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new'
        }

    def print_xls_costo_produccion(self):

        thMes = ""
        thMesa = ""
        if self.start_date.month == 1:
            thMes = "Enero"
        elif self.start_date.month == 2:
            thMes = "Febrero"
        elif self.start_date.month == 3:
            thMes = "Marzo"
        elif self.start_date.month == 4:
            thMes = "Abril"
        elif self.start_date.month == 5:
            thMes = "Mayo"
        elif self.start_date.month == 6:
            thMes = "Junio"
        elif self.start_date.month == 7:
            thMes = "Julio"
        elif self.start_date.month == 8:
            thMes = "Agosto"
        elif self.start_date.month == 9:
            thMes = "Septiembre"
        elif self.start_date.month == 10:
            thMes = "Octubre"
        elif self.start_date.month == 11:
            thMes = "Noviembre"
        else:
            thMes = "Diciembre"

        if self.end_date.month == 1:
            thMesa = "Enero"
        elif self.end_date.month == 2:
            thMesa = "Febrero"
        elif self.end_date.month == 3:
            thMesa = "Marzo"
        elif self.end_date.month == 4:
            thMesa = "Abril"
        elif self.end_date.month == 5:
            thMesa = "Mayo"
        elif self.end_date.month == 6:
            thMesa = "Junio"
        elif self.end_date.month == 7:
            thMesa = "Julio"
        elif self.end_date.month == 8:
            thMesa = "Agosto"
        elif self.end_date.month == 9:
            thMesa = "Septiembre"
        elif self.end_date.month == 10:
            thMesa = "Octubre"
        elif self.end_date.month == 11:
            thMesa = "Noviembre"
        else:
            thMesa = "Diciembre"

        self.check_date_range()
        #self.check_mes()
        #company_id = self.env['res.company'].browse(self._context.get('allowed_company_ids'))
        xls_filename = 'Costo de Produccion.xlsx'
        temp_dir = tempfile.gettempdir()
        xls_path = os.path.join(temp_dir, xls_filename)
        workbook = xlsxwriter.Workbook(xls_path)

        frmt_folio = workbook.add_format({'bold': False, 'align': 'right', \
                                          'font': 'Arial', 'font_size': 10})
        frmt_encabezado = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                               'font': 'Arial', 'font_size': 10})
        frmt_borde_superior = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                                   'font': 'Arial', 'font_size': 10})
        frmt_cuenta_head_foot = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 10, 'bold' : True})
        frmt_cuenta = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 10})
        frmt_van_vacio = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 10, 'border': 1})
        frmt_codigo = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'bold': True})
        frmt_codigo_utilidad_ejercicio = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'bold': True})
        frmt_utilidad_ejercicio = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 10, 'bold': True})
        debe_utilidad_ejercicio = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'border': 1, 'bold': True, 'num_format': 'Q#,##0.00'})
        haber_utilidad_ejercicio = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'border': 1, 'bold': True, 'num_format': 'Q#,##0.00'})
        debe_haber_vacio = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10})
        debe_haber = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'border':1, 'num_format': 'Q#,##0.00'})
        debe_haber_nivel_ii = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'border' : 1, 'num_format': 'Q#,##0.00'})
        debe_haber_nivel_i = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'bold' : True, 'num_format': 'Q#,##0.00'})
        debe_haber_van_vienen = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'bold' : True, 'border' : 1, 'num_format': 'Q#,##0.00'})

        frmt_van = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                                      'font': 'Arial', 'font_size': 10, 'num_format': 'Q#,##0.00'})
        frmt_firma = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                               'font': 'Arial', 'font_size': 10})
        frmt_codigo_utilidad_ejercicio.set_bottom(1)
        frmt_codigo_utilidad_ejercicio.set_left(1)
        frmt_utilidad_ejercicio.set_bottom(1)
        haber_utilidad_ejercicio.set_bottom(6)

        frmt_borde_superior.set_bottom(1)

        frmt_codigo.set_left(1)

        frmt_cuenta.set_right(1)
        frmt_cuenta_head_foot.set_right(1)

        debe_haber_vacio.set_left(1)
        debe_haber_vacio.set_right(1)

        debe_haber_nivel_i.set_right(1)
        debe_haber_nivel_i.set_left(1)
        debe_haber_nivel_i.set_bottom(6)

        worksheet = workbook.add_worksheet("Costo de Ventas")
        worksheet.set_portrait()
        worksheet.set_page_view()
        worksheet.set_paper(1)
        worksheet.set_margins(0.7,0.7,0.7,0.7)
        # Tamaños
        worksheet.set_column('A:A', 10)
        worksheet.set_column('B:B', 45)
        worksheet.set_column('C:C', 15)
        worksheet.set_column('D:D', 15)
        # Empieza detalle
        x_rows = 0 # Linea a imprimir
        x_page = 0 # Numero de pagina
        x_max_rows = 47 # Maximo de lineas por pagina
        x_row_page = 0 # Linea actual vrs maximo de lineas
        x_ctrl_nivel_i = ''
        x_ctrl_nivel_ii = ''
        x_altura = 0
        x_recorre = 0
        x_suma_debe = 0
        x_suma_haber = 0
        x_iteracion = 0
        x_NiveliInicial = 5 # Aca empezamos desde los ingresos
        x_NiveliFinal = 5
        #x_NiveliFinal = int(self.env['account.group'].search([
         #                                                   ('company_id.id', '=', self.company_id.id),
          #                                                  ('parent_id', '=', False),
           #                                                 ], order="code_prefix_start desc", limit=1).mapped('code_prefix_start')[0])

        a_imprimir = []
        while x_NiveliInicial <= x_NiveliFinal: # Principal ciclo para saber que grupos van a ser tomados en cuenta en este caso 4 ingresos 5 cotos 6 gastos
            # Buscamos el id de grupo de la raiz nivel i
            NivelI = self.env['account.group'].search(
            [('company_id.id', '=', self.company_id.id),
             ('parent_id', '=', False),
             ('code_prefix_start', '=', x_NiveliInicial)],
                order="code_prefix_start asc", limit=1)

            if NivelI:
                for x_NivelI in NivelI:
                    x_control = 0
                    x_control = sum(self.env['account.move.line'].search([
                        ('account_id.group_id.parent_id.parent_id.id', 'in', x_NivelI.ids),
                        ('move_id.state', '=', 'posted'),
                        ('date', '>=', self.start_date),
                        ('date', '<=', self.end_date),
                        ('balance', '!=', 0),
                        ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
                    if x_control != 0:
                        a_imprimir.append([])
                        a_imprimir[x_altura].append(x_NivelI.code_prefix_start)
                        a_imprimir[x_altura].append('')
                        a_imprimir[x_altura].append('head_nivel_i')
                        a_imprimir[x_altura].append(x_NivelI.code_prefix_start)
                        a_imprimir[x_altura].append(x_NivelI.name)
                        a_imprimir[x_altura].append(0)
                        a_imprimir[x_altura].append(0)

                        x_altura += 1
                        # Buscamos el id de grupo del nivel ii que pertenezcan a nivel i
                        NivelII = self.env['account.group'].search([('parent_id.id', 'in', x_NivelI.ids), ('code_prefix_start', '=', '501')],
                                                                   order="code_prefix_start asc")
                        if NivelII:
                            for x_NivelII in NivelII:
                                x_control = 0
                                x_control = sum(self.env['account.move.line'].search([
                                    ('account_id.group_id.parent_id.id', 'in', x_NivelII.ids),
                                    ('move_id.state', '=', 'posted'),
                                    ('date', '>=', self.start_date),
                                    ('date', '<=', self.end_date),
                                    ('balance', '!=', 0),
                                    ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
                                if x_control != 0:
                                    a_imprimir.append([])
                                    a_imprimir[x_altura].append(x_NivelI.code_prefix_start)
                                    a_imprimir[x_altura].append(x_NivelII.code_prefix_start)
                                    a_imprimir[x_altura].append('head_nivel_ii')
                                    a_imprimir[x_altura].append(x_NivelII.code_prefix_start)
                                    a_imprimir[x_altura].append(x_NivelII.name)
                                    a_imprimir[x_altura].append(0)
                                    a_imprimir[x_altura].append(0)
                                    x_altura += 1
                                    # Buscamos el id de grupo de cuenta que pertenezca a nivel ii
                                    NivelGrupoCuenta = self.env['account.group'].search(
                                        [('parent_id.id', 'in', x_NivelII.ids)],
                                        order="code_prefix_start asc")
                                    if NivelGrupoCuenta:
                                        for x_NivelGrupoCuenta in NivelGrupoCuenta:
                                            x_balance = sum(self.env['account.move.line'].search([
                                                ('account_id.group_id.id', 'in', x_NivelGrupoCuenta.ids),
                                                ('move_id.state', '=', 'posted'),
                                                ('date', '>=', self.start_date),
                                                ('date', '<=', self.end_date),
                                                ('balance', '!=', 0),
                                                ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
                                            if x_balance != 0:
                                                a_imprimir.append([])
                                                a_imprimir[x_altura].append(x_NivelI.code_prefix_start)
                                                a_imprimir[x_altura].append(x_NivelII.code_prefix_start)
                                                a_imprimir[x_altura].append('nivel_gc')
                                                a_imprimir[x_altura].append(x_NivelGrupoCuenta.code_prefix_start)
                                                a_imprimir[x_altura].append(x_NivelGrupoCuenta.name)

                                                if x_NivelI.code_prefix_start == '4':  # 4 Ingresos
                                                    a_imprimir[x_altura].append(x_balance * -1)
                                                else:
                                                    a_imprimir[x_altura].append(x_balance)
                                                a_imprimir[x_altura].append(0)
                                                x_altura += 1
                                    a_imprimir.append([])
                                    a_imprimir[x_altura].append(x_NivelI.code_prefix_start)
                                    a_imprimir[x_altura].append(x_NivelII.code_prefix_start)
                                    a_imprimir[x_altura].append('foot_nivel_ii')
                                    a_imprimir[x_altura].append('')
                                    a_imprimir[x_altura].append('   Suma ' + x_NivelII.name)
                                    a_imprimir[x_altura].append(0)
                                    x_balance = sum(self.env['account.move.line'].search([
                                        ('account_id.group_id.parent_id.id', 'in', x_NivelII.ids),
                                        ('move_id.state', '=', 'posted'),
                                        ('date', '>=', self.start_date),
                                        ('date', '<=', self.end_date),
                                        ('balance', '!=', 0),
                                        ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
                                    if x_NivelI.code_prefix_start == '4':  # 4 Ingresos
                                        a_imprimir[x_altura].append(x_balance * -1)
                                    else:
                                        a_imprimir[x_altura].append(x_balance)
                                    x_altura += 1
                        a_imprimir.append([])
                        a_imprimir[x_altura].append(x_NivelI.code_prefix_start)
                        a_imprimir[x_altura].append(x_NivelII.code_prefix_start)
                        a_imprimir[x_altura].append('foot_nivel_i')
                        a_imprimir[x_altura].append('')
                        a_imprimir[x_altura].append('   TOTAL DE ' + x_NivelI.name)
                        a_imprimir[x_altura].append(0)
                        x_balance = sum(self.env['account.move.line'].search([
                            ('account_id.group_id.parent_id.parent_id.id', 'in', x_NivelI.ids),
                            ('move_id.state', '=', 'posted'),
                            ('date', '>=', self.start_date),
                            ('date', '<=', self.end_date),
                            ('balance', '!=', 0),
                            ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
                        if x_NivelI.code_prefix_start == '4':  # 4 Ingresos
                            a_imprimir[x_altura].append(x_balance * -1)
                        else:
                            a_imprimir[x_altura].append(x_balance)
                        x_altura += 1
            x_NiveliInicial += 1
        if a_imprimir:
            while x_recorre < len(a_imprimir):
                x_iteracion += 1
                if x_ctrl_nivel_i == a_imprimir[x_recorre][0] and x_ctrl_nivel_ii == a_imprimir[x_recorre][1]:
                    x_suma_debe += float(a_imprimir[x_recorre][5])
                    x_suma_haber += float(a_imprimir[x_recorre][6])
                elif x_ctrl_nivel_i == a_imprimir[x_recorre][0] and x_ctrl_nivel_ii != a_imprimir[x_recorre][1]:
                    x_suma_debe = 0
                    x_suma_haber += float(a_imprimir[x_recorre][6])
                else:
                    x_suma_debe = 0
                    x_suma_haber = 0
                x_ctrl_nivel_i = a_imprimir[x_recorre][0]
                x_ctrl_nivel_ii = a_imprimir[x_recorre][1]

                if x_row_page < x_max_rows:  # Estamos en ciclo
                    # ---------------------------- Encabezado ----------------------------------------------------------
                    if x_row_page == 0:  # Nueva pagina

                        worksheet.write(x_rows, 3, "Folio: " + str(self.folio + x_page), frmt_folio)

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3, self.company_id.name,
                                              frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3, "NIT: " + self.company_id.partner_id.vat,
                                              frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3, "Costo de Producción", frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3,
                                              str("Del " + str(self.start_date.day) + " de " + thMes + " de " + str(
                                                  self.start_date.year) + " Al " + str(
                                                  self.end_date.day) + " de " + thMesa + " de " + str(
                                                  self.end_date.year)), frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3, "(EXPRESADO EN QUETZALES)",
                                              frmt_encabezado)  # Encabezado
                        # Aca es solo para cerrar el marco
                        x_rows += 1
                        x_row_page += 1
                        worksheet.write(x_rows, 0, '', frmt_borde_superior)
                        worksheet.write(x_rows, 1, '', frmt_borde_superior)
                        worksheet.write(x_rows, 2, '', frmt_borde_superior)
                        worksheet.write(x_rows, 3, '', frmt_borde_superior)

                        x_rows += 1
                        x_row_page += 1
                        if a_imprimir[x_recorre][2] == 'head_nivel_i' or a_imprimir[x_recorre][2] == 'head_nivel_ii':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber_vacio)
                            worksheet.write(x_rows, 3, '', debe_haber_vacio)
                        elif a_imprimir[x_recorre][2] == 'nivel_gc':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][5], debe_haber)
                            worksheet.write(x_rows, 3, '', debe_haber)
                        elif a_imprimir[x_recorre][2] == 'foot_nivel_ii':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber_nivel_ii)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber_nivel_ii)
                        elif a_imprimir[x_recorre][2] == 'foot_nivel_i':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber_nivel_i)
                        elif a_imprimir[x_recorre][2] == 'utilidad_ejercicio': # utilidad ejercicio
                            worksheet.write(x_rows, 0, '', frmt_codigo_utilidad_ejercicio)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_utilidad_ejercicio)
                            worksheet.write(x_rows, 2, '', debe_utilidad_ejercicio)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], haber_utilidad_ejercicio)
                        else: # utilidad bruta
                            worksheet.write(x_rows, 0, '', frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber)

                    # ---------------------------- Fin Encabezado ----------------------------------------------------------
                    elif x_row_page > 0 and x_row_page == x_max_rows - 1:  # Estamos en la penultima linea

                        x_rows += 1
                        x_row_page = 0
                        worksheet.write(x_rows, 0, '', frmt_van_vacio)
                        worksheet.write(x_rows, 1, 'VAN', frmt_van)
                        worksheet.write(x_rows, 2, float(x_suma_debe), debe_haber_van_vienen)
                        worksheet.write(x_rows, 3, float(x_suma_haber), debe_haber_van_vienen)
                        # Encabezado 1

                        x_rows += 1
                        x_row_page += 1
                        x_page += 1
                        worksheet.write(x_rows, 3, "Folio: " + str(self.folio + x_page), frmt_folio)

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3, self.company_id.name,
                                              frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3, "NIT: " + self.company_id.partner_id.vat,
                                              frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3, "Costo de Producción",
                                              frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3,
                                              str("Del " + str(self.start_date.day) + " de " + thMes + " de " + str(
                                                  self.start_date.year) + " Al " + str(
                                                  self.end_date.day) + " de " + thMesa + " de " + str(
                                                  self.end_date.year)), frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 3, "(EXPRESADO EN QUETZALES)",
                                              frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.write(x_rows, 0, '', frmt_borde_superior)
                        worksheet.write(x_rows, 1, '', frmt_borde_superior)
                        worksheet.write(x_rows, 2, '', frmt_borde_superior)
                        worksheet.write(x_rows, 3, '', frmt_borde_superior)

                        x_rows += 1
                        x_row_page += 1
                        worksheet.write(x_rows, 0, '', frmt_van_vacio)
                        worksheet.write(x_rows, 1, 'VIENEN', frmt_van)
                        worksheet.write(x_rows, 2, float(x_suma_debe), debe_haber_van_vienen)
                        worksheet.write(x_rows, 3, float(x_suma_haber), debe_haber_van_vienen)

                        x_rows += 1
                        x_row_page += 1
                        if a_imprimir[x_recorre][2] == 'head_nivel_i' or a_imprimir[x_recorre][2] == 'head_nivel_ii':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber_vacio)
                            worksheet.write(x_rows, 3, '', debe_haber_vacio)
                        elif a_imprimir[x_recorre][2] == 'nivel_gc':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][5], debe_haber)
                            worksheet.write(x_rows, 3, '', debe_haber)
                        elif a_imprimir[x_recorre][2] == 'foot_nivel_ii':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber_nivel_ii)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber_nivel_ii)
                        elif a_imprimir[x_recorre][2] == 'foot_nivel_i':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber_nivel_i)
                        elif a_imprimir[x_recorre][2] == 'utilidad_ejercicio':  # utilidad ejercicio
                            worksheet.write(x_rows, 0, '', frmt_codigo_utilidad_ejercicio)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_utilidad_ejercicio)
                            worksheet.write(x_rows, 2, '', debe_utilidad_ejercicio)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], haber_utilidad_ejercicio)
                        else:  # utilidad bruta
                            worksheet.write(x_rows, 0, '', frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber)

                    else:  # No estamos en la ultima linea, estamos en la misma cuenta
                        x_rows += 1
                        x_row_page += 1
                        if a_imprimir[x_recorre][2] == 'head_nivel_i' or a_imprimir[x_recorre][2] == 'head_nivel_ii':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber_vacio)
                            worksheet.write(x_rows, 3, '', debe_haber_vacio)
                        elif a_imprimir[x_recorre][2] == 'nivel_gc':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][5], debe_haber)
                            worksheet.write(x_rows, 3, '', debe_haber)
                        elif a_imprimir[x_recorre][2] == 'foot_nivel_ii':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber_nivel_ii)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber_nivel_ii)
                        elif a_imprimir[x_recorre][2] == 'foot_nivel_i':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber_nivel_i)
                        elif a_imprimir[x_recorre][2] == 'utilidad_ejercicio':  # utilidad ejercicio
                            worksheet.write(x_rows, 0, '', frmt_codigo_utilidad_ejercicio)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_utilidad_ejercicio)
                            worksheet.write(x_rows, 2, '', debe_utilidad_ejercicio)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], haber_utilidad_ejercicio)
                        else:  # utilidad bruta
                            worksheet.write(x_rows, 0, '', frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber)

                x_recorre += 1
            certifica = str(self.certificacion)
            text1 = '______________________' \
                   '\n'+self.representante +\
                '\nRepresentante Legal'
            text2 = '______________________' \
                    '\n'+self.contador + \
                    '\nContador'

            options1 = {
                'width': 205,
                'height': 100,
                'x_offset': 0,
                'y_offset': 0,

                'font': {'color': 'black',
                         'font': 'Arial',
                         'size': 10,
                         'bold': True,
                         },
                'align': {'vertical': 'bottom',
                          'horizontal': 'center'
                          },

            }
            options2 = {
                'width': 205,
                'height': 100,
                'x_offset': 0,
                'y_offset': 0,

                'font': {'color': 'black',
                         'font': 'Arial',
                         'size': 10,
                         'bold': True,
                         },
                'align': {'vertical': 'bottom',
                          'horizontal': 'center'
                          },

            }
            cert_options = {
                'width': 615,
                'height': 100,
                'x_offset': 0,
                'y_offset': 0,

                'font': {'color': 'black',
                         'font': 'Arial',
                         'size': 10,
                         'bold': True,
                         },
                'align': {'vertical': 'top',
                          'horizontal': 'left'
                          },

            }
            cell = xl_rowcol_to_cell(x_rows+2, 0)
            worksheet.insert_textbox(cell, certifica, cert_options)
            cell = xl_rowcol_to_cell(x_rows + 7, 0)
            worksheet.insert_textbox(cell, text1, options1)
            cell = xl_rowcol_to_cell(x_rows + 7, 2)
            worksheet.insert_textbox(cell, text2, options2)


        else:
            if x_row_page == 0:  # Nueva pagina

                worksheet.write(x_rows, 3, "Folio: " + str(self.folio + x_page), frmt_folio)

                x_rows += 1
                x_row_page += 1
                worksheet.merge_range(x_rows, 0, x_rows, 3, self.company_id.name,
                                      frmt_encabezado)  # Encabezado

                x_rows += 1
                x_row_page += 1
                worksheet.merge_range(x_rows, 0, x_rows, 3, "NIT: " + self.company_id.partner_id.vat,
                                      frmt_encabezado)  # Encabezado

                x_rows += 1
                x_row_page += 1
                worksheet.merge_range(x_rows, 0, x_rows, 3, "Costo de Producción", frmt_encabezado)  # Encabezado

                x_rows += 1
                x_row_page += 1
                worksheet.merge_range(x_rows, 0, x_rows, 3,
                                      str("Del " + str(self.start_date.day) + " de " + thMes + " de " + str(
                                          self.start_date.year) + " Al " + str(
                                          self.end_date.day) + " de " + thMesa + " de " + str(
                                          self.end_date.year)), frmt_encabezado)  # Encabezado

                x_rows += 1
                x_row_page += 1
                worksheet.merge_range(x_rows, 0, x_rows, 3, "(EXPRESADO EN QUETZALES)",
                                      frmt_encabezado)  # Encabezado
                # Aca es solo para cerrar el marco
                x_rows += 1
                x_row_page += 1
                worksheet.write(x_rows, 0, '', frmt_borde_superior)
                worksheet.write(x_rows, 1, '', frmt_borde_superior)
                worksheet.write(x_rows, 2, '', frmt_borde_superior)
                worksheet.write(x_rows, 3, '', frmt_borde_superior)

                x_rows += 1
                x_row_page += 1

                worksheet.write(x_rows, 0, "5", frmt_codigo)
                worksheet.write(x_rows, 1, "COSTO DE VENTAS", frmt_cuenta_head_foot)

                x_rows += 1
                x_row_page += 1
                worksheet.write(x_rows, 0, "501", frmt_codigo)
                worksheet.write(x_rows, 1, "COSTO DE PRODUCCION", frmt_cuenta_head_foot)
                worksheet.write(x_rows, 2, "", debe_haber_nivel_ii)
                worksheet.write(x_rows, 3, 0, debe_haber_nivel_ii)

                x_rows += 1
                x_row_page += 1
                worksheet.write(x_rows, 0, "", frmt_codigo)
                worksheet.write(x_rows, 1, "TOTAL DE COSTOS", frmt_cuenta_head_foot)
                worksheet.write(x_rows, 2, "", debe_haber_nivel_ii)
                worksheet.write(x_rows, 3, 0, debe_haber_nivel_ii)

                x_recorre += 1

                certifica = str(self.certificacion)
                text1 = '______________________' \
                        '\n' + self.representante + \
                        '\nRepresentante Legal'
                text2 = '______________________' \
                        '\n' + self.contador + \
                        '\nContador'

                options1 = {
                    'width': 205,
                    'height': 100,
                    'x_offset': 0,
                    'y_offset': 0,

                    'font': {'color': 'black',
                             'font': 'Arial',
                             'size': 10,
                             'bold': True,
                             },
                    'align': {'vertical': 'bottom',
                              'horizontal': 'center'
                              },

                }
                options2 = {
                    'width': 205,
                    'height': 100,
                    'x_offset': 0,
                    'y_offset': 0,

                    'font': {'color': 'black',
                             'font': 'Arial',
                             'size': 10,
                             'bold': True,
                             },
                    'align': {'vertical': 'bottom',
                              'horizontal': 'center'
                              },

                }
                cert_options = {
                    'width': 615,
                    'height': 100,
                    'x_offset': 0,
                    'y_offset': 0,

                    'font': {'color': 'black',
                             'font': 'Arial',
                             'size': 10,
                             'bold': True,
                             },
                    'align': {'vertical': 'top',
                              'horizontal': 'left'
                              },

                }
                cell = xl_rowcol_to_cell(x_rows + 2, 0)
                worksheet.insert_textbox(cell, certifica, cert_options)
                cell = xl_rowcol_to_cell(x_rows + 7, 0)
                worksheet.insert_textbox(cell, text1, options1)
                cell = xl_rowcol_to_cell(x_rows + 7, 2)
                worksheet.insert_textbox(cell, text2, options2)

        workbook.close()
        self.write({
            'state': 'get',
            'data': base64.b64encode(open(xls_path, 'rb').read()),
            'name': xls_filename
        })
        return {
            'name': 'Costo de Producción',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new'
        }

class wizard_balance_general(models.TransientModel):
    _name = 'wizard.balance.general'
    _description = "Wizard Balance General"
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id)
    end_date = fields.Date(string="Al")
    folio = fields.Integer(string="Folio")
    certificacion = fields.Char(string="Certificación")
    representante = fields.Char(string="Representante Legal")
    contador = fields.Char(string="Contador")
    state = fields.Selection([('choose', 'choose'), ('get', 'get')], default='choose')
    name = fields.Char(string='File Name', readonly=True)
    data = fields.Binary(string='File', readonly=True)

    @api.onchange('company_id')
    def onchange_company_id(self):
        domain = [('id', 'in', self.env.user.company_ids.ids)]
        return {'domain': {'company_id': domain}}

    def go_back(self):
        self.state = 'choose'
        return {
            'name': 'Report Financial Estado Resultados',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new'
        }

    def print_xls_balance_general(self):

        thMes = ""
        if self.end_date.month == 1:
            thMes = "Enero"
        elif self.end_date.month == 2:
            thMes = "Febrero"
        elif self.end_date.month == 3:
            thMes = "Marzo"
        elif self.end_date.month == 4:
            thMes = "Abril"
        elif self.end_date.month == 5:
            thMes = "Mayo"
        elif self.end_date.month == 6:
            thMes = "Junio"
        elif self.end_date.month == 7:
            thMes = "Julio"
        elif self.end_date.month == 8:
            thMes = "Agosto"
        elif self.end_date.month == 9:
            thMes = "Septiembre"
        elif self.end_date.month == 10:
            thMes = "Octubre"
        elif self.end_date.month == 11:
            thMes = "Noviembre"
        else:
            thMes = "Diciembre"

        xls_filename = 'Balance General.xlsx'
        temp_dir = tempfile.gettempdir()
        xls_path = os.path.join(temp_dir, xls_filename)
        workbook = xlsxwriter.Workbook(xls_path)
        frmt_folio = workbook.add_format({'bold': False, 'align': 'right', \
                                          'font': 'Arial', 'font_size': 10})
        frmt_encabezado = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                               'font': 'Arial', 'font_size': 10})
        frmt_borde_superior = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                                   'font': 'Arial', 'font_size': 10})
        frmt_cuenta_head_foot = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 10, 'bold': True})
        frmt_cuenta = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 10})
        frmt_van_vacio = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 10, 'border': 1})
        frmt_codigo = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'bold': True})
        frmt_codigo_c = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10})
        frmt_codigo_utilidad_ejercicio = workbook.add_format(
            {'align': 'right', 'font': 'Arial', 'font_size': 10, 'bold': True})
        frmt_utilidad_ejercicio = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 10, 'bold': True})
        debe_utilidad_ejercicio = workbook.add_format(
            {'align': 'right', 'font': 'Arial', 'font_size': 10, 'border': 1, 'bold': True})
        haber_utilidad_ejercicio = workbook.add_format(
            {'align': 'right', 'font': 'Arial', 'font_size': 10, 'border': 1, 'bold': True, 'num_format': 'Q#,##0.00'})
        debe_haber_vacio = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10})
        debe_haber_vacio_gc = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10})
        debe_haber = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'num_format': 'Q#,##0.00'})
        debe_haber_gc = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'num_format': 'Q#,##0.00'})
        debe_haber_nivel_ii = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'bold': True, 'num_format': 'Q#,##0.00'})
        debe_haber_nivel_i = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'bold': True, 'num_format': 'Q#,##0.00'})
        debe_haber_van_vienen = workbook.add_format(
            {'align': 'right', 'font': 'Arial', 'font_size': 10, 'bold': True, 'border': 1, 'num_format': 'Q#,##0.00'})
        frmt_van = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                        'font': 'Arial', 'font_size': 10, 'border': 1, 'num_format': 'Q#,##0.00'})
        frmt_codigo_utilidad_ejercicio.set_bottom(1)
        frmt_codigo_utilidad_ejercicio.set_left(1)
        frmt_utilidad_ejercicio.set_bottom(1)
        haber_utilidad_ejercicio.set_bottom(6)
        frmt_borde_superior.set_bottom(1)
        frmt_codigo.set_left(1)
        frmt_codigo_c.set_left(1)
        frmt_cuenta.set_right(1)
        frmt_cuenta_head_foot.set_right(1)
        debe_haber.set_right(1)
        debe_haber.set_left(1)
        debe_haber_vacio.set_left(1)
        debe_haber_vacio.set_right(1)
        debe_haber_vacio_gc.set_top(1)
        debe_haber_vacio_gc.set_left(1)
        debe_haber_vacio_gc.set_right(1)
        debe_haber_nivel_i.set_right(1)
        debe_haber_nivel_i.set_left(1)
        debe_haber_nivel_i.set_top(1)
        debe_haber_nivel_i.set_bottom(6)
        debe_haber_gc.set_top(1)
        debe_haber_gc.set_left(1)
        debe_haber_gc.set_right(1)
        debe_haber_nivel_ii.set_top(1)
        debe_haber_nivel_ii.set_right(1)
        debe_haber_nivel_ii.set_left(1)

        worksheet = workbook.add_worksheet("Balance General")
        worksheet.set_portrait()
        worksheet.set_page_view()
        worksheet.set_paper(1)
        worksheet.set_margins(0.7, 0.7, 0.7, 0.7)
        # Tamaños
        worksheet.set_column('A:A', 8)
        worksheet.set_column('B:B', 42)
        worksheet.set_column('C:C', 12)
        worksheet.set_column('D:D', 12)
        worksheet.set_column('E:E', 12)
        # Empieza detalle
        x_rows = 0  # Linea a imprimir
        x_page = 0  # Numero de pagina
        x_max_rows = 47  # Maximo de lineas por pagina
        x_row_page = 0  # Linea actual vrs maximo de lineas
        x_ctrl_nivel_i = ''
        x_ctrl_nivel_ii = ''
        x_ctrl_nivel_gc = ''
        x_altura = 0
        x_recorre = 0
        x_suma_gc = 0
        x_suma_i = 0
        x_NiveliInicial = 1  # Aca empezamos desde activo
        x_NiveliFinal = 3

        # Calculo de la utilidad del ejercicio
        x_balance_4 = 0
        x_balance_4 = sum(self.env['account.move.line'].search([
            ('account_id.group_id.parent_id.parent_id.code_prefix_start', '=', '4'),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', datetime.strptime(str(self.end_date.year) + '-01-01', "%Y-%m-%d")),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id)]).mapped('balance')) *- 1
            #('move_id.journal_id.name', '!=', 'Partida de Cierre')]).mapped('balance')) *- 1
        x_balance_5 = 0
        x_balance_5 = sum(self.env['account.move.line'].search([
            ('account_id.group_id.parent_id.parent_id.code_prefix_start', '=', '5'),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', datetime.strptime(str(self.end_date.year) + '-01-01', "%Y-%m-%d")),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
            #('move_id.journal_id.name', '!=', 'Partida de Ciere')]).mapped('balance'))
        x_balance_6 = 0
        x_balance_6 = sum(self.env['account.move.line'].search([
            ('account_id.group_id.parent_id.parent_id.code_prefix_start', '=', '6'),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', datetime.strptime(str(self.end_date.year) + '-01-01', "%Y-%m-%d")),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
            #('move_id.journal_id.name', '!=', 'Partida de Cierre')]).mapped('balance'))
        x_balance_7 = 0
        x_balance_7 = sum(self.env['account.move.line'].search([
            ('account_id.group_id.parent_id.parent_id.code_prefix_start', '=', '7'),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', datetime.strptime(str(self.end_date.year) + '-01-01', "%Y-%m-%d")),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id)]).mapped('balance'))*-1
            #('move_id.journal_id.name', '!=', 'Partida de Cierre')]).mapped('balance'))
        x_balance_8 = 0
        x_balance_8 = sum(self.env['account.move.line'].search([
            ('account_id.group_id.parent_id.parent_id.code_prefix_start', '=', '8'),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', datetime.strptime(str(self.end_date.year) + '-01-01', "%Y-%m-%d")),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
            #('move_id.journal_id.name', '!=', 'Partida de Cierre')]).mapped('balance'))

        x_pasivo_capital = sum(self.env['account.move.line'].search([
            ('account_id.group_id.parent_id.parent_id.code_prefix_start', '=', '2'),
            ('move_id.state', '=', 'posted'),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id)]).mapped('balance')) * -1
            #('move_id.journal_id.name', '!=', 'Partida de Cierre')]).mapped('balance')) * -1
        x_pasivo_capital += sum(self.env['account.move.line'].search([
            ('account_id.group_id.parent_id.parent_id.code_prefix_start', '=', '3'),
            ('move_id.state', '=', 'posted'),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id)]).mapped('balance')) * -1
            #('move_id.journal_id.name', '!=', 'Partida de Cierre')]).mapped('balance')) * -1

        x_utilidad_ejercicio = (x_balance_4 - x_balance_5 - x_balance_6) + x_balance_7 - x_balance_8
        x_pasivo_capital = x_pasivo_capital + x_utilidad_ejercicio
        a_imprimir = []
        while x_NiveliInicial <= x_NiveliFinal: # Principal ciclo para saber que grupos van a ser tomados en cuenta en este caso 4 ingresos 5 cotos 6 gastos
            # Buscamos el id de grupo de la raiz nivel i
            NivelI = self.env['account.group'].search([
                ('company_id.id', '=', self.company_id.id),
                ('parent_id', '=', False),
                ('code_prefix_start', '=', x_NiveliInicial)],
                order="code_prefix_start asc", limit=1)

            if NivelI:
                for x_NivelI in NivelI:
                    x_control_i = 0
                    x_control_i = sum(self.env['account.move.line'].search([
                        ('account_id.group_id.parent_id.parent_id.id', 'in', x_NivelI.ids),
                        ('move_id.state', '=', 'posted'),
                        ('date', '<=', self.end_date),
                        ('balance', '!=', 0),
                        ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
                        #('move_id.journal_id.name', '!=', 'Partida de Cierre')]).mapped('balance'))
                    if x_control_i != 0:
                        a_imprimir.append([])
                        a_imprimir[x_altura].append(x_NivelI.code_prefix_start)
                        a_imprimir[x_altura].append('')
                        a_imprimir[x_altura].append('head_nivel_i')
                        a_imprimir[x_altura].append(x_NivelI.code_prefix_start)
                        a_imprimir[x_altura].append(x_NivelI.name)
                        a_imprimir[x_altura].append(0)
                        a_imprimir[x_altura].append(0)
                        a_imprimir[x_altura].append(0)
                        a_imprimir[x_altura].append('') # Nivel grupo cuenta balance general

                        x_altura += 1
                        # Buscamos el id de grupo del nivel ii que pertenezcan a nivel i
                        NivelII = self.env['account.group'].search([('parent_id.id', 'in', x_NivelI.ids)],
                                                                   order="code_prefix_start asc")
                        if NivelII:
                            for x_NivelII in NivelII:
                                x_control_ii = 0
                                x_control_ii = sum(self.env['account.move.line'].search([
                                    ('account_id.group_id.parent_id.id', 'in', x_NivelII.ids),
                                    ('move_id.state', '=', 'posted'),
                                    ('date', '<=', self.end_date),
                                    ('balance', '!=', 0),
                                    ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
                                    #('move_id.journal_id.name', '!=', 'Partida de Cierre')]).mapped('balance'))
                                if x_control_ii != 0:
                                    a_imprimir.append([])
                                    a_imprimir[x_altura].append(x_NivelI.code_prefix_start)
                                    a_imprimir[x_altura].append(x_NivelII.code_prefix_start)
                                    a_imprimir[x_altura].append('head_nivel_ii')
                                    a_imprimir[x_altura].append(x_NivelII.code_prefix_start)
                                    a_imprimir[x_altura].append(x_NivelII.name)
                                    a_imprimir[x_altura].append(0)
                                    a_imprimir[x_altura].append(0)
                                    a_imprimir[x_altura].append(0)
                                    a_imprimir[x_altura].append('')  # Nivel grupo cuenta balance general
                                    x_altura += 1
                                    # Buscamos el id de grupo de cuenta que pertenezca a nivel ii
                                    NivelGrupoCuenta = self.env['account.group'].search(
                                        [('parent_id.id', 'in', x_NivelII.ids)],
                                        order="code_prefix_start asc")
                                    if NivelGrupoCuenta:
                                        for x_NivelGrupoCuenta in NivelGrupoCuenta:
                                            x_control_gc = 0
                                            x_control_gc = sum(self.env['account.move.line'].search([
                                                ('account_id.group_id.id', 'in', x_NivelGrupoCuenta.ids),
                                                ('move_id.state', '=', 'posted'),
                                                ('date', '<=', self.end_date),
                                                #('balance', '!=', 0),
                                                ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
                                            #Consulta a account account agrupado por cuenta o code que sean del grupo x_nivelgrupocuenta
                                            NivelCuenta2 = self.env['account.account'].search(
                                                [('group_id.id', 'in', x_NivelGrupoCuenta.ids)],
                                                order="code asc")
                                            contador = 0
                                            if NivelCuenta2:
                                                for x_NivelCuenta2 in NivelCuenta2:
                                                    x_control_c2 = sum(self.env['account.move.line'].search([
                                                        ('account_id.id', '=', x_NivelCuenta2.id),
                                                        ('move_id.state', '=', 'posted'),
                                                        ('date', '<=', self.end_date),
                                                        ('balance', '!=', 0),
                                                        ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
                                                    if x_control_c2 != 0:
                                                        contador += 1
                                                #('move_id.journal_id.name', '!=', 'Partida de Cierre')]).mapped('balance'))
                                            # if (x_control_gc != 0) or (x_NivelGrupoCuenta.code_prefix_start == '30103' and x_utilidad_ejercicio != 0) or (len(x_agrupados) > 1):
                                            if (x_control_gc != 0) or ( x_NivelGrupoCuenta.code_prefix_start == '30103' and x_utilidad_ejercicio != 0) or contador != 0:
                                                a_imprimir.append([])
                                                a_imprimir[x_altura].append(x_NivelI.code_prefix_start)
                                                a_imprimir[x_altura].append(x_NivelII.code_prefix_start)
                                                a_imprimir[x_altura].append('head_nivel_gc')
                                                a_imprimir[x_altura].append(x_NivelGrupoCuenta.code_prefix_start)
                                                a_imprimir[x_altura].append(x_NivelGrupoCuenta.name)
                                                a_imprimir[x_altura].append(0)
                                                a_imprimir[x_altura].append(0)
                                                a_imprimir[x_altura].append(0)
                                                a_imprimir[x_altura].append(x_NivelGrupoCuenta.code_prefix_start)  # Nivel grupo cuenta balance general
                                                x_altura += 1
                                                NivelCuenta = self.env['account.account'].search(
                                                    [('group_id.id', 'in', x_NivelGrupoCuenta.ids)],
                                                    order="code asc")
                                                if NivelCuenta:
                                                    for x_NivelCuenta in NivelCuenta:
                                                        x_control_c = sum(self.env['account.move.line'].search([
                                                            ('account_id.id', '=', x_NivelCuenta.id),
                                                            ('move_id.state', '=', 'posted'),
                                                            ('date', '<=', self.end_date),
                                                            ('balance', '!=', 0),
                                                            ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
                                                            #('move_id.journal_id.name', '!=', 'Partida de Cierre')]).mapped('balance'))
                                                        if (x_control_c != 0) or (x_NivelCuenta.code == '3010301' and x_utilidad_ejercicio != 0):
                                                            a_imprimir.append([])
                                                            a_imprimir[x_altura].append(x_NivelI.code_prefix_start)
                                                            a_imprimir[x_altura].append(x_NivelII.code_prefix_start)
                                                            a_imprimir[x_altura].append('nivel_c')
                                                            a_imprimir[x_altura].append(x_NivelCuenta.code)
                                                            a_imprimir[x_altura].append(x_NivelCuenta.name)
                                                            if x_NivelI.code_prefix_start == '2' or x_NivelI.code_prefix_start == '3':
                                                                if x_NivelCuenta.code == '3010301':
                                                                    a_imprimir[x_altura].append((x_control_c * -1) + x_utilidad_ejercicio)
                                                                else:
                                                                    a_imprimir[x_altura].append(x_control_c * -1)
                                                            else:
                                                                a_imprimir[x_altura].append(x_control_c)
                                                            a_imprimir[x_altura].append(0)
                                                            a_imprimir[x_altura].append(0)
                                                            a_imprimir[x_altura].append(x_NivelGrupoCuenta.code_prefix_start)  # Nivel grupo cuenta balance general
                                                            x_altura += 1
                                                # Pie de cuenta
                                                a_imprimir.append([])
                                                a_imprimir[x_altura].append(x_NivelI.code_prefix_start)
                                                a_imprimir[x_altura].append(x_NivelII.code_prefix_start)
                                                a_imprimir[x_altura].append('foot_nivel_gc')
                                                a_imprimir[x_altura].append('')
                                                a_imprimir[x_altura].append(x_NivelGrupoCuenta.name)
                                                a_imprimir[x_altura].append(0)
                                                if x_NivelI.code_prefix_start == '2' or x_NivelI.code_prefix_start == '3':
                                                    if x_NivelGrupoCuenta.code_prefix_start == '30103':
                                                        a_imprimir[x_altura].append((x_control_c * -1) + x_utilidad_ejercicio)
                                                    else:
                                                        a_imprimir[x_altura].append(x_control_gc*-1)
                                                else:
                                                    a_imprimir[x_altura].append(x_control_gc)
                                                a_imprimir[x_altura].append(0)
                                                a_imprimir[x_altura].append(x_NivelGrupoCuenta.code_prefix_start)  # Nivel grupo cuenta balance general
                                                x_altura += 1
                                    a_imprimir.append([])
                                    a_imprimir[x_altura].append(x_NivelI.code_prefix_start)
                                    a_imprimir[x_altura].append(x_NivelII.code_prefix_start)
                                    a_imprimir[x_altura].append('foot_nivel_ii')
                                    a_imprimir[x_altura].append('')
                                    a_imprimir[x_altura].append('   Suma '+ x_NivelII.name)
                                    a_imprimir[x_altura].append(0)
                                    a_imprimir[x_altura].append(0)
                                    if x_NivelI.code_prefix_start == '2' or x_NivelI.code_prefix_start == '3':
                                        if x_NivelII.code_prefix_start == '301':
                                            a_imprimir[x_altura].append((x_control_ii * -1) + x_utilidad_ejercicio)
                                        else:
                                            a_imprimir[x_altura].append(x_control_ii*-1)
                                    else:
                                        a_imprimir[x_altura].append(x_control_ii)
                                    a_imprimir[x_altura].append('')  # Nivel grupo cuenta balance general
                                    x_altura += 1
                        a_imprimir.append([])
                        a_imprimir[x_altura].append(x_NivelI.code_prefix_start)
                        a_imprimir[x_altura].append(x_NivelII.code_prefix_start)
                        a_imprimir[x_altura].append('foot_nivel_i')
                        a_imprimir[x_altura].append('')
                        a_imprimir[x_altura].append('   SUMA TOTAL DEL ' + x_NivelI.name)
                        a_imprimir[x_altura].append(0)
                        a_imprimir[x_altura].append(0)
                        if x_NivelI.code_prefix_start == '2' or x_NivelI.code_prefix_start == '3':
                            if x_NivelI.code_prefix_start == '3':
                                a_imprimir[x_altura].append((x_control_i * -1) + x_utilidad_ejercicio)
                            else:
                                a_imprimir[x_altura].append(x_control_i *-1)
                        else:
                            a_imprimir[x_altura].append(x_control_i)
                        a_imprimir[x_altura].append('')  # Nivel grupo cuenta balance general
                        x_altura += 1
            x_NiveliInicial += 1

        a_imprimir.append([])
        a_imprimir[x_altura].append('')
        a_imprimir[x_altura].append('')
        a_imprimir[x_altura].append('utilidad_ejercicio')
        a_imprimir[x_altura].append('')
        a_imprimir[x_altura].append('   SUMA TOTAL DEL PASIVO Y CAPITAL')
        a_imprimir[x_altura].append(0)
        a_imprimir[x_altura].append(0)
        a_imprimir[x_altura].append(x_pasivo_capital)
        a_imprimir[x_altura].append('')  # Nivel grupo cuenta balance general

        if a_imprimir:
            while x_recorre < len(a_imprimir):
                if x_ctrl_nivel_i == a_imprimir[x_recorre][0] and x_ctrl_nivel_ii == a_imprimir[x_recorre][1] and x_ctrl_nivel_gc == a_imprimir[x_recorre][8] and a_imprimir[x_recorre][8]!='':
                    x_suma_gc += float(a_imprimir[x_recorre][5])
                    x_suma_i += float(a_imprimir[x_recorre][5])

                elif x_ctrl_nivel_i == a_imprimir[x_recorre][0] and x_ctrl_nivel_ii == a_imprimir[x_recorre][1] and x_ctrl_nivel_gc != a_imprimir[x_recorre][8]:
                    x_suma_gc = 0
                    x_suma_i += float(a_imprimir[x_recorre][5])

                elif x_ctrl_nivel_i == a_imprimir[x_recorre][0] and x_ctrl_nivel_ii != a_imprimir[x_recorre][1]:
                    x_suma_gc = 0
                    x_suma_i = 0
                else:
                    x_suma_gc = 0
                    x_suma_i = 0
                x_ctrl_nivel_i = a_imprimir[x_recorre][0]
                x_ctrl_nivel_ii = a_imprimir[x_recorre][1]
                x_ctrl_nivel_gc = a_imprimir[x_recorre][8]

                if x_row_page < x_max_rows:  # Estamos en ciclo
                    # ---------------------------- Encabezado ----------------------------------------------------------
                    if x_row_page == 0:  # Nueva pagina

                        worksheet.write(x_rows, 4, "Folio: " + str(self.folio + x_page), frmt_folio)
                        x_rows += 1
                        x_row_page += 1

                        worksheet.merge_range(x_rows, 0, x_rows, 4, self.company_id.name,
                                              frmt_encabezado)  # Encabezado
                        x_rows += 1
                        x_row_page += 1

                        worksheet.merge_range(x_rows, 0, x_rows, 4, "NIT: " + self.company_id.partner_id.vat,
                                              frmt_encabezado)  # Encabezado
                        x_rows += 1
                        x_row_page += 1

                        worksheet.merge_range(x_rows, 0, x_rows, 4, "Balance General", frmt_encabezado)  # Encabezado
                        x_rows += 1
                        x_row_page += 1

                        worksheet.merge_range(x_rows, 0, x_rows, 4,
                                              str("Al " + str(self.end_date.day) + " de " + thMes + " de " + str(
                                                  self.end_date.year)), frmt_encabezado)  # Encabezado
                        x_rows += 1
                        x_row_page += 1

                        worksheet.merge_range(x_rows, 0, x_rows, 4, "(EXPRESADO EN QUETZALES)",
                                              frmt_encabezado)  # Encabezado
                        x_rows += 1
                        x_row_page += 1
                        # Aca es solo para cerrar el marco
                        worksheet.write(x_rows, 0, '', frmt_borde_superior)
                        worksheet.write(x_rows, 1, '', frmt_borde_superior)
                        worksheet.write(x_rows, 2, '', frmt_borde_superior)
                        worksheet.write(x_rows, 3, '', frmt_borde_superior)
                        worksheet.write(x_rows, 4, '', frmt_borde_superior)
                        x_rows += 1
                        x_row_page += 1

                        if a_imprimir[x_recorre][2] == 'head_nivel_i' or a_imprimir[x_recorre][2] == 'head_nivel_ii' or \
                                a_imprimir[x_recorre][2] == 'head_nivel_gc':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber_vacio)
                            worksheet.write(x_rows, 3, '', debe_haber_vacio)
                            worksheet.write(x_rows, 4, '', debe_haber_vacio)
                        elif a_imprimir[x_recorre][2] == 'nivel_c':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][5], debe_haber)
                            worksheet.write(x_rows, 3, '', debe_haber_vacio)
                            worksheet.write(x_rows, 4, '', debe_haber_vacio)
                        elif a_imprimir[x_recorre][2] == 'foot_nivel_gc':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo_c)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber_vacio_gc)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber_gc)
                            worksheet.write(x_rows, 4, '', debe_haber_vacio_gc)
                        elif a_imprimir[x_recorre][2] == 'foot_nivel_ii':
                            worksheet.write(x_rows, 0, '', frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber_nivel_ii)
                            worksheet.write(x_rows, 3, '', debe_haber_nivel_ii)
                            worksheet.write(x_rows, 4, a_imprimir[x_recorre][7], debe_haber_nivel_ii)
                        elif a_imprimir[x_recorre][2] == 'foot_nivel_i':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber_nivel_ii)
                            worksheet.write(x_rows, 3, '', debe_haber_nivel_ii)
                            worksheet.write(x_rows, 4, a_imprimir[x_recorre][7], debe_haber_nivel_i)
                        else:  # a_imprimir[x_recorre][2] == 'utilidad_ejercicio': # utilidad ejercicio
                            worksheet.write(x_rows, 0, '', frmt_codigo_utilidad_ejercicio)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_utilidad_ejercicio)
                            worksheet.write(x_rows, 2, '', debe_utilidad_ejercicio)
                            worksheet.write(x_rows, 3, '', debe_utilidad_ejercicio)
                            worksheet.write(x_rows, 4, a_imprimir[x_recorre][7], haber_utilidad_ejercicio)
                        x_rows += 1
                        x_row_page += 1

                    # ---------------------------- Fin Encabezado ----------------------------------------------------------
                    elif x_row_page > 0 and x_row_page == x_max_rows - 1:  # Estamos en la penultima linea
                        x_row_page = 0
                        worksheet.merge_range(x_rows, 0, x_rows, 1, "VAN", frmt_van)
                        worksheet.write(x_rows, 2, '', debe_haber_van_vienen)
                        worksheet.write(x_rows, 3, float(x_suma_gc), debe_haber_van_vienen)
                        worksheet.write(x_rows, 4, float(x_suma_i), debe_haber_van_vienen)
                        # Encabezado 1
                        x_rows += 1
                        #x_row_page += 1
                        x_page += 1

                        worksheet.write(x_rows, 4, "Folio: " + str(self.folio + x_page), frmt_folio)
                        x_rows += 1
                        x_row_page += 1

                        worksheet.merge_range(x_rows, 0, x_rows, 4, self.company_id.name,
                                              frmt_encabezado)  # Encabezado
                        x_rows += 1
                        x_row_page += 1

                        worksheet.merge_range(x_rows, 0, x_rows, 4, "NIT: " + self.company_id.partner_id.vat,
                                              frmt_encabezado)  # Encabezado
                        x_rows += 1
                        x_row_page += 1

                        worksheet.merge_range(x_rows, 0, x_rows, 4, "Balance General",
                                              frmt_encabezado)  # Encabezado
                        x_rows += 1
                        x_row_page += 1

                        worksheet.merge_range(x_rows, 0, x_rows, 4,
                                              str("Al " + str(self.end_date.day) + " de " + thMes + " de " + str(
                                                  self.end_date.year)), frmt_encabezado)  # Encabezado
                        x_rows += 1
                        x_row_page += 1

                        worksheet.merge_range(x_rows, 0, x_rows, 4, "(EXPRESADO EN QUETZALES)",
                                              frmt_encabezado)  # Encabezado
                        x_rows += 1
                        x_row_page += 1

                        worksheet.write(x_rows, 0, '', frmt_borde_superior)
                        worksheet.write(x_rows, 1, '', frmt_borde_superior)
                        worksheet.write(x_rows, 2, '', frmt_borde_superior)
                        worksheet.write(x_rows, 3, '', frmt_borde_superior)
                        worksheet.write(x_rows, 4, '', frmt_borde_superior)
                        x_rows += 1
                        x_row_page += 1

                        worksheet.merge_range(x_rows, 0, x_rows, 1, "VIENEN", frmt_van)
                        worksheet.write(x_rows, 2, '', debe_haber_van_vienen)
                        worksheet.write(x_rows, 3, float(x_suma_gc), debe_haber_van_vienen)
                        worksheet.write(x_rows, 4, float(x_suma_i), debe_haber_van_vienen)
                        x_rows += 1
                        x_row_page += 1

                        if a_imprimir[x_recorre][2] == 'head_nivel_i' or a_imprimir[x_recorre][2] == 'head_nivel_ii' or \
                                a_imprimir[x_recorre][2] == 'head_nivel_gc':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber_vacio)
                            worksheet.write(x_rows, 3, '', debe_haber_vacio)
                            worksheet.write(x_rows, 4, '', debe_haber_vacio)
                        elif a_imprimir[x_recorre][2] == 'nivel_c':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][5], debe_haber)
                            worksheet.write(x_rows, 3, '', debe_haber_vacio)
                            worksheet.write(x_rows, 4, '', debe_haber_vacio)
                        elif a_imprimir[x_recorre][2] == 'foot_nivel_gc':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo_c)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber_vacio_gc)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber_gc)
                            worksheet.write(x_rows, 4, '', debe_haber_vacio_gc)
                        elif a_imprimir[x_recorre][2] == 'foot_nivel_ii':
                            worksheet.write(x_rows, 0, '', frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber_nivel_ii)
                            worksheet.write(x_rows, 3, '', debe_haber_nivel_ii)
                            worksheet.write(x_rows, 4, a_imprimir[x_recorre][7], debe_haber_nivel_ii)
                        elif a_imprimir[x_recorre][2] == 'foot_nivel_i':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber_nivel_ii)
                            worksheet.write(x_rows, 3, '', debe_haber_nivel_ii)
                            worksheet.write(x_rows, 4, a_imprimir[x_recorre][7], debe_haber_nivel_i)
                        else:  # a_imprimir[x_recorre][2] == 'utilidad_ejercicio': # utilidad ejercicio
                            worksheet.write(x_rows, 0, '', frmt_codigo_utilidad_ejercicio)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_utilidad_ejercicio)
                            worksheet.write(x_rows, 2, '', debe_utilidad_ejercicio)
                            worksheet.write(x_rows, 3, '', debe_utilidad_ejercicio)
                            worksheet.write(x_rows, 4, a_imprimir[x_recorre][7], haber_utilidad_ejercicio)
                        x_rows += 1
                        x_row_page += 1

                    else:  # No estamos en la ultima linea, estamos en la misma cuenta
                        if a_imprimir[x_recorre][2] == 'head_nivel_i' or a_imprimir[x_recorre][2] == 'head_nivel_ii' or \
                                a_imprimir[x_recorre][2] == 'head_nivel_gc':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber_vacio)
                            worksheet.write(x_rows, 3, '', debe_haber_vacio)
                            worksheet.write(x_rows, 4, '', debe_haber_vacio)
                        elif a_imprimir[x_recorre][2] == 'nivel_c':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][5], debe_haber)
                            worksheet.write(x_rows, 3, '', debe_haber_vacio)
                            worksheet.write(x_rows, 4, '', debe_haber_vacio)
                        elif a_imprimir[x_recorre][2] == 'foot_nivel_gc':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo_c)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber_vacio_gc)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber_gc)
                            worksheet.write(x_rows, 4, '', debe_haber_vacio_gc)
                        elif a_imprimir[x_recorre][2] == 'foot_nivel_ii':
                            worksheet.write(x_rows, 0, '', frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber_nivel_ii)
                            worksheet.write(x_rows, 3, '', debe_haber_nivel_ii)
                            worksheet.write(x_rows, 4, a_imprimir[x_recorre][7], debe_haber_nivel_ii)
                        elif a_imprimir[x_recorre][2] == 'foot_nivel_i':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 2, '', debe_haber_nivel_ii)
                            worksheet.write(x_rows, 3, '', debe_haber_nivel_ii)
                            worksheet.write(x_rows, 4, a_imprimir[x_recorre][7], debe_haber_nivel_i)
                        else:  # a_imprimir[x_recorre][2] == 'utilidad_ejercicio': # utilidad ejercicio
                            worksheet.write(x_rows, 0, '', frmt_codigo_utilidad_ejercicio)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][4], frmt_utilidad_ejercicio)
                            worksheet.write(x_rows, 2, '', debe_utilidad_ejercicio)
                            worksheet.write(x_rows, 3, '', debe_utilidad_ejercicio)
                            worksheet.write(x_rows, 4, a_imprimir[x_recorre][7], haber_utilidad_ejercicio)
                        x_rows += 1
                        x_row_page += 1
                x_recorre += 1
            certifica = str(self.certificacion)
            text1 = '______________________' \
                    '\n' + self.representante + \
                    '\nRepresentante Legal'
            text2 = '______________________' \
                    '\n' + self.contador + \
                    '\nContador'

            options1 = {
                'width': 205,
                'height': 100,
                'x_offset': 0,
                'y_offset': 0,

                'font': {'color': 'black',
                         'font': 'Arial',
                         'size': 10,
                         'bold': True,
                         },
                'align': {'vertical': 'bottom',
                          'horizontal': 'center'
                          },

            }
            options2 = {
                'width': 205,
                'height': 100,
                'x_offset': 0,
                'y_offset': 0,

                'font': {'color': 'black',
                         'font': 'Arial',
                         'size': 10,
                         'bold': True,
                         },
                'align': {'vertical': 'bottom',
                          'horizontal': 'center'
                          },

            }
            cert_options = {
                'width': 615,
                'height': 100,
                'x_offset': 0,
                'y_offset': 0,

                'font': {'color': 'black',
                         'font': 'Arial',
                         'size': 10,
                         'bold': True,
                         },
                'align': {'vertical': 'top',
                          'horizontal': 'left'
                          },

            }
            cell = xl_rowcol_to_cell(x_rows + 2, 0)
            worksheet.insert_textbox(cell, certifica, cert_options)
            cell = xl_rowcol_to_cell(x_rows + 7, 0)
            worksheet.insert_textbox(cell, text1, options1)
            cell = xl_rowcol_to_cell(x_rows + 7, 2)
            worksheet.insert_textbox(cell, text2, options2)


        workbook.close()
        self.write({
            'state': 'get',
            'data': base64.b64encode(open(xls_path, 'rb').read()),
            'name': xls_filename
        })
        return {
            'name': 'Balance General',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new'
        }

class wizard_libro_compras(models.TransientModel):
    _name = 'wizard.libro.compras'
    _description = "Wizard Libro de Compras"
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id)
    start_date = fields.Date(string="Del")
    end_date = fields.Date(string="Al")
    folio = fields.Integer(string="Folio")
    # campo many2many de diarios
    journal_ids = fields.Many2many('account.journal', string='Diarios', required=True, domain="[('type', '=', 'purchase')]")
    # campo many2one de facturas entre fechas del al
    invoice_ids = fields.Many2many('account.move.line', string='Facturas', domain="[('move_id.date', '>=', start_date), ('move_id.date', '<=', end_date), ('journal_id.type', '=', 'purchase'),('move_id.state','=','posted')]")
    folio = fields.Integer(string="Folio")
    state = fields.Selection([('choose', 'choose'), ('get', 'get')], default='choose')
    name = fields.Char(string='File Name', readonly=True)
    data = fields.Binary(string='File', readonly=True)

    @api.onchange('company_id')
    def onchange_company_id(self):
        domain = [('id', 'in', self.env.user.company_ids.ids)]
        # if self.company_id:
        # self.warehouse_ids = False
        # self.location_ids = False
        return {'domain': {'company_id': domain}}

    def go_back(self):
        self.state = 'choose'
        return {
            'name': 'Libro de Compras',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new'
        }

    def check_date(self):
        if self.end_date < self.start_date:
            raise ValidationError(_('Fecha A debe ser despues de Fecha Del'))
        if self.start_date.year != self.end_date.year:
            raise ValidationError(_('Las fechas deben ser del mismo año'))

    def print_xls_libro_compras(self):
        self.check_date()
        thMes = ""
        thMesa = ""

        if self.start_date.month == 1:
            thMes = "Enero"
        elif self.start_date.month == 2:
            thMes = "Febrero"
        elif self.start_date.month == 3:
            thMes = "Marzo"
        elif self.start_date.month == 4:
            thMes = "Abril"
        elif self.start_date.month == 5:
            thMes = "Mayo"
        elif self.start_date.month == 6:
            thMes = "Junio"
        elif self.start_date.month == 7:
            thMes = "Julio"
        elif self.start_date.month == 8:
            thMes = "Agosto"
        elif self.start_date.month == 9:
            thMes = "Septiembre"
        elif self.start_date.month == 10:
            thMes = "Octubre"
        elif self.start_date.month == 11:
            thMes = "Noviembre"
        else:
            thMes = "Diciembre"

        if self.end_date.month == 1:
            thMesa = "Enero"
        elif self.end_date.month == 2:
            thMesa = "Febrero"
        elif self.end_date.month == 3:
            thMesa = "Marzo"
        elif self.end_date.month == 4:
            thMesa = "Abril"
        elif self.end_date.month == 5:
            thMesa = "Mayo"
        elif self.end_date.month == 6:
            thMesa = "Junio"
        elif self.end_date.month == 7:
            thMesa = "Julio"
        elif self.end_date.month == 8:
            thMesa = "Agosto"
        elif self.end_date.month == 9:
            thMesa = "Septiembre"
        elif self.end_date.month == 10:
            thMesa = "Octubre"
        elif self.end_date.month == 11:
            thMesa = "Noviembre"
        else:
            thMesa = "Diciembre"
        x_debe_haber = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        #cambiar la forma para tener una carpeta temporal
        xls_filename = 'Libro de Compras.xlsx'
        temp_dir = tempfile.gettempdir()
        xls_path = os.path.join(temp_dir, xls_filename)
        workbook = xlsxwriter.Workbook(xls_path)
        frmt_folio = workbook.add_format({'bold': True, 'align': 'right','font': 'Arial', 'font_size': 6})
        frmt_encabezado = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'font': 'Arial', 'font_size': 6})
        frmt_encabezado_columna = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'font': 'Arial', 'font_size': 6, 'border': 1, 'bg_color': '#DDEBF7', 'text_wrap': True})
        detail_center_nb = workbook.add_format({'align': 'center', 'font': 'Arial', 'font_size': 6})
        detail_left_nb = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 6})
        detail_right_nb = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 6})
        detail_right_b_b = workbook.add_format({'bold': True, 'align': 'right', 'font': 'Arial', 'font_size': 6, 'border': 1})
        detail_right_nb_b = workbook.add_format({'bold': True, 'align': 'right', 'font': 'Arial', 'font_size': 6})
        only_b_b = workbook.add_format({'bold': True, 'align': 'center', 'font': 'Arial', 'font_size': 6, 'border': 1})
        detail_center_b = workbook.add_format({'bold': True, 'align': 'center', 'font': 'Arial', 'font_size': 6, 'border' : 1})

        worksheet = workbook.add_worksheet("Libro de Compras")
        worksheet.set_landscape()
        worksheet.set_page_view()
        worksheet.set_paper(1)
        worksheet.set_margins(0.3, 0.3, 0.3, 0.3)

        # Tamaños
        worksheet.set_column('A:A', 4)
        worksheet.set_column('B:B', 4)
        worksheet.set_column('C:C', 4)
        worksheet.set_column('D:D', 4)
        worksheet.set_column('E:E', 4)
        worksheet.set_column('F:F', 4)
        worksheet.set_column('G:G', 4)
        worksheet.set_column('H:H', 4)
        worksheet.set_column('I:I', 4)
        worksheet.set_column('J:J', 14)
        worksheet.set_column('K:K', 5)
        worksheet.set_column('L:L', 5)
        worksheet.set_column('M:M', 5)
        worksheet.set_column('N:N', 5)
        worksheet.set_column('O:O', 5)
        worksheet.set_column('P:P', 5)
        worksheet.set_column('Q:Q', 5)
        worksheet.set_column('R:R', 5)
        worksheet.set_column('S:S', 5)
        worksheet.set_column('T:T', 5)
        worksheet.set_column('U:U', 5)
        worksheet.set_column('V:V', 5)
        worksheet.set_column('W:W', 5)
        # Empieza detalle
        x_rows = 0  # Linea a imprimir
        x_page = 0  # Numero de pagina
        x_row_page = 0  # Linea actual vrs maximo de lineas
        x_max_rows = 38  # Maximo de lineas por pagina
        x_recorre = 0
        aux_mes = 1

        if self.invoice_ids:
            account_move = self.env['account.move'].search([
                ('company_id.id', '=', self.company_id.id),
                ('state', '=', 'posted'),
                ('date', '>=', self.start_date),
                ('date', '<=', self.end_date),
                ('invoice_line_ids', 'in', self.invoice_ids.ids),
                ('journal_id.id', 'in', self.journal_ids.ids)], order="date desc")
        else:
            account_move = self.env['account.move'].search([
                ('company_id.id', '=', self.company_id.id),
                ('state', '=', 'posted'),
                ('date', '>=', self.start_date),
                ('date', '<=', self.end_date),
                ('journal_id.id', 'in', self.journal_ids.ids)], order="date desc")

        if account_move:
            x_rows = 0
            for am in account_move:
                # ---------------------------- Encabezado ----------------------------------------------------------
                if x_row_page == x_max_rows:
                    worksheet.write(x_rows, 9, 'VAN', frmt_encabezado_columna)
                    worksheet.write(x_rows, 10, x_debe_haber[0], detail_right_nb_b)
                    worksheet.write(x_rows, 11, x_debe_haber[1], detail_right_nb_b)
                    worksheet.write(x_rows, 12, x_debe_haber[2], detail_right_nb_b)
                    worksheet.write(x_rows, 13, x_debe_haber[3], detail_right_nb_b)
                    worksheet.write(x_rows, 14, x_debe_haber[4], detail_right_nb_b)
                    worksheet.write(x_rows, 15, x_debe_haber[5], detail_right_nb_b)
                    worksheet.write(x_rows, 16, x_debe_haber[6], detail_right_nb_b)
                    worksheet.write(x_rows, 17, x_debe_haber[7], detail_right_nb_b)
                    worksheet.write(x_rows, 18, x_debe_haber[8], detail_right_nb_b)
                    worksheet.write(x_rows, 19, x_debe_haber[9], detail_right_nb_b)
                    worksheet.write(x_rows, 20, x_debe_haber[10], detail_right_nb_b)
                    worksheet.write(x_rows, 21, x_debe_haber[11], detail_right_nb_b)
                    worksheet.write(x_rows, 22, x_debe_haber[12], detail_right_nb_b)
                    x_rows += 1
                    x_row_page = 0
                    x_page += 1
                if x_row_page == 0:  # Nueva pagina
                    worksheet.write(x_rows, 22, "Folio: " + str(self.folio + x_page), frmt_folio)
                    x_rows += 1
                    x_row_page += 1

                    worksheet.merge_range(x_rows, 0, x_rows, 22, 'LIBRO DE COMPRAS Y SERVICIOS', frmt_encabezado)  # Encabezado
                    x_rows += 1
                    x_row_page += 1

                    worksheet.merge_range(x_rows, 0, x_rows, 22, self.company_id.name, frmt_encabezado)  # Encabezado
                    x_rows += 1
                    x_row_page += 1

                    worksheet.merge_range(x_rows, 0, x_rows, 22, "NIT: " + self.company_id.partner_id.vat, frmt_encabezado)  # Encabezado
                    x_rows += 1
                    x_row_page += 1

                    worksheet.merge_range(x_rows, 0, x_rows, 22,str("Del " + str(self.start_date.day) + " de " + thMes + " de " + str(self.start_date.year) +
                                                                    " Al " + str(self.end_date.day) + " de " + thMesa + " de " + str(self.end_date.year)), frmt_encabezado)  # Encabezado
                    x_rows += 2
                    x_row_page += 2

                    worksheet.merge_range(x_rows, 0, x_rows+2, 0, 'Fecha', frmt_encabezado_columna)
                    worksheet.merge_range(x_rows, 1, x_rows+2, 1, 'Establecimiento', frmt_encabezado_columna)
                    worksheet.merge_range(x_rows, 2, x_rows+2, 2, 'Tipo de Transacción', frmt_encabezado_columna)
                    worksheet.merge_range(x_rows, 3, x_rows+2, 3, 'Tipo de Documento', frmt_encabezado_columna)
                    worksheet.merge_range(x_rows, 4, x_rows+2, 4, 'Estado', frmt_encabezado_columna)
                    worksheet.merge_range(x_rows, 5, x_rows+2, 5, 'Referencia Interna', frmt_encabezado_columna)
                    worksheet.merge_range(x_rows, 6, x_rows+2, 6, 'Serie', frmt_encabezado_columna)
                    worksheet.merge_range(x_rows, 7, x_rows+2, 7, 'Numero', frmt_encabezado_columna)
                    worksheet.merge_range(x_rows, 8, x_rows+2, 8, 'NIT', frmt_encabezado_columna)
                    worksheet.merge_range(x_rows, 9, x_rows+2, 9, 'Nombre', frmt_encabezado_columna)
                    worksheet.merge_range(x_rows, 10, x_rows, 13, 'Local', frmt_encabezado_columna)
                    worksheet.merge_range(x_rows + 1, 10, x_rows + 1, 11, 'Gravadas', frmt_encabezado_columna)
                    worksheet.merge_range(x_rows + 1, 12, x_rows + 1, 13, 'Exentas/No Afectas', frmt_encabezado_columna)
                    worksheet.write(x_rows + 2, 10, 'Bienes', frmt_encabezado_columna)
                    worksheet.write(x_rows + 2, 11, 'Servicios', frmt_encabezado_columna)
                    worksheet.write(x_rows + 2, 12, 'Bienes', frmt_encabezado_columna)
                    worksheet.write(x_rows + 2, 13, 'Servicios', frmt_encabezado_columna)
                    worksheet.merge_range(x_rows, 14, x_rows, 17, 'Importación', frmt_encabezado_columna)
                    worksheet.merge_range(x_rows + 1, 14, x_rows + 1, 15, 'Gravadas', frmt_encabezado_columna)
                    worksheet.merge_range(x_rows + 1, 16, x_rows + 1, 17, 'Exentas/No Afectas', frmt_encabezado_columna)
                    worksheet.write(x_rows + 2, 14, 'Bienes', frmt_encabezado_columna)
                    worksheet.write(x_rows + 2, 15, 'Servicios', frmt_encabezado_columna)
                    worksheet.write(x_rows + 2, 16, 'Bienes', frmt_encabezado_columna)
                    worksheet.write(x_rows + 2, 17, 'Servicios', frmt_encabezado_columna)
                    worksheet.merge_range(x_rows, 18, x_rows + 1, 19, 'Pequeño Contribuyente', frmt_encabezado_columna)
                    worksheet.write(x_rows + 2, 18, 'Bienes', frmt_encabezado_columna)
                    worksheet.write(x_rows + 2, 19, 'Servicios', frmt_encabezado_columna)
                    worksheet.merge_range(x_rows, 20, x_rows + 2, 20, 'IDP / Otros Arbitrios', frmt_encabezado_columna)
                    worksheet.merge_range(x_rows, 21, x_rows + 2, 21, 'IVA', frmt_encabezado_columna)
                    worksheet.merge_range(x_rows, 22, x_rows + 2, 22, 'TOTAL', frmt_encabezado_columna)
                    x_rows += 3
                    x_row_page += 3
                    if x_page > 0:
                        worksheet.write(x_rows, 9, 'VIENEN', frmt_encabezado)
                        worksheet.write(x_rows, 10, x_debe_haber[0], detail_right_nb_b)
                        worksheet.write(x_rows, 11, x_debe_haber[1], detail_right_nb_b)
                        worksheet.write(x_rows, 12, x_debe_haber[2], detail_right_nb_b)
                        worksheet.write(x_rows, 13, x_debe_haber[3], detail_right_nb_b)
                        worksheet.write(x_rows, 14, x_debe_haber[4], detail_right_nb_b)
                        worksheet.write(x_rows, 15, x_debe_haber[5], detail_right_nb_b)
                        worksheet.write(x_rows, 16, x_debe_haber[6], detail_right_nb_b)
                        worksheet.write(x_rows, 17, x_debe_haber[7], detail_right_nb_b)
                        worksheet.write(x_rows, 18, x_debe_haber[8], detail_right_nb_b)
                        worksheet.write(x_rows, 19, x_debe_haber[9], detail_right_nb_b)
                        worksheet.write(x_rows, 20, x_debe_haber[10], detail_right_nb_b)
                        worksheet.write(x_rows, 21, x_debe_haber[11], detail_right_nb_b)
                        worksheet.write(x_rows, 22, x_debe_haber[12], detail_right_nb_b)
                        x_rows += 1
                        x_row_page += 1
                worksheet.write(x_rows, 0, am.date.strftime('%d-%m-%Y'), detail_center_nb)
                worksheet.write(x_rows, 1, am.journal_id.codigo_establecimiento, detail_center_nb)
                worksheet.write(x_rows, 2, am.tipo_transaccion, detail_center_nb)
                worksheet.write(x_rows, 3, am.tipo_documento, detail_center_nb)
                worksheet.write(x_rows, 4, am.estado_factura, detail_center_nb)
                worksheet.write(x_rows, 5, am.referencia_interna if am.referencia_interna else '', detail_center_nb)
                worksheet.write(x_rows, 6, am.serie_fel if am.serie_fel else '', detail_center_nb)
                worksheet.write(x_rows, 7, am.numero_fel if am.numero_fel else '', detail_center_nb)
                worksheet.write(x_rows, 8, am.partner_id.vat, detail_left_nb)
                worksheet.write(x_rows, 9, am.partner_id.name, detail_left_nb)
                worksheet.write(x_rows, 10, am.txt_total_bien_cpa, detail_right_nb)
                x_debe_haber[0] += am.txt_total_bien_cpa
                worksheet.write(x_rows, 11, am.txt_total_servicio_cpa, detail_right_nb)
                x_debe_haber[1] += am.txt_total_servicio_cpa
                worksheet.write(x_rows, 12, 0, detail_right_nb)
                x_debe_haber[2] += 0
                worksheet.write(x_rows, 13, 0, detail_right_nb)
                x_debe_haber[3] += 0
                worksheet.write(x_rows, 14, am.txt_total_ie_bien_cpa, detail_right_nb)
                x_debe_haber[4] += am.txt_total_ie_bien_cpa
                worksheet.write(x_rows, 15, am.txt_total_ie_servicio_cpa, detail_right_nb)
                x_debe_haber[5] += am.txt_total_ie_servicio_cpa
                worksheet.write(x_rows, 16, am.txt_exter_ie_exen_bien, detail_right_nb)
                x_debe_haber[6] += am.txt_exter_ie_exen_bien
                worksheet.write(x_rows, 17, am.txt_exter_ie_exen_serv, detail_right_nb)
                x_debe_haber[7] += am.txt_exter_ie_exen_serv
                worksheet.write(x_rows, 18, am.txt_local_bien_pq, detail_right_nb)
                x_debe_haber[8] += am.txt_local_bien_pq
                worksheet.write(x_rows, 19, am.txt_local_serv_pq, detail_right_nb)
                x_debe_haber[9] += am.txt_local_serv_pq
                worksheet.write(x_rows, 20, am.txt_total_idp_arb if am.txt_total_idp_arb > 0.03 else 0, detail_right_nb)
                x_debe_haber[10] += am.txt_total_idp_arb if am.txt_total_idp_arb > 0.03 else 0
                worksheet.write(x_rows, 21, am.txt_sum_iva_asiste, detail_right_nb)
                x_debe_haber[11] += am.txt_sum_iva_asiste
                thSuma_txt_total_idp_arb = 0
                thSuma_txt_total_idp_arb = am.txt_total_idp_arb if am.txt_total_idp_arb > 0.03 else 0
                thTotal = 0
                thTotal = am.txt_total_bien_cpa + am.txt_total_servicio_cpa + am.txt_total_ie_bien_cpa + am.txt_total_ie_servicio_cpa + am.txt_exter_ie_exen_bien + am.txt_exter_ie_exen_serv + am.txt_local_bien_pq + am.txt_local_serv_pq + thSuma_txt_total_idp_arb + am.txt_sum_iva_asiste
                worksheet.write(x_rows, 22, format(thTotal, ".2f"), detail_right_nb)
                x_debe_haber[12] += thTotal
                x_rows += 1
                x_row_page += 1
                x_recorre += 1
            if x_row_page == x_max_rows:
                worksheet.write(x_rows, 9, 'VAN', frmt_encabezado)
                worksheet.write(x_rows, 10, x_debe_haber[0], detail_right_nb_b)
                worksheet.write(x_rows, 11, x_debe_haber[1], detail_right_nb_b)
                worksheet.write(x_rows, 12, x_debe_haber[2], detail_right_nb_b)
                worksheet.write(x_rows, 13, x_debe_haber[3], detail_right_nb_b)
                worksheet.write(x_rows, 14, x_debe_haber[4], detail_right_nb_b)
                worksheet.write(x_rows, 15, x_debe_haber[5], detail_right_nb_b)
                worksheet.write(x_rows, 16, x_debe_haber[6], detail_right_nb_b)
                worksheet.write(x_rows, 17, x_debe_haber[7], detail_right_nb_b)
                worksheet.write(x_rows, 18, x_debe_haber[8], detail_right_nb_b)
                worksheet.write(x_rows, 19, x_debe_haber[9], detail_right_nb_b)
                worksheet.write(x_rows, 20, x_debe_haber[10], detail_right_nb_b)
                worksheet.write(x_rows, 21, x_debe_haber[11], detail_right_nb_b)
                worksheet.write(x_rows, 22, x_debe_haber[12], detail_right_nb_b)
                x_rows += 1
                x_row_page = 0
                x_page += 1
            if x_row_page == 0:  # Nueva pagina
                worksheet.write(x_rows, 22, "Folio: " + str(self.folio + x_page), frmt_folio)
                x_rows += 1
                x_row_page += 1

                worksheet.merge_range(x_rows, 0, x_rows, 22, 'LIBRO DE COMPRAS Y SERVICIOS',
                                      frmt_encabezado)  # Encabezado
                x_rows += 1
                x_row_page += 1

                worksheet.merge_range(x_rows, 0, x_rows, 22, self.company_id.name, frmt_encabezado)  # Encabezado
                x_rows += 1
                x_row_page += 1

                worksheet.merge_range(x_rows, 0, x_rows, 22, "NIT: " + self.company_id.partner_id.vat,
                                      frmt_encabezado)  # Encabezado
                x_rows += 1
                x_row_page += 1

                worksheet.merge_range(x_rows, 0, x_rows, 22,
                                      str("Del " + str(self.start_date.day) + " de " + thMes + " de " + str(
                                          self.start_date.year) +
                                          " Al " + str(self.end_date.day) + " de " + thMesa + " de " + str(
                                          self.end_date.year)), frmt_encabezado)  # Encabezado
                x_rows += 2
                x_row_page += 2

                worksheet.merge_range(x_rows, 0, x_rows + 2, 0, 'Fecha', frmt_encabezado_columna)
                worksheet.merge_range(x_rows, 1, x_rows + 2, 1, 'Establecimiento', frmt_encabezado_columna)
                worksheet.merge_range(x_rows, 2, x_rows + 2, 2, 'Tipo de Transacción', frmt_encabezado_columna)
                worksheet.merge_range(x_rows, 3, x_rows + 2, 3, 'Tipo de Documento', frmt_encabezado_columna)
                worksheet.merge_range(x_rows, 4, x_rows + 2, 4, 'Estado', frmt_encabezado_columna)
                worksheet.merge_range(x_rows, 5, x_rows + 2, 5, 'Referencia Interna', frmt_encabezado_columna)
                worksheet.merge_range(x_rows, 6, x_rows + 2, 6, 'Serie', frmt_encabezado_columna)
                worksheet.merge_range(x_rows, 7, x_rows + 2, 7, 'Numero', frmt_encabezado_columna)
                worksheet.merge_range(x_rows, 8, x_rows + 2, 8, 'NIT', frmt_encabezado_columna)
                worksheet.merge_range(x_rows, 9, x_rows + 2, 9, 'Nombre', frmt_encabezado_columna)
                worksheet.merge_range(x_rows, 10, x_rows, 13, 'Local', frmt_encabezado_columna)
                worksheet.merge_range(x_rows + 1, 10, x_rows + 1, 11, 'Gravadas', frmt_encabezado_columna)
                worksheet.merge_range(x_rows + 1, 12, x_rows + 1, 13, 'Exentas/No Afectas', frmt_encabezado_columna)
                worksheet.write(x_rows + 2, 10, 'Bienes', frmt_encabezado_columna)
                worksheet.write(x_rows + 2, 11, 'Servicios', frmt_encabezado_columna)
                worksheet.write(x_rows + 2, 12, 'Bienes', frmt_encabezado_columna)
                worksheet.write(x_rows + 2, 13, 'Servicios', frmt_encabezado_columna)
                worksheet.merge_range(x_rows, 14, x_rows, 17, 'Importación', frmt_encabezado_columna)
                worksheet.merge_range(x_rows + 1, 14, x_rows + 1, 15, 'Gravadas', frmt_encabezado_columna)
                worksheet.merge_range(x_rows + 1, 16, x_rows + 1, 17, 'Exentas/No Afectas', frmt_encabezado_columna)
                worksheet.write(x_rows + 2, 14, 'Bienes', frmt_encabezado_columna)
                worksheet.write(x_rows + 2, 15, 'Servicios', frmt_encabezado_columna)
                worksheet.write(x_rows + 2, 16, 'Bienes', frmt_encabezado_columna)
                worksheet.write(x_rows + 2, 17, 'Servicios', frmt_encabezado_columna)
                worksheet.merge_range(x_rows, 18, x_rows + 1, 19, 'Pequeño Contribuyente', frmt_encabezado_columna)
                worksheet.write(x_rows + 2, 18, 'Bienes', frmt_encabezado_columna)
                worksheet.write(x_rows + 2, 19, 'Servicios', frmt_encabezado_columna)
                worksheet.merge_range(x_rows, 20, x_rows + 2, 20, 'IDP / Otros Arbitrios', frmt_encabezado_columna)
                worksheet.merge_range(x_rows, 21, x_rows + 2, 21, 'IVA', frmt_encabezado_columna)
                worksheet.merge_range(x_rows, 22, x_rows + 2, 22, 'TOTAL', frmt_encabezado_columna)
                x_rows += 3
                x_row_page += 3
                if x_page > 0:
                    worksheet.write(x_rows, 9, 'VIENEN', frmt_encabezado)
                    worksheet.write(x_rows, 10, x_debe_haber[0], detail_right_nb_b)
                    worksheet.write(x_rows, 11, x_debe_haber[1], detail_right_nb_b)
                    worksheet.write(x_rows, 12, x_debe_haber[2], detail_right_nb_b)
                    worksheet.write(x_rows, 13, x_debe_haber[3], detail_right_nb_b)
                    worksheet.write(x_rows, 14, x_debe_haber[4], detail_right_nb_b)
                    worksheet.write(x_rows, 15, x_debe_haber[5], detail_right_nb_b)
                    worksheet.write(x_rows, 16, x_debe_haber[6], detail_right_nb_b)
                    worksheet.write(x_rows, 17, x_debe_haber[7], detail_right_nb_b)
                    worksheet.write(x_rows, 18, x_debe_haber[8], detail_right_nb_b)
                    worksheet.write(x_rows, 19, x_debe_haber[9], detail_right_nb_b)
                    worksheet.write(x_rows, 20, x_debe_haber[10], detail_right_nb_b)
                    worksheet.write(x_rows, 21, x_debe_haber[11], detail_right_nb_b)
                    worksheet.write(x_rows, 22, x_debe_haber[12], detail_right_nb_b)
                    x_rows += 1
                    x_row_page += 1

            worksheet.write(x_rows, 9, 'TOTALES', frmt_encabezado)
            worksheet.write(x_rows, 10, x_debe_haber[0], detail_right_nb_b)
            worksheet.write(x_rows, 11, x_debe_haber[1], detail_right_nb_b)
            worksheet.write(x_rows, 12, x_debe_haber[2], detail_right_nb_b)
            worksheet.write(x_rows, 13, x_debe_haber[3], detail_right_nb_b)
            worksheet.write(x_rows, 14, x_debe_haber[4], detail_right_nb_b)
            worksheet.write(x_rows, 15, x_debe_haber[5], detail_right_nb_b)
            worksheet.write(x_rows, 16, x_debe_haber[6], detail_right_nb_b)
            worksheet.write(x_rows, 17, x_debe_haber[7], detail_right_nb_b)
            worksheet.write(x_rows, 18, x_debe_haber[8], detail_right_nb_b)
            worksheet.write(x_rows, 19, x_debe_haber[9], detail_right_nb_b)
            worksheet.write(x_rows, 20, x_debe_haber[10], detail_right_nb_b)
            worksheet.write(x_rows, 21, x_debe_haber[11], detail_right_nb_b)
            worksheet.write(x_rows, 22, x_debe_haber[12], detail_right_nb_b)
            x_rows += 2
            x_row_page += 2

            x_rows = x_rows + (x_max_rows - x_row_page) + 1
            x_row_page = 0
            x_page += 1
            worksheet.write(x_rows, 22, "Folio: " + str(self.folio + x_page), frmt_folio)
            x_rows += 1
            x_row_page += 1

            worksheet.merge_range(x_rows, 0, x_rows, 22, 'LIBRO DE COMPRAS Y SERVICIOS',
                                  frmt_encabezado)  # Encabezado
            x_rows += 1
            x_row_page += 1

            worksheet.merge_range(x_rows, 0, x_rows, 22, self.company_id.name, frmt_encabezado)  # Encabezado
            x_rows += 1
            x_row_page += 1

            worksheet.merge_range(x_rows, 0, x_rows, 22, "NIT: " + self.company_id.partner_id.vat,
                                  frmt_encabezado)  # Encabezado
            x_rows += 1
            x_row_page += 1

            worksheet.merge_range(x_rows, 0, x_rows, 22,
                                  str("Del " + str(self.start_date.day) + " de " + thMes + " de " + str(
                                      self.start_date.year) +
                                      " Al " + str(self.end_date.day) + " de " + thMesa + " de " + str(
                                      self.end_date.year)), frmt_encabezado)  # Encabezado
            x_rows += 2
            x_row_page += 2

            worksheet.merge_range(x_rows, 0, x_rows + 2, 0, 'Fecha', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 1, x_rows + 2, 1, 'Establecimiento', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 2, x_rows + 2, 2, 'Tipo de Transacción', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 3, x_rows + 2, 3, 'Tipo de Documento', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 4, x_rows + 2, 4, 'Estado', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 5, x_rows + 2, 5, 'Referencia Interna', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 6, x_rows + 2, 6, 'Serie', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 7, x_rows + 2, 7, 'Numero', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 8, x_rows + 2, 8, 'NIT', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 9, x_rows + 2, 9, 'Nombre', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 10, x_rows, 13, 'Local', frmt_encabezado_columna)
            worksheet.merge_range(x_rows + 1, 10, x_rows + 1, 11, 'Gravadas', frmt_encabezado_columna)
            worksheet.merge_range(x_rows + 1, 12, x_rows + 1, 13, 'Exentas/No Afectas', frmt_encabezado_columna)
            worksheet.write(x_rows + 2, 10, 'Bienes', frmt_encabezado_columna)
            worksheet.write(x_rows + 2, 11, 'Servicios', frmt_encabezado_columna)
            worksheet.write(x_rows + 2, 12, 'Bienes', frmt_encabezado_columna)
            worksheet.write(x_rows + 2, 13, 'Servicios', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 14, x_rows, 17, 'Importación', frmt_encabezado_columna)
            worksheet.merge_range(x_rows + 1, 14, x_rows + 1, 15, 'Gravadas', frmt_encabezado_columna)
            worksheet.merge_range(x_rows + 1, 16, x_rows + 1, 17, 'Exentas/No Afectas', frmt_encabezado_columna)
            worksheet.write(x_rows + 2, 14, 'Bienes', frmt_encabezado_columna)
            worksheet.write(x_rows + 2, 15, 'Servicios', frmt_encabezado_columna)
            worksheet.write(x_rows + 2, 16, 'Bienes', frmt_encabezado_columna)
            worksheet.write(x_rows + 2, 17, 'Servicios', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 18, x_rows + 1, 19, 'Pequeño Contribuyente', frmt_encabezado_columna)
            worksheet.write(x_rows + 2, 18, 'Bienes', frmt_encabezado_columna)
            worksheet.write(x_rows + 2, 19, 'Servicios', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 20, x_rows + 2, 20, 'IDP / Otros Arbitrios', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 21, x_rows + 2, 21, 'IVA', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 22, x_rows + 2, 22, 'TOTAL', frmt_encabezado_columna)
            x_rows += 3
            x_row_page += 3

            # Resumen
            worksheet.merge_range(x_rows, 5, x_rows, 14, 'Resumen', only_b_b)  # Encabezado
            x_rows += 1
            worksheet.merge_range(x_rows, 5, x_rows, 6, 'Local', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 7, x_rows, 8, 'Importación', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 9, x_rows, 10, 'Pequeño Contribuyente', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 11, x_rows + 1, 11, 'IDP / Otros Arbitrios', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 12, x_rows + 1, 12, 'IVA', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 13, x_rows + 1, 13, 'TOTAL COMBUSTIBLES', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 14, x_rows + 1, 14, 'IDP', frmt_encabezado_columna)
            x_rows += 1
            worksheet.write(x_rows, 5, 'Bienes', frmt_encabezado_columna)
            worksheet.write(x_rows, 6, 'Servicios', frmt_encabezado_columna)
            worksheet.write(x_rows, 7, 'Bienes', frmt_encabezado_columna)
            worksheet.write(x_rows, 8, 'Servicios', frmt_encabezado_columna)
            worksheet.write(x_rows, 9, 'Bienes', frmt_encabezado_columna)
            worksheet.write(x_rows, 10, 'Servicios', frmt_encabezado_columna)
            x_rows += 1

            aux_mes = 1
            while aux_mes <= 12:
                worksheet.write(x_rows, 5, sum(account_move.filtered(lambda x: x.date.month == aux_mes).mapped('txt_total_solo_bienes')), detail_right_b_b)
                worksheet.write(x_rows, 6, sum(account_move.filtered(lambda x: x.date.month == aux_mes).mapped('txt_total_servicio_cpa')), detail_right_b_b)
                worksheet.write(x_rows, 7, sum(account_move.filtered(lambda x: x.date.month == aux_mes).mapped('txt_total_ie_bien_cpa')), detail_right_b_b)
                worksheet.write(x_rows, 8, sum(account_move.filtered(lambda x: x.date.month == aux_mes).mapped('txt_total_ie_servicio_cpa')), detail_right_b_b)
                worksheet.write(x_rows, 9, sum(account_move.filtered(lambda x: x.date.month == aux_mes).mapped('txt_local_bien_pq')), detail_right_b_b)
                worksheet.write(x_rows, 10, sum(account_move.filtered(lambda x: x.date.month == aux_mes).mapped('txt_local_serv_pq')), detail_right_b_b)
                worksheet.write(x_rows, 11, sum(account_move.filtered(lambda x: x.date.month == aux_mes and x.txt_total_idp_arb > 0.03).mapped('txt_total_idp_arb')), detail_right_b_b)
                worksheet.write(x_rows, 12, sum(account_move.filtered(lambda x: x.date.month == aux_mes).mapped('txt_sum_iva_asiste')), detail_right_b_b)
                worksheet.write(x_rows, 13, sum(account_move.filtered(lambda x: x.date.month == aux_mes).mapped('total_facturas_combustibles')), detail_right_b_b)
                worksheet.write(x_rows, 14, sum(account_move.filtered(lambda x: x.date.month == aux_mes).mapped('total_final_idp')), detail_right_b_b)
                aux_mes += 1
                x_rows += 1
            # Resumen

            if self.invoice_ids:
                result = account_move.read_group(
                    domain=[('date', '>=', self.start_date), ('date', '<=', self.end_date), ('state', '=', 'posted'),
                            ('journal_id', '=', self.journal_ids.id), ('invoice_line_ids', 'in', self.invoice_ids.ids)],
                    fields=['tipo_documento'],
                    groupby=['tipo_documento'],
                    lazy=False
                )
            else:
                result = account_move.read_group(
                    domain=[('date', '>=', self.start_date), ('date', '<=', self.end_date), ('state', '=', 'posted'),
                            ('journal_id', '=', self.journal_ids.id)],
                    fields=['tipo_documento'],
                    groupby=['tipo_documento'],
                    lazy=False
                )

            worksheet.merge_range(x_rows, 5, x_rows, 6, 'Documentos Recibidos', frmt_encabezado_columna)
            x_rows += 1
            for res in result:
                worksheet.write(x_rows, 5, res['tipo_documento'] if res.get('tipo_documento') else 'Sin tipo de documento', detail_center_b)
                worksheet.write(x_rows, 6, res['__count'], detail_center_b)
                x_rows += 1
            x_rows += 1
#este es la declaración de las columnas
        else:
            worksheet.write(x_rows, 22, "Folio: " + str(self.folio + x_page), frmt_folio)
            x_rows += 1
            worksheet.merge_range(x_rows, 0, x_rows, 22, 'LIBRO DE COMPRAS Y SERVICIOS',
                                  frmt_encabezado)  # Encabezado
            x_rows += 1
            worksheet.merge_range(x_rows, 0, x_rows, 22, self.company_id.name, frmt_encabezado)  # Encabezado
            x_rows += 1
            worksheet.merge_range(x_rows, 0, x_rows, 22, "NIT: " + self.company_id.partner_id.vat,
                                  frmt_encabezado)  # Encabezado
            x_rows += 1
            worksheet.merge_range(x_rows, 0, x_rows, 22,
                                  str("Del " + str(self.start_date.day) + " de " + thMes + " de " + str(
                                      self.start_date.year) +
                                      " Al " + str(self.end_date.day) + " de " + thMesa + " de " + str(
                                      self.end_date.year)), frmt_encabezado)  # Encabezado
            x_rows += 2
            worksheet.merge_range(x_rows, 0, x_rows + 2, 0, 'Fecha', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 1, x_rows + 2, 1, 'Establecimiento', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 2, x_rows + 2, 2, 'Tipo de Transacción', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 3, x_rows + 2, 3, 'Tipo de Documento', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 4, x_rows + 2, 4, 'Estado', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 5, x_rows + 2, 5, 'Referencia Interna', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 6, x_rows + 2, 6, 'Serie', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 7, x_rows + 2, 7, 'Numero', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 8, x_rows + 2, 8, 'NIT', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 9, x_rows + 2, 9, 'Nombre', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 10, x_rows, 13, 'Local', frmt_encabezado_columna)
            worksheet.merge_range(x_rows + 1, 10, x_rows + 1, 11, 'Gravadas', frmt_encabezado_columna)
            worksheet.merge_range(x_rows + 1, 12, x_rows + 1, 13, 'Exentas/No Afectas', frmt_encabezado_columna)
            worksheet.write(x_rows + 2, 10, 'Bienes', frmt_encabezado_columna)
            worksheet.write(x_rows + 2, 11, 'Servicios', frmt_encabezado_columna)
            worksheet.write(x_rows + 2, 12, 'Bienes', frmt_encabezado_columna)
            worksheet.write(x_rows + 2, 13, 'Servicios', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 14, x_rows, 17, 'Importación', frmt_encabezado_columna)
            worksheet.merge_range(x_rows + 1, 14, x_rows + 1, 15, 'Gravadas', frmt_encabezado_columna)
            worksheet.merge_range(x_rows + 1, 16, x_rows + 1, 17, 'Exentas/No Afectas', frmt_encabezado_columna)
            worksheet.write(x_rows + 2, 14, 'Bienes', frmt_encabezado_columna)
            worksheet.write(x_rows + 2, 15, 'Servicios', frmt_encabezado_columna)
            worksheet.write(x_rows + 2, 16, 'Bienes', frmt_encabezado_columna)
            worksheet.write(x_rows + 2, 17, 'Servicios', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 18, x_rows + 1, 19, 'Pequeño Contribuyente', frmt_encabezado_columna)
            worksheet.write(x_rows + 2, 18, 'Bienes', frmt_encabezado_columna)
            worksheet.write(x_rows + 2, 19, 'Servicios', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 20, x_rows + 2, 20, 'IDP / Otros Arbitrios', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 21, x_rows + 2, 21, 'IVA', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 22, x_rows + 2, 22, 'TOTAL', frmt_encabezado_columna)


        workbook.close()
        self.write({
            'state': 'get',
            #13-02-2024 aqui agregue xls_path
            'data': base64.b64encode(open(xls_path, 'rb').read()),
            'name': xls_filename
        })
        return {
            'name': 'Libro Compras',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new'
        }

class wizard_libro_ventas(models.TransientModel):
    _name = 'wizard.libro.ventas'
    _description = "Wizard Libro de Ventas"
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id)
    start_date = fields.Date(string="Del")
    end_date = fields.Date(string="Al")
    # campo many2many de diarios
    journal_ids = fields.Many2many('account.journal', string='Diarios', required=True, domain="[('type', '=', 'sale')]")
    folio = fields.Integer(string="Folio")
    state = fields.Selection([('choose', 'choose'), ('get', 'get')], default='choose')
    name = fields.Char(string='File Name', readonly=True)
    data = fields.Binary(string='File', readonly=True)

    @api.onchange('company_id')
    def onchange_company_id(self):
        domain = [('id', 'in', self.env.user.company_ids.ids)]
        # if self.company_id:
        # self.warehouse_ids = False
        # self.location_ids = False
        return {'domain': {'company_id': domain}}

    def go_back(self):
        self.state = 'choose'
        return {
            'name': 'Libro de Compras',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new'
        }
    def check_date(self):
        if self.end_date < self.start_date:
            raise ValidationError(_('Fecha A debe ser despues de Fecha Del'))
        if self.start_date.year != self.end_date.year:
            raise ValidationError(_('Las fechas deben ser del mismo año'))

    def print_xls_libro_ventas(self):
        self.check_date()
        thMes = ""
        thMesa = ""
        if self.start_date.month == 1:
            thMes = "Enero"
        elif self.start_date.month == 2:
            thMes = "Febrero"
        elif self.start_date.month == 3:
            thMes = "Marzo"
        elif self.start_date.month == 4:
            thMes = "Abril"
        elif self.start_date.month == 5:
            thMes = "Mayo"
        elif self.start_date.month == 6:
            thMes = "Junio"
        elif self.start_date.month == 7:
            thMes = "Julio"
        elif self.start_date.month == 8:
            thMes = "Agosto"
        elif self.start_date.month == 9:
            thMes = "Septiembre"
        elif self.start_date.month == 10:
            thMes = "Octubre"
        elif self.start_date.month == 11:
            thMes = "Noviembre"
        else:
            thMes = "Diciembre"

        if self.end_date.month == 1:
            thMesa = "Enero"
        elif self.end_date.month == 2:
            thMesa = "Febrero"
        elif self.end_date.month == 3:
            thMesa = "Marzo"
        elif self.end_date.month == 4:
            thMesa = "Abril"
        elif self.end_date.month == 5:
            thMesa = "Mayo"
        elif self.end_date.month == 6:
            thMesa = "Junio"
        elif self.end_date.month == 7:
            thMesa = "Julio"
        elif self.end_date.month == 8:
            thMesa = "Agosto"
        elif self.end_date.month == 9:
            thMesa = "Septiembre"
        elif self.end_date.month == 10:
            thMesa = "Octubre"
        elif self.end_date.month == 11:
            thMesa = "Noviembre"
        else:
            thMesa = "Diciembre"

        xls_filename = 'Libro de Ventas.xlsx'
        temp_dir = tempfile.gettempdir()
        xls_path = os.path.join(temp_dir, xls_filename)
        workbook = xlsxwriter.Workbook(xls_path)

        frmt_encabezado = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'font': 'Arial', 'font_size': 8})
        frmt_encabezado_columna = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'font': 'Arial', 'font_size': 8, 'border': 1, 'bg_color': '#DDEBF7', 'text_wrap': True})
        detail_center_nb = workbook.add_format({'align': 'center', 'font': 'Arial', 'font_size': 8})
        detail_left_nb = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 8})
        detail_right_nb = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 8})
        detail_center_b = workbook.add_format({'bold': True, 'align': 'center', 'font': 'Arial', 'font_size': 10, 'border' : 1, 'text_wrap': True})

        frmt_folio = workbook.add_format({'bold': True, 'align': 'right', 'font': 'Arial', 'font_size': 6})
        detail_right_nb_b = workbook.add_format({'bold': True, 'align': 'right', 'font': 'Arial', 'font_size': 6})


        worksheet = workbook.add_worksheet("Libro de Ventas")
        worksheet.set_landscape()
        worksheet.set_page_view()
        # worksheet.set_paper(1)
        worksheet.set_margins(0.5, 0.5, 0.5, 0.5)
        # Tamaños
        worksheet.set_column('A:A', 7)
        worksheet.set_column('B:B', 7)
        worksheet.set_column('C:C', 7)
        worksheet.set_column('D:D', 7)
        worksheet.set_column('E:E', 7)
        worksheet.set_column('F:F', 7)
        worksheet.set_column('G:G', 7)
        worksheet.set_column('H:H', 21)
        worksheet.set_column('I:I', 7)
        worksheet.set_column('J:J', 7)
        worksheet.set_column('K:K', 7)
        worksheet.set_column('L:L', 7)
        worksheet.set_column('M:M', 7)
        worksheet.set_column('N:N', 7)
        # Empieza detalle
        x_rows = 0  # Linea a imprimir
        x_max_rows = 35
        x_row_page = 0
        x_page = 0
        x_debe_haber = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        aux_mes = 1
        account_move = self.env['account.move'].search([
            ('company_id.id', '=', self.company_id.id),
            ('state', 'in', ['cancel', 'posted']),
            ('date', '>=', self.start_date),
            ('date', '<=', self.end_date),
            #('journal_id.id', 'in', [146, 132])], order="date desc")
            ('journal_id.id', 'in', self.journal_ids.ids)], order="date desc")

        if account_move:
            x_rows = 0
            for am in account_move:
                if x_row_page == x_max_rows:
                    worksheet.write(x_rows, 7, 'VAN', frmt_encabezado)
                    worksheet.write(x_rows, 8, x_debe_haber[0], detail_right_nb_b)
                    worksheet.write(x_rows, 9, x_debe_haber[1], detail_right_nb_b)
                    worksheet.write(x_rows, 10, x_debe_haber[2], detail_right_nb_b)
                    worksheet.write(x_rows, 11, x_debe_haber[3], detail_right_nb_b)
                    worksheet.write(x_rows, 12, x_debe_haber[4], detail_right_nb_b)
                    worksheet.write(x_rows, 13, x_debe_haber[5], detail_right_nb_b)
                    x_rows += 1
                    x_row_page = 0
                    x_page += 1
                # ---------------------------- Encabezado ----------------------------------------------------------
                if x_row_page == 0:  # Nueva pagina
                    worksheet.write(x_rows, 13, "Folio: " + str(self.folio + x_page), frmt_folio)
                    x_rows += 1
                    x_row_page += 1

                    worksheet.merge_range(x_rows, 0, x_rows, 13, 'LIBRO DE VENTAS Y SERVICIOS', frmt_encabezado)  # Encabezado
                    x_rows += 1
                    x_row_page += 1

                    worksheet.merge_range(x_rows, 0, x_rows, 13, self.company_id.name, frmt_encabezado)  # Encabezado
                    x_rows += 1
                    x_row_page += 1

                    worksheet.merge_range(x_rows, 0, x_rows, 13, "NIT: " + self.company_id.partner_id.vat, frmt_encabezado)  # Encabezado
                    x_rows += 1
                    x_row_page += 1

                    worksheet.merge_range(x_rows, 0, x_rows, 13, str("Del " + str(self.start_date.day) + " de " + thMes + " de " + str(self.start_date.year) +
                                                                    " Al " + str(self.end_date.day) + " de " + thMesa + " de " + str(self.end_date.year)), frmt_encabezado)  # Encabezado
                    x_rows += 2
                    x_row_page += 2

                    worksheet.merge_range(x_rows, 8, x_rows, 9, 'LOCAL', frmt_encabezado_columna)
                    worksheet.merge_range(x_rows, 10, x_rows, 11, 'EXPORTACION', frmt_encabezado_columna)
                    x_rows += 1
                    x_row_page += 1

                    worksheet.write(x_rows, 0, 'Fecha', frmt_encabezado_columna)
                    worksheet.write(x_rows, 1, 'Establecimiento', frmt_encabezado_columna)
                    worksheet.write(x_rows, 2, 'Tipo', frmt_encabezado_columna)
                    worksheet.write(x_rows, 3, 'Estado', frmt_encabezado_columna)
                    worksheet.write(x_rows, 4, 'Serie', frmt_encabezado_columna)
                    worksheet.write(x_rows, 5, 'Número', frmt_encabezado_columna)
                    worksheet.write(x_rows, 6, 'NIT', frmt_encabezado_columna)
                    worksheet.write(x_rows, 7, 'Nombre', frmt_encabezado_columna)
                    worksheet.write(x_rows, 8, 'Bienes', frmt_encabezado_columna)
                    worksheet.write(x_rows, 9, 'Servicios', frmt_encabezado_columna)
                    worksheet.write(x_rows, 10, 'Bienes', frmt_encabezado_columna)
                    worksheet.write(x_rows, 11, 'Servicios', frmt_encabezado_columna)
                    worksheet.write(x_rows, 12, 'IVA Débito Fiscal', frmt_encabezado_columna)
                    worksheet.write(x_rows, 13, 'Total Documento', frmt_encabezado_columna)
                    x_rows += 1
                    x_row_page += 1
                    if x_page > 0:
                        worksheet.write(x_rows, 7, 'VIENEN', frmt_encabezado)
                        worksheet.write(x_rows, 8, x_debe_haber[0], detail_right_nb_b)
                        worksheet.write(x_rows, 9, x_debe_haber[1], detail_right_nb_b)
                        worksheet.write(x_rows, 10, x_debe_haber[2], detail_right_nb_b)
                        worksheet.write(x_rows, 11, x_debe_haber[3], detail_right_nb_b)
                        worksheet.write(x_rows, 12, x_debe_haber[4], detail_right_nb_b)
                        worksheet.write(x_rows, 13, x_debe_haber[5], detail_right_nb_b)
                        x_rows += 1
                        x_row_page += 1
                worksheet.write(x_rows, 0, am.date.strftime('%d-%m-%Y'), detail_center_nb)
                worksheet.write(x_rows, 1, am.journal_id.codigo_establecimiento, detail_center_nb)
                worksheet.write(x_rows, 2, am.tipo_documento, detail_center_nb)
                worksheet.write(x_rows, 3, am.estado_factura, detail_center_nb)
                worksheet.write(x_rows, 4, am.serie_fel, detail_center_nb)
                worksheet.write(x_rows, 5, am.numero_fel, detail_center_nb)
                worksheet.write(x_rows, 6, am.partner_id.vat, detail_left_nb)
                worksheet.write(x_rows, 7, am.partner_id.name, detail_left_nb)
                worksheet.write(x_rows, 8, am.total_bien_s_iva, detail_right_nb)
                x_debe_haber[0] += am.total_bien_s_iva
                worksheet.write(x_rows, 9, am.total_serv_s_iva, detail_right_nb)
                x_debe_haber[1] += am.total_serv_s_iva
                worksheet.write(x_rows, 10, am.total_ie_bien_s_iva, detail_right_nb)
                x_debe_haber[2] += am.total_ie_bien_s_iva
                worksheet.write(x_rows, 11, am.total_ie_serv_s_iva, detail_right_nb)
                x_debe_haber[3] += am.total_ie_serv_s_iva
                worksheet.write(x_rows, 12, am.txt_sum_iva_asiste, detail_right_nb)
                x_debe_haber[4] += am.txt_sum_iva_asiste
                worksheet.write(x_rows, 13,
                                am.total_bien_s_iva +
                                am.total_serv_s_iva +
                                am.total_ie_bien_s_iva +
                                am.total_ie_serv_s_iva +
                                am.txt_sum_iva_asiste, detail_right_nb)
                x_debe_haber[5] += am.total_bien_s_iva + am.total_serv_s_iva + am.total_ie_bien_s_iva + am.total_ie_serv_s_iva + am.txt_sum_iva_asiste
                x_rows += 1
                x_row_page += 1
            if x_row_page == x_max_rows:
                worksheet.write(x_rows, 7, 'VAN', frmt_encabezado)
                worksheet.write(x_rows, 8, x_debe_haber[0], detail_right_nb_b)
                worksheet.write(x_rows, 9, x_debe_haber[1], detail_right_nb_b)
                worksheet.write(x_rows, 10, x_debe_haber[2], detail_right_nb_b)
                worksheet.write(x_rows, 11, x_debe_haber[3], detail_right_nb_b)
                worksheet.write(x_rows, 12, x_debe_haber[4], detail_right_nb_b)
                worksheet.write(x_rows, 13, x_debe_haber[5], detail_right_nb_b)
                x_rows += 1
                x_row_page = 0
                x_page += 1
            # ---------------------------- Encabezado ----------------------------------------------------------
            if x_row_page == 0:  # Nueva pagina
                worksheet.write(x_rows, 13, "Folio: " + str(self.folio + x_page), frmt_folio)
                x_rows += 1
                x_row_page += 1

                worksheet.merge_range(x_rows, 0, x_rows, 13, 'LIBRO DE VENTAS Y SERVICIOS',
                                      frmt_encabezado)  # Encabezado
                x_rows += 1
                x_row_page += 1

                worksheet.merge_range(x_rows, 0, x_rows, 13, self.company_id.name, frmt_encabezado)  # Encabezado
                x_rows += 1
                x_row_page += 1

                worksheet.merge_range(x_rows, 0, x_rows, 13, "NIT: " + self.company_id.partner_id.vat,
                                      frmt_encabezado)  # Encabezado
                x_rows += 1
                x_row_page += 1

                worksheet.merge_range(x_rows, 0, x_rows, 13,
                                      str("Del " + str(self.start_date.day) + " de " + thMes + " de " + str(
                                          self.start_date.year) +
                                          " Al " + str(self.end_date.day) + " de " + thMesa + " de " + str(
                                          self.end_date.year)), frmt_encabezado)  # Encabezado
                x_rows += 2
                x_row_page += 2

                worksheet.merge_range(x_rows, 8, x_rows, 9, 'LOCAL', frmt_encabezado_columna)
                worksheet.merge_range(x_rows, 10, x_rows, 11, 'EXPORTACION', frmt_encabezado_columna)
                x_rows += 1
                x_row_page += 1

                worksheet.write(x_rows, 0, 'Fecha', frmt_encabezado_columna)
                worksheet.write(x_rows, 1, 'Establecimiento', frmt_encabezado_columna)
                worksheet.write(x_rows, 2, 'Tipo', frmt_encabezado_columna)
                worksheet.write(x_rows, 3, 'Estado', frmt_encabezado_columna)
                worksheet.write(x_rows, 4, 'Serie', frmt_encabezado_columna)
                worksheet.write(x_rows, 5, 'Número', frmt_encabezado_columna)
                worksheet.write(x_rows, 6, 'NIT', frmt_encabezado_columna)
                worksheet.write(x_rows, 7, 'Nombre', frmt_encabezado_columna)
                worksheet.write(x_rows, 8, 'Bienes', frmt_encabezado_columna)
                worksheet.write(x_rows, 9, 'Servicios', frmt_encabezado_columna)
                worksheet.write(x_rows, 10, 'Bienes', frmt_encabezado_columna)
                worksheet.write(x_rows, 11, 'Servicios', frmt_encabezado_columna)
                worksheet.write(x_rows, 12, 'IVA Débito Fiscal', frmt_encabezado_columna)
                worksheet.write(x_rows, 13, 'Total Documento', frmt_encabezado_columna)
                x_rows += 1
                x_row_page += 1
                if x_page > 0:
                    worksheet.write(x_rows, 7, 'VIENEN', frmt_encabezado)
                    worksheet.write(x_rows, 8, x_debe_haber[0], detail_right_nb_b)
                    worksheet.write(x_rows, 9, x_debe_haber[1], detail_right_nb_b)
                    worksheet.write(x_rows, 10, x_debe_haber[2], detail_right_nb_b)
                    worksheet.write(x_rows, 11, x_debe_haber[3], detail_right_nb_b)
                    worksheet.write(x_rows, 12, x_debe_haber[4], detail_right_nb_b)
                    worksheet.write(x_rows, 13, x_debe_haber[5], detail_right_nb_b)
                    x_rows += 1
                    x_row_page += 1
            worksheet.write(x_rows, 7, 'TOTALES', frmt_encabezado)
            worksheet.write(x_rows, 8, x_debe_haber[0], detail_right_nb_b)
            worksheet.write(x_rows, 9, x_debe_haber[1], detail_right_nb_b)
            worksheet.write(x_rows, 10, x_debe_haber[2], detail_right_nb_b)
            worksheet.write(x_rows, 11, x_debe_haber[3], detail_right_nb_b)
            worksheet.write(x_rows, 12, x_debe_haber[4], detail_right_nb_b)
            worksheet.write(x_rows, 13, x_debe_haber[5], detail_right_nb_b)
            x_rows += 1
            x_row_page = 0

            result = account_move.read_group(
                domain=[('date', '>=', self.start_date), ('date', '<=', self.end_date), ('state', '=', 'posted'),
                        ('journal_id', '=', self.journal_ids.id)],
                fields=['tipo_documento'],
                groupby=['tipo_documento'],
                lazy=False
            )

            #worksheet.merge_range(x_rows, 5, x_rows, 6, 'Documentos Recibidos', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 5, x_rows, 6, 'Documentos Emitidos', frmt_encabezado_columna)
            x_rows += 1
            for res in result:
                worksheet.write(x_rows, 5, res['tipo_documento'] if res.get('tipo_documento') else 'Sin tipo de documento', detail_center_b)
                worksheet.write(x_rows, 6, res['__count'], detail_center_b)
                x_rows += 1

        else:
            worksheet.write(x_rows, 13, "Folio: " + str(self.folio + x_page), frmt_folio)
            x_rows += 1
            x_row_page += 1
            worksheet.merge_range(x_rows, 0, x_rows, 13, 'LIBRO DE VENTAS Y SERVICIOS', frmt_encabezado)  # Encabezado
            x_rows += 1
            x_row_page += 1
            worksheet.merge_range(x_rows, 0, x_rows, 13, self.company_id.name, frmt_encabezado)  # Encabezado
            x_rows += 1
            x_row_page += 1
            worksheet.merge_range(x_rows, 0, x_rows, 13, "NIT: " + self.company_id.partner_id.vat,
                                  frmt_encabezado)  # Encabezado
            x_rows += 1
            x_row_page += 1
            worksheet.merge_range(x_rows, 0, x_rows, 13,
                                  str("Del " + str(self.start_date.day) + " de " + thMes + " de " + str(
                                      self.start_date.year) +
                                      " Al " + str(self.end_date.day) + " de " + thMesa + " de " + str(
                                      self.end_date.year)), frmt_encabezado)  # Encabezado
            x_rows += 2
            x_row_page += 2

            worksheet.merge_range(x_rows, 8, x_rows, 9, 'LOCAL', frmt_encabezado_columna)
            worksheet.merge_range(x_rows, 10, x_rows, 11, 'EXPORTACION', frmt_encabezado_columna)
            x_rows += 1
            x_row_page += 1

            worksheet.write(x_rows, 0, 'Fecha', frmt_encabezado_columna)
            worksheet.write(x_rows, 1, 'Establecimiento', frmt_encabezado_columna)
            worksheet.write(x_rows, 2, 'Tipo', frmt_encabezado_columna)
            worksheet.write(x_rows, 3, 'Estado', frmt_encabezado_columna)
            worksheet.write(x_rows, 4, 'Serie', frmt_encabezado_columna)
            worksheet.write(x_rows, 5, 'Número', frmt_encabezado_columna)
            worksheet.write(x_rows, 6, 'NIT', frmt_encabezado_columna)
            worksheet.write(x_rows, 7, 'Nombre', frmt_encabezado_columna)
            worksheet.write(x_rows, 8, 'Bienes', frmt_encabezado_columna)
            worksheet.write(x_rows, 9, 'Servicios', frmt_encabezado_columna)
            worksheet.write(x_rows, 10, 'Bienes', frmt_encabezado_columna)
            worksheet.write(x_rows, 11, 'Servicios', frmt_encabezado_columna)
            worksheet.write(x_rows, 12, 'IVA Débito Fiscal', frmt_encabezado_columna)
            worksheet.write(x_rows, 13, 'Total Documento', frmt_encabezado_columna)
            x_rows += 5
            x_row_page += 1

            worksheet.merge_range(x_rows, 5, x_rows, 6, 'Documentos Emitidos', frmt_encabezado_columna)
            x_rows += 1
            worksheet.write(x_rows, 5, 'Sin tipo de documento', detail_center_b)
            worksheet.write(x_rows, 6, '0', detail_center_b)

        workbook.close()
        self.write({
            'state': 'get',
            'data': base64.b64encode(open(xls_path, 'rb').read()),
            'name': xls_filename
        })
        return {
            'name': 'Libro Ventas',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new'
        }

class wizard_flujo_efectivo(models.TransientModel):
    _name = 'wizard.flujo.efectivo'
    _description = "Wizard Flujo de efectivo"
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id)
    start_date = fields.Date(string="Fecha Inicio")
    end_date = fields.Date(string="Fecha Fin")

    anio = fields.Integer(string="Año")
    mes_de = fields.Selection([('1','Enero'),('2','Febrero'),('3','Marzo'),('4','Abril'),('5','Mayo'),('6','Junio'),('7','Julio'),('8','Agosto'),('9','Septiembre'),('10','Octubre'),('11','Noviembre'),('12','Diciembre')],string="De")
    mes_a = fields.Selection(
        [('1', 'Enero'), ('2', 'Febrero'), ('3', 'Marzo'), ('4', 'Abril'), ('5', 'Mayo'), ('6', 'Junio'),
         ('7', 'Julio'), ('8', 'Agosto'), ('9', 'Septiembre'), ('10', 'Octubre'), ('11', 'Noviembre'),
         ('12', 'Diciembre')], string="A")
    folio = fields.Integer(string="Folio")
    certificacion = fields.Char(string="Certificación")
    representante = fields.Char(string="Representante Legal")
    contador = fields.Char(string="Contador")
    filter_by = fields.Selection([('product', 'Product'), ('category', 'Category')], string="Filter By")
    group_by_categ = fields.Boolean(string="Group By Category")
    state = fields.Selection([('choose', 'choose'), ('get', 'get')], default='choose')
    name = fields.Char(string='File Name', readonly=True)
    data = fields.Binary(string='File', readonly=True)
    product_ids = fields.Many2many('product.product', string="Products")
    category_ids = fields.Many2many('product.category', string="Categories")
    # Columnas para el reporte


    @api.onchange('company_id')
    def onchange_company_id(self):
        domain = [('id', 'in', self.env.user.company_ids.ids)]
        # if self.company_id:
            # self.warehouse_ids = False
            # self.location_ids = False
        return {'domain':{'company_id':domain}}

    def check_date_range(self):
        if self.end_date < self.start_date:
            raise ValidationError(_('Fecha fin ser posterior a fecha inicio.'))

    def check_mes(self):
        if int(self.mes_de) > int(self.mes_a):
            raise ValidationError(_('Mes De debe ser anterior a mes A.'))

    @api.onchange('filter_by')
    def onchange_filter_by(self):
        self.product_ids = False
        self.category_ids = False

    def print_report(self):
        self.check_date_range()
        datas = {'form':
                    {
                        'company_id': self.company_id.id,
                        'warehouse_ids': [y.id for y in self.warehouse_ids],
                        'location_ids': self.location_ids.ids or False,
                        'start_date': self.start_date,
                        'end_date': self.end_date,
                        'id': self.id,
                        'product_ids': self.product_ids.ids,
                        'product_categ_ids': self.category_ids.ids
                    },
                }
        return self.env.ref('account_report_financial.action_report_financial_template').report_action(self, data=datas)

    def go_back(self):
        self.state = 'choose'
        return {
            'name': 'Report Financial Estado Resultados',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new'
        }

    def print_xls_flujo_efectivo(self):

        thMes = ""
        thMesa = ""
        if self.start_date.month == 1:
            thMes = "Enero"
        elif self.start_date.month == 2:
            thMes = "Febrero"
        elif self.start_date.month == 3:
            thMes = "Marzo"
        elif self.start_date.month == 4:
            thMes = "Abril"
        elif self.start_date.month == 5:
            thMes = "Mayo"
        elif self.start_date.month == 6:
            thMes = "Junio"
        elif self.start_date.month == 7:
            thMes = "Julio"
        elif self.start_date.month == 8:
            thMes = "Agosto"
        elif self.start_date.month == 9:
            thMes = "Septiembre"
        elif self.start_date.month == 10:
            thMes = "Octubre"
        elif self.start_date.month == 11:
            thMes = "Noviembre"
        else:
            thMes = "Diciembre"

        if self.end_date.month == 1:
            thMesa = "Enero"
        elif self.end_date.month == 2:
            thMesa = "Febrero"
        elif self.end_date.month == 3:
            thMesa = "Marzo"
        elif self.end_date.month == 4:
            thMesa = "Abril"
        elif self.end_date.month == 5:
            thMesa = "Mayo"
        elif self.end_date.month == 6:
            thMesa = "Junio"
        elif self.end_date.month == 7:
            thMesa = "Julio"
        elif self.end_date.month == 8:
            thMesa = "Agosto"
        elif self.end_date.month == 9:
            thMesa = "Septiembre"
        elif self.end_date.month == 10:
            thMesa = "Octubre"
        elif self.end_date.month == 11:
            thMesa = "Noviembre"
        else:
            thMesa = "Diciembre"

        self.check_date_range()
        #self.check_mes()
        #company_id = self.env['res.company'].browse(self._context.get('allowed_company_ids'))
        xls_filename = 'Flujo de Efectivo.xlsx'
        temp_dir = tempfile.gettempdir()
        xls_path = os.path.join(temp_dir, xls_filename)
        workbook = xlsxwriter.Workbook(xls_path)
        #workbook = xlsxwriter.Workbook('/tmp/' + xls_filename)

        frmt_folio = workbook.add_format({'bold': False, 'align': 'right', \
                                          'font': 'Arial', 'font_size': 10})
        frmt_encabezado = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                               'font': 'Arial', 'font_size': 10})
        frmt_borde_superior = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                                   'font': 'Arial', 'font_size': 10})
        frmt_cuenta = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 10})
        frmt_van_vacio = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 10})
        frmt_van_vacio_i = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 10})
        frmt_van_vacio_ii = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 10})
        frmt_codigo = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'bold': True})
        frmt_titulos = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 10, 'bold': True})
        debe_haber_vacio = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10})
        debe_haber = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'num_format': 'Q#,##0.00'})
        debe_haber_bold = workbook.add_format({'bold' : True, 'align': 'right', 'font': 'Arial', 'font_size': 10, 'num_format': 'Q#,##0.00'})
        debe_haber_bold_total = workbook.add_format(
            {'bold': True, 'align': 'right', 'font': 'Arial', 'font_size': 10, 'num_format': 'Q#,##0.00'})
        debe_haber_van_vienen = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'bold' : True, 'border' : 1, 'num_format': 'Q#,##0.00'})

        frmt_van_q = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                                      'font': 'Arial', 'font_size': 10, 'num_format': 'Q#,##0.00'})
        frmt_firma = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                               'font': 'Arial', 'font_size': 10})
        frmt_titulos.set_left(1)
        debe_haber_bold.set_right(1)
        debe_haber_bold.set_left(1)
        debe_haber_bold_total.set_left(1)
        debe_haber_bold_total.set_right(1)
        debe_haber_bold_total.set_top(1)

        frmt_borde_superior.set_bottom(1)
        frmt_cuenta.set_right(1)
        debe_haber_vacio.set_left(1)
        debe_haber_vacio.set_right(1)
        debe_haber.set_left(1)
        debe_haber.set_right(1)

        frmt_van_vacio.set_left(1)
        frmt_van_vacio.set_top(1)
        frmt_van_vacio.set_bottom(1)
        frmt_van_vacio_i.set_top(1)
        frmt_van_vacio_i.set_bottom(1)
        frmt_van_vacio_ii.set_right(1)
        frmt_van_vacio_ii.set_top(1)
        frmt_van_vacio_ii.set_bottom(1)

        worksheet = workbook.add_worksheet("Flujo de Efectivo")
        worksheet.set_portrait()
        worksheet.set_page_view()
        worksheet.set_paper(1)
        worksheet.set_margins(0.7, 0.7, 0.7, 0.7)
        # Tamaños
        worksheet.set_column('A:A', 5)
        worksheet.set_column('B:B', 10)
        worksheet.set_column('C:C', 35)
        worksheet.set_column('D:D', 15)
        worksheet.set_column('E:E', 15)
        # Empieza detalle
        x_rows = 0 # Linea a imprimir
        x_page = 0 # Numero de pagina
        x_max_rows = 47 # Maximo de lineas por pagina
        x_row_page = 0 # Linea actual vrs maximo de lineas
        x_ctrl_nivel_i = ''
        x_ctrl_nivel_ii = ''
        x_cuentas = None
        x_altura = 0
        x_recorre = 0
        x_suma_debe = 0
        x_suma_haber = 0
        x_iteracion = 0
        x_NiveliInicial = 1 # Aca empezamos desde la cuenta 1
        x_NiveliFinal = int(self.env['account.group'].search([
                                                            ('company_id.id', '=', self.company_id.id),
                                                            ('parent_id', '=', False),
                                                            ], order="code_prefix_start desc", limit=1).mapped('code_prefix_start')[0])
        x_SubGranTotal = 0
        x_AumentoDisminucion = 0

        a_imprimir = []
        # Calculo de la utilidad del ejercicio
        x_balance_4 = 0
        x_balance_4 = sum(self.env['account.move.line'].search([
            ('account_id.group_id.parent_id.parent_id.code_prefix_start', '=', '4'),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', self.start_date),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id),
            ('journal_id.name', '!=', 'Partida de Cierre')]).mapped('balance')) * -1
        x_balance_5 = 0
        x_balance_5 = sum(self.env['account.move.line'].search([
            ('account_id.group_id.parent_id.parent_id.code_prefix_start', '=', '5'),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', self.start_date),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id),
            ('journal_id.name', '!=', 'Partida de Cierre')]).mapped('balance'))
        x_balance_6 = 0
        x_balance_6 = sum(self.env['account.move.line'].search([
            ('account_id.group_id.parent_id.parent_id.code_prefix_start', '=', '6'),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', self.start_date),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id),
            ('journal_id.name', '!=', 'Partida de Cierre')]).mapped('balance'))
        x_balance_7 = 0
        x_balance_7 = sum(self.env['account.move.line'].search([
            ('account_id.group_id.parent_id.parent_id.code_prefix_start', '=', '7'),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', self.start_date),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id),
            ('journal_id.name', '!=', 'Partida de Cierre')]).mapped('balance'))*-1
        x_balance_8 = 0
        x_balance_8 = sum(self.env['account.move.line'].search([
            ('account_id.group_id.parent_id.parent_id.code_prefix_start', '=', '8'),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', self.start_date),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id),
            ('journal_id.name', '!=', 'Partida de Cierre')]).mapped('balance'))

        a_imprimir.append([])
        a_imprimir[x_altura].append('head_total')
        a_imprimir[x_altura].append('actividades_operacion')
        a_imprimir[x_altura].append('RESULTADO DEL EJERCICIO')
        a_imprimir[x_altura].append('')
        a_imprimir[x_altura].append('')
        a_imprimir[x_altura].append(0)
        a_imprimir[x_altura].append((x_balance_4 - x_balance_5 - x_balance_6) + x_balance_7 - x_balance_8)
        x_altura += 1

        a_imprimir.append([])
        a_imprimir[x_altura].append('head')
        a_imprimir[x_altura].append('actividades_operacion')
        a_imprimir[x_altura].append('GASTOS QUE NO REQUIEREN DESEMBOLSO DE EFECTIVO')
        a_imprimir[x_altura].append('')
        a_imprimir[x_altura].append('')
        a_imprimir[x_altura].append(0)
        a_imprimir[x_altura].append(0)
        x_altura += 1

        x_account_tag = self.env['account.account.tag'].search([('id', '=', 4)])
        if x_account_tag:
            x_cuentas = self.env['account.move.line'].search([
                ('move_id.state', '=', 'posted'),
                ('date', '>=', self.start_date),
                ('date', '<=', self.end_date),
                ('balance', '!=', 0),
                ('company_id.id', '=', self.company_id.id),
                ('account_id.tag_ids', 'in', x_account_tag.ids),
                ('journal_id.name', '!=', 'Partida de Apertura'),
                ('journal_id.name', '!=', 'Partida de Cierre'),
                ('journal_id.name', '!=', 'Traslado de Utilidad')
                # ('account_id.id', 'in', x_account_tag.mapped('account_account_id').mapped('id'))
            ])
        if x_cuentas:
            query = """
                            SELECT 
                                account_id,
                                a.code as code,
                                a.name as name, 
                                sum(balance) as balance
                            FROM account_move_line aml
                            inner join account_account a on a.id = aml.account_id
                            WHERE aml.id IN %s
                            GROUP BY account_id, a.code, a.name
                        """
            self.env.cr.execute(query, (tuple(x_cuentas.ids),))
            result = self.env.cr.dictfetchall()
            #result = x_cuentas.read_group(
            #    domain=[('date', '>=', self.start_date), ('date', '<=', self.end_date), ('move_id.state', '=', 'posted')],
            #    fields=['balance'],
            #    groupby=['account_id'],
            #    lazy=False
            #)

            for line in result:
                a_imprimir.append([])
                a_imprimir[x_altura].append('line')
                a_imprimir[x_altura].append('actividades_operacion')
                a_imprimir[x_altura].append('')
                a_imprimir[x_altura].append(line['code'])
                a_imprimir[x_altura].append(line['name'])
                a_imprimir[x_altura].append(line['balance'])
                a_imprimir[x_altura].append(0)
                x_altura += 1
                x_SubGranTotal += line['balance']
                x_AumentoDisminucion += line['balance'] * -1

        a_imprimir.append([])
        a_imprimir[x_altura].append('head')
        a_imprimir[x_altura].append('actividades_operacion')
        a_imprimir[x_altura].append('FLUJO DE EFECTIVO POR ACTIVIDADES DE OPERACIÓN')
        a_imprimir[x_altura].append('')
        a_imprimir[x_altura].append('')
        a_imprimir[x_altura].append(0)
        a_imprimir[x_altura].append(0)
        x_altura += 1

        x_account_tag = self.env['account.account.tag'].search([('id', '=', 1)])
        if x_account_tag:
            x_cuentas = self.env['account.move.line'].search([
                ('move_id.state', '=', 'posted'),
                ('date', '>=', self.start_date),
                ('date', '<=', self.end_date),
                ('balance', '!=', 0),
                ('company_id.id', '=', self.company_id.id),
                ('account_id.tag_ids', 'in', x_account_tag.ids),
                ('journal_id.name', '!=', 'Partida de Apertura'),
                ('journal_id.name', '!=', 'Partida de Cierre'),
                ('journal_id.name', '!=', 'Traslado de Utilidad')
            ])
        if x_cuentas:
            query = """
                SELECT 
                    account_id,
                    a.code as code,
                    a.name as name, 
                    sum(balance) as balance
                FROM account_move_line aml
                inner join account_account a on a.id = aml.account_id
                WHERE aml.id IN %s
                GROUP BY account_id, a.code, a.name
            """
            self.env.cr.execute(query, (tuple(x_cuentas.ids),))
            result = self.env.cr.dictfetchall()
            #result = x_cuentas.read_group(
            #    domain=[('date', '>=', self.start_date), ('date', '<=', self.end_date),
            #            ('move_id.state', '=', 'posted')],
            #    fields=['balance', 'account_id', 'account_id.code'],
            #    groupby=['account_id', 'account_id.name'],
            #    lazy=False
            # )
            #result[0])
            for line in result:
                a_imprimir.append([])
                a_imprimir[x_altura].append('line')
                a_imprimir[x_altura].append('actividades_operacion')
                a_imprimir[x_altura].append('')
                a_imprimir[x_altura].append(line['code'])
                a_imprimir[x_altura].append(line['name'])
                a_imprimir[x_altura].append(line['balance'])
                a_imprimir[x_altura].append(0)
                x_altura += 1
                x_SubGranTotal += line['balance']
                x_AumentoDisminucion += line['balance'] * -1
        a_imprimir.append([])
        a_imprimir[x_altura].append('foot')
        a_imprimir[x_altura].append('actividades_operacion')
        a_imprimir[x_altura].append('EFECTIVO NETO POR ACTIVIDADES DE OPERACIÓN')
        a_imprimir[x_altura].append('')
        a_imprimir[x_altura].append('')
        a_imprimir[x_altura].append(0)
        a_imprimir[x_altura].append(x_SubGranTotal)
        x_altura += 1

        x_SubGranTotal = 0
        a_imprimir.append([])
        a_imprimir[x_altura].append('head')
        a_imprimir[x_altura].append('actividades_inversion')
        a_imprimir[x_altura].append('FLUJO DE EFECTIVO POR ACTIVIDADES DE INVERSIÓN')
        a_imprimir[x_altura].append('')
        a_imprimir[x_altura].append('')
        a_imprimir[x_altura].append(0)
        a_imprimir[x_altura].append(0)
        x_altura += 1

        x_account_tag = self.env['account.account.tag'].search([('id', '=', 3)])
        if x_account_tag:
            x_cuentas = self.env['account.move.line'].search([
                ('move_id.state', '=', 'posted'),
                ('date', '>=', self.start_date),
                ('date', '<=', self.end_date),
                ('balance', '!=', 0),
                ('company_id.id', '=', self.company_id.id),
                ('account_id.tag_ids', 'in', x_account_tag.ids),
                ('journal_id.name', '!=', 'Partida de Apertura'),
                ('journal_id.name', '!=', 'Partida de Cierre'),
                ('journal_id.name', '!=', 'Traslado de Utilidad')
            ])
        if x_cuentas:
            query = """
                            SELECT 
                                account_id,
                                a.code as code,
                                a.name as name, 
                                sum(balance) as balance
                            FROM account_move_line aml
                            inner join account_account a on a.id = aml.account_id
                            WHERE aml.id IN %s
                            GROUP BY account_id, a.code, a.name
                        """
            self.env.cr.execute(query, (tuple(x_cuentas.ids),))
            result = self.env.cr.dictfetchall()
            #result = x_cuentas.read_group(
            #    domain=[('date', '>=', self.start_date), ('date', '<=', self.end_date),
            #            ('move_id.state', '=', 'posted')],
            #    fields=['balance'],
            #    groupby=['account_id'],
            #    lazy=False
            #)

            for line in result:
                a_imprimir.append([])
                a_imprimir[x_altura].append('line')
                a_imprimir[x_altura].append('actividades_inversion')
                a_imprimir[x_altura].append('')
                a_imprimir[x_altura].append(line['code'])
                a_imprimir[x_altura].append(line['name'])
                a_imprimir[x_altura].append(line['balance'])
                a_imprimir[x_altura].append(0)
                x_altura += 1
                x_SubGranTotal += line['balance']
                x_AumentoDisminucion += line['balance'] * -1

        a_imprimir.append([])
        a_imprimir[x_altura].append('foot')
        a_imprimir[x_altura].append('actividades_inversion')
        a_imprimir[x_altura].append('EFECTIVO NETO POR ACTIVIDADES DE INVERSIÓN')
        a_imprimir[x_altura].append('')
        a_imprimir[x_altura].append('')
        a_imprimir[x_altura].append(0)
        a_imprimir[x_altura].append(x_SubGranTotal)
        x_altura += 1

        x_SubGranTotal = 0
        a_imprimir.append([])
        a_imprimir[x_altura].append('head')
        a_imprimir[x_altura].append('actividades_financiamiento')
        a_imprimir[x_altura].append('FLUJO DE EFECTIVO POR ACTIVIDADES DE FINANCIAMIENTO')
        a_imprimir[x_altura].append('')
        a_imprimir[x_altura].append('')
        a_imprimir[x_altura].append(0)
        a_imprimir[x_altura].append(0)
        x_altura += 1

        x_account_tag = self.env['account.account.tag'].search([('id', '=', 2)])
        if x_account_tag:
            x_cuentas = self.env['account.move.line'].search([
                ('move_id.state', '=', 'posted'),
                ('date', '>=', self.start_date),
                ('date', '<=', self.end_date),
                ('balance', '!=', 0),
                ('company_id.id', '=', self.company_id.id),
                ('account_id.tag_ids', 'in', x_account_tag.ids),
                ('journal_id.name', '!=', 'Partida de Apertura'),
                ('journal_id.name', '!=', 'Partida de Cierre'),
                ('journal_id.name', '!=', 'Traslado de Utilidad')
            ])
        if x_cuentas:
            query = """
                            SELECT 
                                account_id,
                                a.code as code,
                                a.name as name, 
                                sum(balance) as balance
                            FROM account_move_line aml
                            inner join account_account a on a.id = aml.account_id
                            WHERE aml.id IN %s
                            GROUP BY account_id, a.code, a.name
                        """
            self.env.cr.execute(query, (tuple(x_cuentas.ids),))
            result = self.env.cr.dictfetchall()
            #result = x_cuentas.read_group(
             #   domain=[('date', '>=', self.start_date), ('date', '<=', self.end_date),
              #  ('move_id.state', '=', 'posted')],
               # fields=['balance'],
                #groupby=['account_id'],
                #lazy=False
                #)

            for line in result:
                a_imprimir.append([])
                a_imprimir[x_altura].append('line')
                a_imprimir[x_altura].append('actividades_financiamiento')
                a_imprimir[x_altura].append('')
                a_imprimir[x_altura].append(line['code'])
                a_imprimir[x_altura].append(line['name'])
                a_imprimir[x_altura].append(line['balance'])
                a_imprimir[x_altura].append(0)
                x_altura += 1
                x_SubGranTotal += line['balance']
                x_AumentoDisminucion += line['balance'] * -1

        a_imprimir.append([])
        a_imprimir[x_altura].append('foot')
        a_imprimir[x_altura].append('actividades_financiamiento')
        a_imprimir[x_altura].append('EFECTIVO NETO POR ACTIVIDADES DE FINANCIAMIENTO')
        a_imprimir[x_altura].append('')
        a_imprimir[x_altura].append('')
        a_imprimir[x_altura].append(0)
        a_imprimir[x_altura].append(x_SubGranTotal)
        x_altura += 1

        a_imprimir.append([])
        a_imprimir[x_altura].append('foot')
        a_imprimir[x_altura].append('aumento_disminucion')
        a_imprimir[x_altura].append('AUMENTO / DISMINUCIÓN NETO DE EFECTIVO Y EQUIVALENTES DE EFECTIVO AL ' + str(self.end_date.day) + " de " + thMesa + " de " + str(self.end_date.year))
        a_imprimir[x_altura].append('')
        a_imprimir[x_altura].append('')
        a_imprimir[x_altura].append(0)
        a_imprimir[x_altura].append(x_AumentoDisminucion + ((x_balance_4 - x_balance_5 - x_balance_6) + x_balance_7 - x_balance_8))
        x_altura += 1

        a_imprimir.append([])
        a_imprimir[x_altura].append('head')
        a_imprimir[x_altura].append('prueba_aumento_disminucion')
        a_imprimir[x_altura].append('PRUEBA DEL AUMENTO / DISMINUCIÓN DEL EFECTIVO')
        a_imprimir[x_altura].append('')
        a_imprimir[x_altura].append('')
        a_imprimir[x_altura].append(0)
        a_imprimir[x_altura].append(0)
        x_altura += 1

        x_SaldoInicial = sum(self.env['account.move.line'].search([
            ('account_id.group_id.code_prefix_start', 'in', ['10101', '10102']),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', str(self.start_date.year) + '-01-01'),
            ('date', '<=', self.start_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id),
            ('journal_id.name', '!=', 'Partida de Cierre')]).mapped('balance'))

        a_imprimir.append([])
        a_imprimir[x_altura].append('foot_no_total')
        a_imprimir[x_altura].append('saldo_aumento_disminucion')
        a_imprimir[x_altura].append('Saldo inicial de efectivo y equivalentes de efectivo al 1 de enero de ' + str(self.start_date.year))
        a_imprimir[x_altura].append('')
        a_imprimir[x_altura].append('')
        a_imprimir[x_altura].append(0)
        a_imprimir[x_altura].append(x_SaldoInicial)
        x_altura += 1

        x_SaldoFinal = sum(self.env['account.move.line'].search([
            ('account_id.group_id.code_prefix_start', 'in', ['10101', '10102']),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', self.start_date),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id),
            ('journal_id.name', '!=', 'Partida de Cierre')]).mapped('balance'))

        a_imprimir.append([])
        a_imprimir[x_altura].append('foot_no_total')
        a_imprimir[x_altura].append('efectivo_aumento_disminucion')
        a_imprimir[x_altura].append('Efectivo y equivalentes de efectivo al ' + str(self.end_date.day) + " de " + thMesa + " de " + str(self.end_date.year))
        a_imprimir[x_altura].append('')
        a_imprimir[x_altura].append('')
        a_imprimir[x_altura].append(0)
        a_imprimir[x_altura].append(x_SaldoFinal)
        x_altura += 1

        a_imprimir.append([])
        a_imprimir[x_altura].append('foot')
        a_imprimir[x_altura].append('fin_aumento_disminucion')
        a_imprimir[x_altura].append('AUMENTO / DISMINUCIÓN NETO DE EFECTIVO Y EQUIVALENTES DE EFECTIVO AL ' + str(self.end_date.day) + " de " + thMesa + " de " + str(self.end_date.year))
        a_imprimir[x_altura].append('')
        a_imprimir[x_altura].append('')
        a_imprimir[x_altura].append(0)
        a_imprimir[x_altura].append(x_SaldoFinal - x_SaldoInicial)
        x_altura += 1

        if a_imprimir:
            x_seccion = ''
            while x_recorre < len(a_imprimir):
                x_iteracion += 1
                if x_seccion == a_imprimir[x_recorre][1]:
                    x_suma_debe += float(a_imprimir[x_recorre][5])
                    x_suma_haber += float(a_imprimir[x_recorre][5])
                else:
                    x_suma_debe = float(a_imprimir[x_recorre][5])
                    x_suma_haber = float(a_imprimir[x_recorre][5])

                if x_row_page < x_max_rows:  # Estamos en ciclo
                    # ---------------------------- Encabezado ----------------------------------------------------------
                    if x_row_page == 0:  # Nueva pagina

                        worksheet.write(x_rows, 4, "Folio: " + str(self.folio + x_page), frmt_folio)

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 4, self.company_id.name,
                                              frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 4, "NIT: " + self.company_id.partner_id.vat,
                                              frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 4, "Flujo de Efectivo", frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 4,
                                              str("Del " + str(self.start_date.day) + " de " + thMes + " de " + str(
                                                  self.start_date.year) + " Al " + str(
                                                  self.end_date.day) + " de " + thMesa + " de " + str(
                                                  self.end_date.year)), frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 4, "(EXPRESADO EN QUETZALES)",
                                              frmt_encabezado)  # Encabezado
                        # Aca es solo para cerrar el marco
                        x_rows += 1
                        x_row_page += 1
                        worksheet.write(x_rows, 0, '', frmt_borde_superior)
                        worksheet.write(x_rows, 1, '', frmt_borde_superior)
                        worksheet.write(x_rows, 2, '', frmt_borde_superior)
                        worksheet.write(x_rows, 3, '', frmt_borde_superior)
                        worksheet.write(x_rows, 4, '', frmt_borde_superior)

                        x_rows += 1
                        x_row_page += 1
                        if a_imprimir[x_recorre][0] == 'head_total' and a_imprimir[x_recorre][1] == 'actividades_operacion':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][2], frmt_titulos)
                            worksheet.write(x_rows, 1, '', False)
                            worksheet.write(x_rows, 2, '', False)
                            worksheet.write(x_rows, 3, '', debe_haber_vacio)
                            worksheet.write(x_rows, 4, a_imprimir[x_recorre][6], debe_haber_bold)

                        elif a_imprimir[x_recorre][0] in ['head'] and a_imprimir[x_recorre][1] in ['actividades_operacion', 'actividades_inversion', 'actividades_financiamiento', 'prueba_aumento_disminucion','saldo_aumento_disminucion','efectivo_aumento_disminucion']:
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][2], frmt_titulos)
                            worksheet.write(x_rows, 1, '', False)
                            worksheet.write(x_rows, 2, '', False)
                            worksheet.write(x_rows, 3, '', debe_haber_vacio)
                            worksheet.write(x_rows, 4, '', debe_haber_vacio)

                        elif a_imprimir[x_recorre][0] in ['foot_no_total'] and a_imprimir[x_recorre][1] in ['saldo_aumento_disminucion','efectivo_aumento_disminucion']:
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][2], frmt_cuenta)
                            worksheet.write(x_rows, 1, '', False)
                            worksheet.write(x_rows, 2, '', False)
                            worksheet.write(x_rows, 3, '', debe_haber_vacio)
                            worksheet.write(x_rows, 4, a_imprimir[x_recorre][6], debe_haber)

                        elif a_imprimir[x_recorre][0] == 'line' and a_imprimir[x_recorre][1] in ['actividades_operacion', 'actividades_inversion', 'actividades_financiamiento']:
                            worksheet.write(x_rows, 0, '', frmt_titulos)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][4], frmt_cuenta)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][5], debe_haber)
                            worksheet.write(x_rows, 4, '', debe_haber)

                        elif a_imprimir[x_recorre][0] == 'foot' and a_imprimir[x_recorre][1] in ['actividades_operacion', 'actividades_inversion', 'actividades_financiamiento', 'aumento_disminucion', 'fin_aumento_disminucion']:
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][2], frmt_titulos)
                            worksheet.write(x_rows, 1, '', False)
                            worksheet.write(x_rows, 2, '', False)
                            worksheet.write(x_rows, 3, '', debe_haber_vacio)
                            worksheet.write(x_rows, 4, a_imprimir[x_recorre][6], debe_haber_bold)

                    # ---------------------------- Fin Encabezado ----------------------------------------------------------
                    elif x_row_page > 0 and x_row_page == x_max_rows - 1:  # Estamos en la penultima linea

                        x_rows += 1
                        x_row_page = 0
                        worksheet.write(x_rows, 0, '', frmt_van_vacio)
                        worksheet.write(x_rows, 1, '', frmt_van_vacio_i)
                        worksheet.write(x_rows, 2, 'VAN', frmt_van_vacio_ii)
                        worksheet.write(x_rows, 3, float(x_suma_debe), debe_haber_van_vienen)
                        worksheet.write(x_rows, 4, float(x_suma_haber), debe_haber_van_vienen)
                        # Encabezado 1

                        x_rows += 1
                        #x_row_page += 1
                        x_page += 1
                        worksheet.write(x_rows, 4, "Folio: " + str(self.folio + x_page), frmt_folio)

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 4, self.company_id.name,
                                              frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 4, "NIT: " + self.company_id.partner_id.vat,
                                              frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 4, "Flujo de Efectivo",
                                              frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 4,
                                              str("Del " + str(self.start_date.day) + " de " + thMes + " de " + str(
                                                  self.start_date.year) + " Al " + str(
                                                  self.end_date.day) + " de " + thMesa + " de " + str(
                                                  self.end_date.year)), frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.merge_range(x_rows, 0, x_rows, 4, "(EXPRESADO EN QUETZALES)",
                                              frmt_encabezado)  # Encabezado

                        x_rows += 1
                        x_row_page += 1
                        worksheet.write(x_rows, 0, '', frmt_borde_superior)
                        worksheet.write(x_rows, 1, '', frmt_borde_superior)
                        worksheet.write(x_rows, 2, '', frmt_borde_superior)
                        worksheet.write(x_rows, 3, '', frmt_borde_superior)
                        worksheet.write(x_rows, 4, '', frmt_borde_superior)

                        x_rows += 1
                        x_row_page = 0
                        worksheet.write(x_rows, 0, '', frmt_van_vacio)
                        worksheet.write(x_rows, 1, '', frmt_van_vacio_i)
                        worksheet.write(x_rows, 2, 'VIENEN', frmt_van_vacio_ii)
                        worksheet.write(x_rows, 3, float(x_suma_debe), debe_haber_van_vienen)
                        worksheet.write(x_rows, 4, float(x_suma_haber), debe_haber_van_vienen)

                        x_rows += 1
                        x_row_page += 1
                        if a_imprimir[x_recorre][0] == 'head_total' and a_imprimir[x_recorre][
                            1] == 'actividades_operacion':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][2], frmt_titulos)
                            worksheet.write(x_rows, 1, '', False)
                            worksheet.write(x_rows, 2, '', False)
                            worksheet.write(x_rows, 3, '', debe_haber_vacio)
                            worksheet.write(x_rows, 4, a_imprimir[x_recorre][6], debe_haber_bold)

                        elif a_imprimir[x_recorre][0] in ['head',] and a_imprimir[x_recorre][1] in [
                            'actividades_operacion', 'actividades_inversion', 'actividades_financiamiento',
                            'prueba_aumento_disminucion']:
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][2], frmt_titulos)
                            worksheet.write(x_rows, 1, '', False)
                            worksheet.write(x_rows, 2, '', False)
                            worksheet.write(x_rows, 3, '', debe_haber_vacio)
                            worksheet.write(x_rows, 4, '', debe_haber_vacio)

                        elif a_imprimir[x_recorre][0] in ['foot_no_total'] and a_imprimir[x_recorre][1] in ['saldo_aumento_disminucion','efectivo_aumento_disminucion']:
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][2], frmt_cuenta)
                            worksheet.write(x_rows, 1, '', False)
                            worksheet.write(x_rows, 2, '', False)
                            worksheet.write(x_rows, 3, '', debe_haber_vacio)
                            worksheet.write(x_rows, 4, a_imprimir[x_recorre][6], debe_haber)

                        elif a_imprimir[x_recorre][0] == 'line' and a_imprimir[x_recorre][1] in [
                            'actividades_operacion', 'actividades_inversion', 'actividades_financiamiento']:
                            worksheet.write(x_rows, 0, '', frmt_titulos)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][4], frmt_cuenta)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][5], debe_haber)
                            worksheet.write(x_rows, 4, '', debe_haber)

                        elif a_imprimir[x_recorre][0] == 'foot' and a_imprimir[x_recorre][1] in [
                            'actividades_operacion', 'actividades_inversion', 'actividades_financiamiento',
                            'aumento_disminucion', 'fin_aumento_disminucion']:
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][2], frmt_titulos)
                            worksheet.write(x_rows, 1, '', False)
                            worksheet.write(x_rows, 2, '', False)
                            worksheet.write(x_rows, 3, '', debe_haber_vacio)
                            worksheet.write(x_rows, 4, a_imprimir[x_recorre][6], debe_haber_bold)

                    else:  # No estamos en la ultima linea, estamos en la misma cuenta
                        x_rows += 1
                        x_row_page += 1
                        if a_imprimir[x_recorre][0] == 'head_total' and a_imprimir[x_recorre][
                            1] == 'actividades_operacion':
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][2], frmt_titulos)
                            worksheet.write(x_rows, 1, '', False)
                            worksheet.write(x_rows, 2, '', False)
                            worksheet.write(x_rows, 3, '', debe_haber_vacio)
                            worksheet.write(x_rows, 4, a_imprimir[x_recorre][6], debe_haber_bold)

                        elif a_imprimir[x_recorre][0] in ['head'] and a_imprimir[x_recorre][1] in [
                            'actividades_operacion', 'actividades_inversion', 'actividades_financiamiento',
                            'prueba_aumento_disminucion']:
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][2], frmt_titulos)
                            worksheet.write(x_rows, 1, '', False)
                            worksheet.write(x_rows, 2, '', False)
                            worksheet.write(x_rows, 3, '', debe_haber_vacio)
                            worksheet.write(x_rows, 4, '', debe_haber_vacio)

                        elif a_imprimir[x_recorre][0] in ['foot_no_total'] and a_imprimir[x_recorre][1] in ['saldo_aumento_disminucion','efectivo_aumento_disminucion']:
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][2], frmt_cuenta)
                            worksheet.write(x_rows, 1, '', False)
                            worksheet.write(x_rows, 2, '', False)
                            worksheet.write(x_rows, 3, '', debe_haber_vacio)
                            worksheet.write(x_rows, 4, a_imprimir[x_recorre][6], debe_haber)

                        elif a_imprimir[x_recorre][0] == 'line' and a_imprimir[x_recorre][1] in [
                            'actividades_operacion', 'actividades_inversion', 'actividades_financiamiento']:
                            worksheet.write(x_rows, 0, '', frmt_titulos)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][4], frmt_cuenta)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][5], debe_haber)
                            worksheet.write(x_rows, 4, '', debe_haber)

                        elif a_imprimir[x_recorre][0] == 'foot' and a_imprimir[x_recorre][1] in [
                            'actividades_operacion', 'actividades_inversion', 'actividades_financiamiento',
                            'aumento_disminucion', 'fin_aumento_disminucion']:
                            worksheet.write(x_rows, 0, a_imprimir[x_recorre][2], frmt_titulos)
                            worksheet.write(x_rows, 1, '', False)
                            worksheet.write(x_rows, 2, '', False)
                            worksheet.write(x_rows, 3, '', debe_haber_vacio)
                            worksheet.write(x_rows, 4, a_imprimir[x_recorre][6], debe_haber_bold)

                x_recorre += 1
            certifica = str(self.certificacion)
            text1 = '______________________' \
                   '\n'+self.representante +\
                '\nRepresentante Legal'
            text2 = '______________________' \
                    '\n'+self.contador + \
                    '\nContador'

            options1 = {
                'width': 205,
                'height': 100,
                'x_offset': 0,
                'y_offset': 0,

                'font': {'color': 'black',
                         'font': 'Arial',
                         'size': 10,
                         'bold': True,
                         },
                'align': {'vertical': 'bottom',
                          'horizontal': 'center'
                          },

            }
            options2 = {
                'width': 205,
                'height': 100,
                'x_offset': 0,
                'y_offset': 0,

                'font': {'color': 'black',
                         'font': 'Arial',
                         'size': 10,
                         'bold': True,
                         },
                'align': {'vertical': 'bottom',
                          'horizontal': 'center'
                          },

            }
            cert_options = {
                'width': 615,
                'height': 100,
                'x_offset': 0,
                'y_offset': 0,

                'font': {'color': 'black',
                         'font': 'Arial',
                         'size': 10,
                         'bold': True,
                         },
                'align': {'vertical': 'top',
                          'horizontal': 'left'
                          },

            }
            cell = xl_rowcol_to_cell(x_rows+2, 0)
            worksheet.insert_textbox(cell, certifica, cert_options)
            cell = xl_rowcol_to_cell(x_rows + 7, 0)
            worksheet.insert_textbox(cell, text1, options1)
            cell = xl_rowcol_to_cell(x_rows + 7, 3)
            worksheet.insert_textbox(cell, text2, options2)


        workbook.close()
        self.write({
            'state': 'get',
            'data': base64.b64encode(open(xls_path, 'rb').read()),
            'name': xls_filename
        })
        return {
            'name': 'Flujo de Efectivo',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new'
        }

class wizard_cambio_patrimonio(models.TransientModel):
    _name = 'wizard.cambio.patrimonio'
    _description = "Wizard Estado de Cambios al Patrimonio"
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id)
    end_date = fields.Date(string="Fecha Fin")
    IsrPagar = fields.Float(string="ISR a Pagar", default=0)
    ReservaLegal = fields.Float(string="Reserva Legal", default=0)
    anio = fields.Integer(string="Año")
    mes_de = fields.Selection([('1','Enero'),('2','Febrero'),('3','Marzo'),('4','Abril'),('5','Mayo'),('6','Junio'),('7','Julio'),('8','Agosto'),('9','Septiembre'),('10','Octubre'),('11','Noviembre'),('12','Diciembre')],string="De")
    mes_a = fields.Selection(
        [('1', 'Enero'), ('2', 'Febrero'), ('3', 'Marzo'), ('4', 'Abril'), ('5', 'Mayo'), ('6', 'Junio'),
         ('7', 'Julio'), ('8', 'Agosto'), ('9', 'Septiembre'), ('10', 'Octubre'), ('11', 'Noviembre'),
         ('12', 'Diciembre')], string="A")
    folio = fields.Integer(string="Folio")
    representante = fields.Char(string="Representante Legal")
    contador = fields.Char(string="Contador")
    nit_contador = fields.Char(string="NIT Contador")
    filter_by = fields.Selection([('product', 'Product'), ('category', 'Category')], string="Filter By")
    group_by_categ = fields.Boolean(string="Group By Category")
    state = fields.Selection([('choose', 'choose'), ('get', 'get')], default='choose')
    name = fields.Char(string='File Name', readonly=True)
    data = fields.Binary(string='File', readonly=True)
    product_ids = fields.Many2many('product.product', string="Products")
    category_ids = fields.Many2many('product.category', string="Categories")
    #Utilidades retenidas de partida de apertura
    # ISR a pagar
    # Reserva Legal
    # Columnas para el reporte

    @api.onchange('company_id')
    def onchange_company_id(self):
        domain = [('id', 'in', self.env.user.company_ids.ids)]
        # if self.company_id:
            # self.warehouse_ids = False
            # self.location_ids = False
        return {'domain':{'company_id':domain}}

    @api.onchange('filter_by')
    def onchange_filter_by(self):
        self.product_ids = False
        self.category_ids = False

    def print_report(self):
        self.check_date_range()
        datas = {'form':
                    {
                        'company_id': self.company_id.id,
                        'warehouse_ids': [y.id for y in self.warehouse_ids],
                        'location_ids': self.location_ids.ids or False,
                        'start_date': self.start_date,
                        'end_date': self.end_date,
                        'id': self.id,
                        'product_ids': self.product_ids.ids,
                        'product_categ_ids': self.category_ids.ids
                    },
                }
        return self.env.ref('account_report_financial.action_report_financial_template').report_action(self, data=datas)

    def go_back(self):
        self.state = 'choose'
        return {
            'name': 'Report Financial Cambio Patrimonio',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new'
        }

    def print_xls_cambio_patrimonio(self):
        thMesa = ""

        if self.end_date.month == 1:
            thMesa = "Enero"
        elif self.end_date.month == 2:
            thMesa = "Febrero"
        elif self.end_date.month == 3:
            thMesa = "Marzo"
        elif self.end_date.month == 4:
            thMesa = "Abril"
        elif self.end_date.month == 5:
            thMesa = "Mayo"
        elif self.end_date.month == 6:
            thMesa = "Junio"
        elif self.end_date.month == 7:
            thMesa = "Julio"
        elif self.end_date.month == 8:
            thMesa = "Agosto"
        elif self.end_date.month == 9:
            thMesa = "Septiembre"
        elif self.end_date.month == 10:
            thMesa = "Octubre"
        elif self.end_date.month == 11:
            thMesa = "Noviembre"
        else:
            thMesa = "Diciembre"

        xls_filename = 'Cambio Patrimonio.xlsx'
        temp_dir = tempfile.gettempdir()
        xls_path = os.path.join(temp_dir, xls_filename)
        workbook = xlsxwriter.Workbook(xls_path)
        #workbook = xlsxwriter.Workbook('/tmp/' + xls_filename)

        frmt_folio = workbook.add_format({'bold': False, 'align': 'right', \
                                          'font': 'Arial', 'font_size': 10})
        frmt_encabezado = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                               'font': 'Arial', 'font_size': 10})
        frmt_valor = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 10, 'num_format': 'Q#,##0.00'})
        frmt_valor_resultado = workbook.add_format(
            {'align': 'right', 'font': 'Arial', 'font_size': 10, 'num_format': 'Q#,##0.00'})
        frmt_valor_total = workbook.add_format({'bold': True, 'align': 'right', 'font': 'Arial', 'font_size': 10, 'num_format': 'Q#,##0.00'})
        frmt_valor_gran_total = workbook.add_format(
            {'align': 'right', 'font': 'Arial', 'font_size': 10, 'num_format': 'Q#,##0.00'})
        frmt_titulos = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 10, 'bold': True})
        frmt_linea = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 10})
        frmt_certificacion = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 10, 'text_wrap': True})
        frmt_fecha = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 10})

        frmt_firma = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                               'font': 'Arial', 'font_size': 10})
        frmt_valor_resultado.set_bottom(1)
        frmt_valor_total.set_top(1)
        frmt_valor_gran_total.set_bottom(6)

        worksheet = workbook.add_worksheet("Movimientos al Patrimonio")
        worksheet.set_portrait()
        worksheet.set_page_view()
        worksheet.set_paper(1)
        worksheet.set_margins(0.7, 0.7, 0.7, 0.7)
        # Tamaños
        worksheet.set_column('A:A', 50)
        worksheet.set_column('B:B', 15)
        worksheet.set_column('C:C', 15)

        # Empieza detalle
        x_rows = 0 # Linea a imprimir
        x_page = 0 # Numero de pagina
        x_max_rows = 47 # Maximo de lineas por pagina
        x_row_page = 0 # Linea actual vrs maximo de lineas
        x_altura = 0
        x_recorre = 0
        x_suma_debe = 0
        x_suma_haber = 0
        x_iteracion = 0

        a_imprimir = []
        # Calculo del capital social
        x_CapitalSocial = sum(self.env['account.move.line'].search([
            ('account_id.group_id.code_prefix_start', 'in', ['30101']),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', str(self.end_date.year) + '-01-01'),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id),
            #('journal_id.name', '!=', 'Partida de Apertura'),
            ('journal_id.name', '!=', 'Traslado de Utilidad')]).mapped('balance'))

        a_imprimir.append([])
        a_imprimir[x_altura].append('line')
        a_imprimir[x_altura].append('capital_social')
        a_imprimir[x_altura].append('Capital Social')
        a_imprimir[x_altura].append(0)
        a_imprimir[x_altura].append(x_CapitalSocial * -1)
        x_altura += 1

        # Calculo acciones por suscribir
        x_AccionesSuscribir = sum(self.env['account.move.line'].search([
            ('account_id.group_id.code_prefix_start', 'in', ['30102']),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', str(self.end_date.year) + '-01-01'),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id),
            #('journal_id.name', '!=', 'Partida de Apertura'),
            ('journal_id.name', '!=', 'Traslado de Utilidad')]).mapped('balance')) * -1

        a_imprimir.append([])
        a_imprimir[x_altura].append('line')
        a_imprimir[x_altura].append('acciones_suscribir')
        a_imprimir[x_altura].append('Acciones por Suscribir')
        a_imprimir[x_altura].append(0)
        a_imprimir[x_altura].append(x_AccionesSuscribir)
        x_altura += 1

        # Calculo reserva legal
        x_ReservaLegali = sum(self.env['account.move.line'].search([
            ('account_id.group_id.code_prefix_start', 'in', ['30106']),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', str(self.end_date.year) + '-01-01'),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id),
            #('journal_id.name', '!=', 'Partida de Apertura'),
            ('journal_id.name', '!=', 'Traslado de Utilidad')]).mapped('balance'))

        a_imprimir.append([])
        a_imprimir[x_altura].append('line')
        a_imprimir[x_altura].append('reserva_legal')
        a_imprimir[x_altura].append('Reserva Legal')
        a_imprimir[x_altura].append(0)
        a_imprimir[x_altura].append(x_ReservaLegali*-1)
        x_altura += 1

        a_imprimir.append([])
        a_imprimir[x_altura].append('head')
        a_imprimir[x_altura].append('integracion_utilidades')
        a_imprimir[x_altura].append('Integracion de los resultados acumulados')
        a_imprimir[x_altura].append(0)
        a_imprimir[x_altura].append(0)
        x_altura += 1

        # Calculo utilidad retenida al
        x_UtilidadRetenidaAl = sum(self.env['account.move.line'].search([
            #('account_id.group_id.code_prefix_start', 'in', ['30104']), 3010401
            ('account_id.code', 'in', ['3010401', '3010501']),
            ('move_id.state', '=', 'posted'),
            ('date', '=', str(self.end_date.year) + '-01-01'),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id),
            ('journal_id.name', 'in', ['Partida de Apertura'])]).mapped('balance')) * -1

        x_UtilidadRetenidaAl += sum(self.env['account.move.line'].search([
            ('account_id.code', 'in', ['3010401', '3010501']),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', str(self.end_date.year-1) + '-01-01'),
            ('date', '<=', str(self.end_date.year-1) + '-12-31'),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id),
            ('journal_id.name', 'in', ['Traslado de Utilidad'])]).mapped('balance')) * -1
        #2027-05-27 Edvin calculando las utilidades retinidas , REsultado del ejericico, utilidad retenida, y perdidas Acumuladas
        #x_utilidades_retenidas la estoy utilizando linea 7483 y 7529
        x_utilidades_retenidas = sum(self.env['account.move.line'].search([
            ('account_id.code', 'in', ['3010301','3010401', '3010501']),
            ('move_id.state', '=', 'posted'),
            ('date', '=', str(self.end_date.year-1) + '-12-31'),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id),
            ('journal_id.name', 'in', ['Partida de Cierre'])]).mapped('balance'))
            #('journal_id.name', 'in', ['Partida de Cierre'])]).mapped('balance'))*-1

        a_imprimir.append([])
        a_imprimir[x_altura].append('line')
        a_imprimir[x_altura].append('utilidad_retenida')
        a_imprimir[x_altura].append('Resultados acumulados al 31 de Diciembre de ' + str(self.end_date.year-1))
        a_imprimir[x_altura].append(x_utilidades_retenidas)
        a_imprimir[x_altura].append(0)
        x_altura += 1

        # Calculo ISR a pagar
        x_IsrPagar = self.IsrPagar #sum(self.env['account.move.line'].search([
            #('account_id.code', '=', ['2010210']),
            #('move_id.state', '=', 'posted'),
            #('date', '>=', str(self.end_date.year) + '-01-01'),
            #('date', '<=', self.end_date),
            #('balance', '!=', 0),
            #('company_id.id', '=', self.company_id.id),
            #]).mapped('balance'))

        a_imprimir.append([])
        a_imprimir[x_altura].append('line')
        a_imprimir[x_altura].append('isr_pagar')
        a_imprimir[x_altura].append('-) ISR a pagar')
        a_imprimir[x_altura].append(x_IsrPagar)
        a_imprimir[x_altura].append(0)
        x_altura += 1

        # Calculo reserva legal
        x_ReservaLegalii = self.ReservaLegal #sum(self.env['account.move.line'].search([
            #('account_id.group_id.code_prefix_start', 'in', ['30106']),
            #('move_id.state', '=', 'posted'),
            #('date', '>=', str(self.end_date.year) + '-01-01'),
            #('date', '<=', self.end_date),
            #('balance', '!=', 0),
            #('company_id.id', '=', self.company_id.id),
            #('journal_id.name', '!=', 'Partida de Apertura'),
            #('journal_id.name', '!=', 'Traslado de Utilidad')
            #]).mapped('balance'))

        a_imprimir.append([])
        a_imprimir[x_altura].append('line')
        a_imprimir[x_altura].append('reserva_legal_i')
        a_imprimir[x_altura].append('-) Reserva Legal')
        a_imprimir[x_altura].append(x_ReservaLegalii)
        a_imprimir[x_altura].append(0)
        x_altura += 1

        a_imprimir.append([])
        a_imprimir[x_altura].append('foot')
        a_imprimir[x_altura].append('utilidades_netas')
        a_imprimir[x_altura].append('Resultados acumulados netos al 31 de Diciembre de ' + str(self.end_date.year-1))
        a_imprimir[x_altura].append(x_utilidades_retenidas - x_IsrPagar - x_ReservaLegalii)
        #a_imprimir[x_altura].append(0)
        a_imprimir[x_altura].append(0)
        x_altura += 1

        x_AjustesReclasificaciones = sum(self.env['account.move.line'].search([
            #('account_id.group_id.code_prefix_start', 'in', ['30106']),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', str(self.end_date.year) + '-01-01'),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id),
            ('journal_id.name', '=', 'Ajustes y Reclasificaciones'),
            ]).mapped('debit'))

        a_imprimir.append([])
        a_imprimir[x_altura].append('line')
        a_imprimir[x_altura].append('ajustes_reclasificaciones')
        a_imprimir[x_altura].append('Ajustes al resultado ' + str(self.end_date.year))
        a_imprimir[x_altura].append(abs(x_AjustesReclasificaciones))
        a_imprimir[x_altura].append(0)
        x_altura += 1

        x_DistribucionDividendos = sum(self.env['account.move.line'].search([
            #('account_id.group_id.code_prefix_start', 'in', ['30106']),
            ('account_id.code', 'in', ['2010104']),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', str(self.end_date.year) + '-01-01'),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id),
            ('journal_id.name', '!=', 'Partida de Cierre')
            ]).mapped('balance'))

        a_imprimir.append([])
        a_imprimir[x_altura].append('line')
        a_imprimir[x_altura].append('distribucion_dividendos')
        a_imprimir[x_altura].append('Distribución de Dividendos')
        a_imprimir[x_altura].append(abs(x_DistribucionDividendos))
        a_imprimir[x_altura].append(0)
        x_altura += 1

        # Calculo de la utilidad del ejercicio
        x_balance_4 = 0
        x_balance_4 = sum(self.env['account.move.line'].search([
            ('account_id.group_id.parent_id.parent_id.code_prefix_start', '=', '4'),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', str(self.end_date.year) + '-01-01'),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id),
        ('journal_id.name', '!=', 'Partida de Cierre')]).mapped('balance')) * -1
        x_balance_5 = 0
        x_balance_5 = sum(self.env['account.move.line'].search([
            ('account_id.group_id.parent_id.parent_id.code_prefix_start', '=', '5'),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', str(self.end_date.year) + '-01-01'),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id),
        ('journal_id.name', '!=', 'Partida de Cierre')]).mapped('balance'))
        x_balance_6 = 0
        x_balance_6 = sum(self.env['account.move.line'].search([
            ('account_id.group_id.parent_id.parent_id.code_prefix_start', '=', '6'),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', str(self.end_date.year) + '-01-01'),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id),
        ('journal_id.name', '!=', 'Partida de Cierre')]).mapped('balance'))
        x_balance_7 = 0
        x_balance_7 = sum(self.env['account.move.line'].search([
            ('account_id.group_id.parent_id.parent_id.code_prefix_start', '=', '7'),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', str(self.end_date.year) + '-01-01'),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id),
            ('journal_id.name', '!=', 'Partida de Cierre')]).mapped('balance'))*-1
        x_balance_8 = 0
        x_balance_8 = sum(self.env['account.move.line'].search([
            ('account_id.group_id.parent_id.parent_id.code_prefix_start', '=', '8'),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', str(self.end_date.year) + '-01-01'),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id),
        ('journal_id.name', '!=', 'Partida de Cierre')]).mapped('balance'))

        a_imprimir.append([])
        a_imprimir[x_altura].append('line')
        a_imprimir[x_altura].append('resultado_ejercicio')
        a_imprimir[x_altura].append('Resultado del Ejercicio Contable ' + str(self.end_date.year))
        a_imprimir[x_altura].append((((x_balance_4 - x_balance_5) - x_balance_6) + x_balance_7 - x_balance_8))
        a_imprimir[x_altura].append(
            (
                    x_utilidades_retenidas
                    - x_IsrPagar
                    - x_ReservaLegalii
            )

            + (((x_balance_4 - x_balance_5) - x_balance_6) + x_balance_7 - x_balance_8)
        )
        x_altura += 1

        a_imprimir.append([])
        a_imprimir[x_altura].append('foot_total')
        a_imprimir[x_altura].append('total_patrimonio')
        a_imprimir[x_altura].append('Total Patrimonio de la Empresa')
        a_imprimir[x_altura].append(0)
        a_imprimir[x_altura].append(

            (
                (
                        (
                            x_utilidades_retenidas
                            - x_IsrPagar
                            - x_ReservaLegalii
                        )
                        + (((x_balance_4 - x_balance_5 - x_balance_6) + x_balance_7 - x_balance_8))
                )
            )
            + (x_CapitalSocial * -1)
            + x_AccionesSuscribir
            + (x_ReservaLegali * -1)

        )
        x_altura += 1

        certificacion = 'El infrascrito Perito Contador identificado con NIT ' + str(self.nit_contador) + ' CERTIFICA: Que el presente Estado de Movimientos Al patrimonio fue realizado conforme los registros contables de la entidad '+ self.company_id.name+' NIT ' + self.company_id.partner_id.vat +' y que el mismo refleja los cambios en el patrimonio durante el ejercicio correspondiente al 01 del enero al '+ str(self.end_date.day)+' de '+thMesa+' de '+ str(self.end_date.year)

        a_imprimir.append([])
        a_imprimir[x_altura].append('line')
        a_imprimir[x_altura].append('certificacion')
        a_imprimir[x_altura].append(certificacion)
        a_imprimir[x_altura].append(0)
        a_imprimir[x_altura].append(0)
        x_altura += 1

        a_imprimir.append([])
        a_imprimir[x_altura].append('line')
        a_imprimir[x_altura].append('fecha')
        a_imprimir[x_altura].append('Quetzaltenango, '+str(self.end_date.day)+' de '+thMesa+' de '+str(self.end_date.year))
        a_imprimir[x_altura].append(0)
        a_imprimir[x_altura].append(0)
        x_altura += 1

        if a_imprimir:
            # ---------------------------- Encabezado ----------------------------------------------------------
            worksheet.write(x_rows, 2, "Folio: " + str(self.folio + x_page), frmt_folio)

            x_rows += 1
            x_row_page += 1
            worksheet.merge_range(x_rows, 0, x_rows, 2, self.company_id.name, frmt_encabezado)  # Encabezado

            x_rows += 1
            x_row_page += 1
            worksheet.merge_range(x_rows, 0, x_rows, 2, "NIT: " + self.company_id.partner_id.vat,
                                              frmt_encabezado)  # Encabezado

            x_rows += 1
            x_row_page += 1
            worksheet.merge_range(x_rows, 0, x_rows, 2, "Estado de Cambios de Movimientos en el Patrimonio", frmt_encabezado)  # Encabezado

            x_rows += 1
            x_row_page += 1
            worksheet.merge_range(x_rows, 0, x_rows, 2,
                                              str("Al " + str(
                                                  self.end_date.day) + " de " + thMesa + " de " + str(
                                                  self.end_date.year)), frmt_encabezado)  # Encabezado

            x_rows += 1
            x_row_page += 1
            worksheet.merge_range(x_rows, 0, x_rows, 2, "(EXPRESADO EN QUETZALES)",
                                              frmt_encabezado)  # Encabezado

            x_rows += 1
            x_row_page += 1
            if a_imprimir[x_recorre][0] == 'line' and a_imprimir[x_recorre][1] in ['capital_social', 'acciones_suscribir', 'reserva_legal', 'integracion_utilidades']:
                worksheet.write(x_rows, 0, a_imprimir[x_recorre][2], frmt_linea)
                worksheet.write(x_rows, 1, '', False)
                worksheet.write(x_rows, 2, a_imprimir[x_recorre][4], frmt_valor)
                x_recorre += 1

            x_rows += 1
            x_row_page += 1
            if a_imprimir[x_recorre][0] == 'line' and a_imprimir[x_recorre][1] in ['capital_social',
                                                                                   'acciones_suscribir',
                                                                                   'reserva_legal',
                                                                                   'integracion_utilidades']:
                worksheet.write(x_rows, 0, a_imprimir[x_recorre][2], frmt_linea)
                worksheet.write(x_rows, 1, '', False)
                worksheet.write(x_rows, 2, a_imprimir[x_recorre][4], frmt_valor)
                x_recorre += 1

            x_rows += 1
            x_row_page += 1
            if a_imprimir[x_recorre][0] == 'line' and a_imprimir[x_recorre][1] in ['capital_social',
                                                                                   'acciones_suscribir',
                                                                                   'reserva_legal',
                                                                                   'integracion_utilidades']:
                worksheet.write(x_rows, 0, a_imprimir[x_recorre][2], frmt_linea)
                worksheet.write(x_rows, 1, '', False)
                worksheet.write(x_rows, 2, a_imprimir[x_recorre][4], frmt_valor)
                x_recorre += 1

            #x_rows += 1
            #x_row_page += 1
            #if a_imprimir[x_recorre][0] == 'line' and a_imprimir[x_recorre][1] in ['capital_social',
            #                                                                       'acciones_suscribir',
            #                                                                       'reserva_legal',
            #                                                                       'integracion_utilidades']:
            #    worksheet.write(x_rows, 0, a_imprimir[x_recorre][2], frmt_linea)
            #    worksheet.write(x_rows, 1, '', False)
            #    worksheet.write(x_rows, 2, a_imprimir[x_recorre][4], frmt_valor)
            #    x_recorre += 1

            x_rows += 1
            x_row_page += 1
            if a_imprimir[x_recorre][0] in ['head'] and a_imprimir[x_recorre][1] == 'integracion_utilidades':
                worksheet.write(x_rows, 0, a_imprimir[x_recorre][2], frmt_titulos)
                worksheet.write(x_rows, 1, '', False)
                worksheet.write(x_rows, 2, '', False)
                x_recorre += 1

            x_rows += 1
            x_row_page += 1
            if a_imprimir[x_recorre][0] == 'line' and a_imprimir[x_recorre][1] in ['utilidad_retenida',
                                                                                   'isr_pagar',
                                                                                   'reserva_legal_i',
                                                                                   'ajustes_reclasificaciones',
                                                                                   'distribucion_dividendos',
                                                                                   'resultado_ejercicio']:
                worksheet.write(x_rows, 0, a_imprimir[x_recorre][2], frmt_linea)
                worksheet.write(x_rows, 1, a_imprimir[x_recorre][3], frmt_valor)
                worksheet.write(x_rows, 2, '', False)
                x_recorre += 1

            x_rows += 1
            x_row_page += 1
            if a_imprimir[x_recorre][0] == 'line' and a_imprimir[x_recorre][1] in ['utilidad_retenida',
                                                                                   'isr_pagar',
                                                                                   'reserva_legal_i',
                                                                                   'ajustes_reclasificaciones',
                                                                                   'distribucion_dividendos',
                                                                                   'resultado_ejercicio']:
                worksheet.write(x_rows, 0, a_imprimir[x_recorre][2], frmt_linea)
                worksheet.write(x_rows, 1, a_imprimir[x_recorre][3], frmt_valor)
                worksheet.write(x_rows, 2, '', False)
                x_recorre += 1

            x_rows += 1
            x_row_page += 1
            if a_imprimir[x_recorre][0] == 'line' and a_imprimir[x_recorre][1] in ['utilidad_retenida', 'isr_pagar',
                                                                                   'reserva_legal_i',
                                                                                   'ajustes_reclasificaciones',
                                                                                   'distribucion_dividendos',
                                                                                   'resultado_ejercicio']:
                worksheet.write(x_rows, 0, a_imprimir[x_recorre][2], frmt_linea)
                worksheet.write(x_rows, 1, a_imprimir[x_recorre][3], frmt_valor)
                worksheet.write(x_rows, 2, '', False)
                x_recorre += 1

            x_rows += 1
            x_row_page += 1
            if a_imprimir[x_recorre][0] == 'foot' and a_imprimir[x_recorre][1] in ['utilidades_netas']:
                worksheet.write(x_rows, 0, a_imprimir[x_recorre][2], frmt_titulos)
                worksheet.write(x_rows, 1, a_imprimir[x_recorre][3], frmt_valor_total)
                worksheet.write(x_rows, 2, '', False)
                x_recorre += 1

            x_rows += 1
            x_row_page += 1
            if a_imprimir[x_recorre][0] == 'line' and a_imprimir[x_recorre][1] in ['utilidad_retenida', 'isr_pagar',
                                                                                   'reserva_legal_i',
                                                                                   'ajustes_reclasificaciones',
                                                                                   'distribucion_dividendos',
                                                                                   'resultado_ejercicio']:
                worksheet.write(x_rows, 0, a_imprimir[x_recorre][2], frmt_linea)
                worksheet.write(x_rows, 1, a_imprimir[x_recorre][3], frmt_valor)
                worksheet.write(x_rows, 2, '', False)
                x_recorre += 1

            x_rows += 1
            x_row_page += 1
            if a_imprimir[x_recorre][0] == 'line' and a_imprimir[x_recorre][1] in ['utilidad_retenida',
                                                                                   'isr_pagar',
                                                                                   'reserva_legal_i',
                                                                                   'ajustes_reclasificaciones',
                                                                                   'distribucion_dividendos',
                                                                                   'resultado_ejercicio']:
                worksheet.write(x_rows, 0, a_imprimir[x_recorre][2], frmt_linea)
                worksheet.write(x_rows, 1, a_imprimir[x_recorre][3], frmt_valor)
                worksheet.write(x_rows, 2, '', False)
                x_recorre += 1

            x_rows += 1
            x_row_page += 1
            if a_imprimir[x_recorre][0] == 'line' and a_imprimir[x_recorre][1] in ['resultado_ejercicio']:
                worksheet.write(x_rows, 0, a_imprimir[x_recorre][2], frmt_linea)
                worksheet.write(x_rows, 1, a_imprimir[x_recorre][3], frmt_valor_resultado)
                worksheet.write(x_rows, 2, a_imprimir[x_recorre][4], frmt_valor_resultado)
                x_recorre += 1

            x_rows += 1
            x_row_page += 1
            if a_imprimir[x_recorre][0] == 'foot_total' and a_imprimir[x_recorre][1] in ['total_patrimonio']:
                worksheet.write(x_rows, 0, a_imprimir[x_recorre][2], frmt_titulos)
                worksheet.write(x_rows, 1, '', False)
                worksheet.write(x_rows, 2, a_imprimir[x_recorre][4], frmt_valor_gran_total)
                x_recorre += 1

            x_rows += 1
            x_row_page += 1
            if a_imprimir[x_recorre][0] == 'line' and a_imprimir[x_recorre][1] in ['certificacion']:
                worksheet.merge_range(x_rows+17, 0, x_rows+20, 2, a_imprimir[x_recorre][2], frmt_certificacion)
                x_recorre += 1

            x_rows += 6
            x_row_page += 6
            if a_imprimir[x_recorre][0] == 'line' and a_imprimir[x_recorre][1] in ['fecha']:
                worksheet.merge_range(x_rows+15, 0, x_rows+15, 2, a_imprimir[x_recorre][2], frmt_fecha)
                x_recorre += 1

            #certifica = str(self.certificacion)
            text1 = '______________________' \
                   '\n'+self.representante +\
                '\nRepresentante Legal'
            text2 = '______________________' \
                    '\n'+self.contador + \
                    '\nContador'

            options1 = {
                'width': 205,
                'height': 100,
                'x_offset': 0,
                'y_offset': 0,

                'font': {'color': 'black',
                         'font': 'Arial',
                         'size': 10,
                         'bold': True,
                         },
                'align': {'vertical': 'bottom',
                          'horizontal': 'center'
                          },

            }
            options2 = {
                'width': 205,
                'height': 100,
                'x_offset': 0,
                'y_offset': 0,

                'font': {'color': 'black',
                         'font': 'Arial',
                         'size': 10,
                         'bold': True,
                         },
                'align': {'vertical': 'bottom',
                          'horizontal': 'center'
                          },

            }
            cert_options = {
                'width': 615,
                'height': 100,
                'x_offset': 0,
                'y_offset': 0,

                'font': {'color': 'black',
                         'font': 'Arial',
                         'size': 10,
                         'bold': True,
                         },
                'align': {'vertical': 'top',
                          'horizontal': 'left'
                          },

            }
            #cell = xl_rowcol_to_cell(x_rows+13, 0)
            #worksheet.insert_textbox(cell, certifica, cert_options)
            cell = xl_rowcol_to_cell(x_rows + 17, 0)
            worksheet.insert_textbox(cell, text1, options1)
            cell = xl_rowcol_to_cell(x_rows + 17, 1)
            worksheet.insert_textbox(cell, text2, options2)


        workbook.close()
        self.write({
            'state': 'get',
            'data': base64.b64encode(open(xls_path, 'rb').read()),
            'name': xls_filename
        })
        return {
            'name': 'Cambios al Patrimonio',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new'
        }

class wizard_libro_inventario(models.TransientModel):
    _name = 'wizard.libro.inventario'
    _description = "Wizard Libro de Inventario"
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id)
    end_date = fields.Date(string="Al")
    folio = fields.Integer(string="Folio")
    certificacion = fields.Char(string="Certificación")
    representante = fields.Char(string="Representante Legal")
    contador = fields.Char(string="Contador")
    state = fields.Selection([('choose', 'choose'), ('get', 'get')], default='choose')
    name = fields.Char(string='File Name', readonly=True)
    data = fields.Binary(string='File', readonly=True)

    @api.onchange('company_id')
    def onchange_company_id(self):
        domain = [('id', 'in', self.env.user.company_ids.ids)]
        return {'domain': {'company_id': domain}}

    def go_back(self):
        self.state = 'choose'
        return {
            'name': 'Libro de Inventario',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new'
        }

    def print_xls_libro_inventario(self):

        thMes = ""
        if self.end_date.month == 1:
            thMes = "Enero"
        elif self.end_date.month == 2:
            thMes = "Febrero"
        elif self.end_date.month == 3:
            thMes = "Marzo"
        elif self.end_date.month == 4:
            thMes = "Abril"
        elif self.end_date.month == 5:
            thMes = "Mayo"
        elif self.end_date.month == 6:
            thMes = "Junio"
        elif self.end_date.month == 7:
            thMes = "Julio"
        elif self.end_date.month == 8:
            thMes = "Agosto"
        elif self.end_date.month == 9:
            thMes = "Septiembre"
        elif self.end_date.month == 10:
            thMes = "Octubre"
        elif self.end_date.month == 11:
            thMes = "Noviembre"
        else:
            thMes = "Diciembre"

        xls_filename = 'Libro de Inventario.xlsx'
        temp_dir = tempfile.gettempdir()
        xls_path = os.path.join(temp_dir, xls_filename)
        workbook = xlsxwriter.Workbook(xls_path)
        #workbook = xlsxwriter.Workbook('/tmp/' + xls_filename)
        frmt_folio = workbook.add_format({'bold': False, 'align': 'right', \
                                          'font': 'Arial', 'font_size': 8})
        frmt_encabezado = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                               'font': 'Arial', 'font_size': 8})
        frmt_borde_superior = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                                   'font': 'Arial', 'font_size': 8})
        frmt_cuenta_head_foot = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 8, 'bold': True})
        frmt_cuenta = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 8})
        frmt_van_vacio = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 8, 'border': 1})
        frmt_codigo = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 8, 'bold': True})
        frmt_codigo_c = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 8})
        frmt_codigo_utilidad_ejercicio = workbook.add_format(
            {'align': 'right', 'font': 'Arial', 'font_size': 8, 'bold': True})
        frmt_utilidad_ejercicio = workbook.add_format({'align': 'left', 'font': 'Arial', 'font_size': 8, 'bold': True})
        debe_utilidad_ejercicio = workbook.add_format(
            {'align': 'right', 'font': 'Arial', 'font_size': 8, 'border': 1, 'bold': True})
        haber_utilidad_ejercicio = workbook.add_format(
            {'align': 'right', 'font': 'Arial', 'font_size': 8, 'border': 1, 'bold': True, 'num_format': 'Q#,##0.00'})
        debe_haber_vacio = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 8})
        debe_haber_vacio_gc = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 8})
        debe_haber = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 8, 'num_format': 'Q#,##0.00'})
        debe_haber_gc = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 8, 'num_format': 'Q#,##0.00'})
        debe_haber_nivel_ii = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 8, 'bold': True, 'num_format': 'Q#,##0.00'})
        debe_haber_nivel_i = workbook.add_format({'align': 'right', 'font': 'Arial', 'font_size': 8, 'bold': True, 'num_format': 'Q#,##0.00'})
        debe_haber_van_vienen = workbook.add_format(
            {'align': 'right', 'font': 'Arial', 'font_size': 8, 'bold': True, 'border': 1, 'num_format': 'Q#,##0.00'})
        frmt_van = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', \
                                        'font': 'Arial', 'font_size': 8, 'border': 1, 'num_format': 'Q#,##0.00'})
        frmt_codigo_utilidad_ejercicio.set_bottom(1)
        frmt_codigo_utilidad_ejercicio.set_left(1)
        frmt_utilidad_ejercicio.set_bottom(1)
        haber_utilidad_ejercicio.set_bottom(6)
        frmt_borde_superior.set_bottom(1)
        frmt_codigo.set_left(1)
        frmt_codigo_c.set_left(1)
        frmt_cuenta.set_right(1)
        frmt_cuenta_head_foot.set_right(1)
        debe_haber.set_right(1)
        debe_haber.set_left(1)
        debe_haber_vacio.set_left(1)
        debe_haber_vacio.set_right(1)
        debe_haber_vacio_gc.set_top(1)
        debe_haber_vacio_gc.set_left(1)
        debe_haber_vacio_gc.set_right(1)
        debe_haber_nivel_i.set_right(1)
        debe_haber_nivel_i.set_left(1)
        debe_haber_nivel_i.set_top(1)
        debe_haber_nivel_i.set_bottom(6)
        debe_haber_gc.set_top(1)
        debe_haber_gc.set_left(1)
        debe_haber_gc.set_right(1)
        debe_haber_nivel_ii.set_top(1)
        debe_haber_nivel_ii.set_right(1)
        debe_haber_nivel_ii.set_left(1)

        worksheet = workbook.add_worksheet("Libro de Inventario")
        worksheet.set_portrait()
        worksheet.set_page_view()
        worksheet.set_paper(1)
        worksheet.set_margins(0.7, 0.7, 0.7, 0.7)
        # Tamaños
        worksheet.set_column('A:A', 4)
        worksheet.set_column('B:B', 8)
        worksheet.set_column('C:C', 38)
        worksheet.set_column('D:D', 12)
        worksheet.set_column('E:E', 12)
        worksheet.set_column('F:F', 12)
        # Empieza detalle
        x_rows = 0  # Linea a imprimir
        x_page = 0  # Numero de pagina
        x_max_rows = 47  # Maximo de lineas por pagina
        x_row_page = 0  # Linea actual vrs maximo de lineas
        x_ctrl_nivel_i = ''
        x_ctrl_nivel_ii = ''
        x_ctrl_nivel_gc = ''
        x_ctrl_nivel_c = ''
        x_ctrl_nivel_d = ''
        x_altura = 0
        x_recorre = 0
        x_suma_nivel_i = 0
        x_suma_nivel_ii = 0
        x_suma_nivel_iii = 0
        x_suma_nivel_gc = 0
        x_suma_nivel_c = 0
        x_suma_nivel_d = 0 #
        x_NiveliInicial = 1  # Aca empezamos desde activo
        x_NiveliFinal = 3
        auxrows = 0

        # Calculo de la utilidad del ejercicio
        x_balance_4 = 0
        x_balance_4 = sum(self.env['account.move.line'].search([
            ('account_id.group_id.parent_id.parent_id.code_prefix_start', '=', '4'),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', datetime.strptime(str(self.end_date.year) + '-01-01', "%Y-%m-%d")),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id)]).mapped('balance')) *- 1
            #('move_id.journal_id.name', '!=', 'Partida de Cierre')]).mapped('balance')) *- 1
        x_balance_5 = 0
        x_balance_5 = sum(self.env['account.move.line'].search([
            ('account_id.group_id.parent_id.parent_id.code_prefix_start', '=', '5'),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', datetime.strptime(str(self.end_date.year) + '-01-01', "%Y-%m-%d")),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
            #('move_id.journal_id.name', '!=', 'Partida de Cierre')]).mapped('balance'))
        x_balance_6 = 0
        x_balance_6 = sum(self.env['account.move.line'].search([
            ('account_id.group_id.parent_id.parent_id.code_prefix_start', '=', '6'),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', datetime.strptime(str(self.end_date.year) + '-01-01', "%Y-%m-%d")),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
            #('move_id.journal_id.name', '!=', 'Partida de Cierre')]).mapped('balance'))
        x_balance_7 = 0
        x_balance_7 = sum(self.env['account.move.line'].search([
            ('account_id.group_id.parent_id.parent_id.code_prefix_start', '=', '7'),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', datetime.strptime(str(self.end_date.year) + '-01-01', "%Y-%m-%d")),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id)]).mapped('balance'))*-1
            #('move_id.journal_id.name', '!=', 'Partida de Cierre')]).mapped('balance'))
        x_balance_8 = 0
        x_balance_8 = sum(self.env['account.move.line'].search([
            ('account_id.group_id.parent_id.parent_id.code_prefix_start', '=', '8'),
            ('move_id.state', '=', 'posted'),
            ('date', '>=', datetime.strptime(str(self.end_date.year) + '-01-01', "%Y-%m-%d")),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
            #('move_id.journal_id.name', '!=', 'Partida de Cierre')]).mapped('balance'))

        x_pasivo_capital = sum(self.env['account.move.line'].search([
            ('account_id.group_id.parent_id.parent_id.code_prefix_start', '=', '2'),
            ('move_id.state', '=', 'posted'),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id)]).mapped('balance')) * -1
            # ('move_id.journal_id.name', '!=', 'Partida de Cierre')]).mapped('balance')) * -1
        x_pasivo_capital += sum(self.env['account.move.line'].search([
            ('account_id.group_id.parent_id.parent_id.code_prefix_start', '=', '3'),
            ('move_id.state', '=', 'posted'),
            ('date', '<=', self.end_date),
            ('balance', '!=', 0),
            ('company_id.id', '=', self.company_id.id)]).mapped('balance')) * -1
            # ('move_id.journal_id.name', '!=', 'Partida de Cierre')]).mapped('balance')) * -1

        x_utilidad_ejercicio = (x_balance_4 - x_balance_5 - x_balance_6) + x_balance_7 - x_balance_8
        x_pasivo_capital += x_utilidad_ejercicio
        a_imprimir = []
        while x_NiveliInicial <= x_NiveliFinal: # Principal ciclo para saber que grupos van a ser tomados en cuenta en este caso 4 ingresos 5 cotos 6 gastos
            # Buscamos el id de grupo de la raiz nivel i
            NivelI = self.env['account.group'].search([
                ('company_id.id', '=', self.company_id.id),
                ('parent_id', '=', False),
                ('code_prefix_start', '=', x_NiveliInicial)],
                order="code_prefix_start asc", limit=1)

            if NivelI:
                for x_NivelI in NivelI:
                    x_control_i = 0
                    x_control_i = sum(self.env['account.move.line'].search([
                        ('account_id.group_id.parent_id.parent_id.id', 'in', x_NivelI.ids),
                        ('move_id.state', '=', 'posted'),
                        ('date', '<=', self.end_date),
                        ('balance', '!=', 0),
                        ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
                        #('move_id.journal_id.name', '!=', 'Partida de Cierre')]).mapped('balance'))

                    if x_control_i != 0:
                        a_imprimir.append([])
                        a_imprimir[x_altura].append(x_NivelI.code_prefix_start) # Nivel I 1
                        a_imprimir[x_altura].append('') # Nivel II 101
                        a_imprimir[x_altura].append('')  # Nivel III 10101
                        a_imprimir[x_altura].append(x_NivelI.code_prefix_start) # Codigo Nivel
                        a_imprimir[x_altura].append('')  # Espacio para cantidades
                        a_imprimir[x_altura].append(x_NivelI.name) # Nombre Nivel
                        a_imprimir[x_altura].append(0) # Celda valor 1
                        a_imprimir[x_altura].append(0) # Celda valor 2
                        a_imprimir[x_altura].append(0) # Celda valor 3
                        a_imprimir[x_altura].append('head_nivel_i')  # Tipo de fila
                        a_imprimir[x_altura].append('')  # Cuenta desglozada

                        x_altura += 1
                        # Buscamos el id de grupo del nivel ii que pertenezcan a nivel i
                        NivelII = self.env['account.group'].search([('parent_id.id', 'in', x_NivelI.ids)],
                                                                   order="code_prefix_start asc")
                        if NivelII:
                            for x_NivelII in NivelII:
                                x_control_ii = 0
                                x_control_ii = sum(self.env['account.move.line'].search([
                                    ('account_id.group_id.parent_id.id', 'in', x_NivelII.ids),
                                    ('move_id.state', '=', 'posted'),
                                    ('date', '<=', self.end_date),
                                    ('balance', '!=', 0),
                                    ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
                                    # ('move_id.journal_id.name', '!=', 'Partida de Cierre')]).mapped('balance'))
                                if x_control_ii != 0:
                                    a_imprimir.append([])
                                    a_imprimir[x_altura].append(x_NivelI.code_prefix_start) # Nivel I   1
                                    a_imprimir[x_altura].append(x_NivelII.code_prefix_start) # Nivel II 101
                                    a_imprimir[x_altura].append('')  # Nivel grupo cuenta balance general
                                    a_imprimir[x_altura].append(x_NivelII.code_prefix_start) # Codigo Nivel
                                    a_imprimir[x_altura].append('')  # Espacio para cantidades
                                    a_imprimir[x_altura].append(x_NivelII.name) # Nombre Nivel
                                    a_imprimir[x_altura].append(0) # Celda valor 1
                                    a_imprimir[x_altura].append(0) # Celda valor 2
                                    a_imprimir[x_altura].append(0) # Celda valor 3
                                    a_imprimir[x_altura].append('head_nivel_ii')  # Tipo de fila
                                    a_imprimir[x_altura].append('')  # Cuenta desglozada

                                    x_altura += 1
                                    # Buscamos el id de grupo de cuenta que pertenezca a nivel ii
                                    NivelGrupoCuenta = self.env['account.group'].search(
                                        [('parent_id.id', 'in', x_NivelII.ids)],
                                        order="code_prefix_start asc")
                                    if NivelGrupoCuenta:
                                        for x_NivelGrupoCuenta in NivelGrupoCuenta:
                                            x_control_gc = 0
                                            x_control_gc = sum(self.env['account.move.line'].search([
                                                ('account_id.group_id.id', 'in', x_NivelGrupoCuenta.ids),
                                                ('move_id.state', '=', 'posted'),
                                                ('date', '<=', self.end_date),
                                                ('balance', '!=', 0),
                                                ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
                                                # ('move_id.journal_id.name', '!=', 'Partida de Cierre')]).mapped('balance'))
                                            contador = 0
                                            NivelCuenta2 = self.env['account.account'].search(
                                                [('group_id.id', 'in', x_NivelGrupoCuenta.ids)],
                                                order="code asc")
                                            if NivelCuenta2:
                                                for x_NivelCuenta2 in NivelCuenta2:
                                                    x_control_c2 = sum(self.env['account.move.line'].search([
                                                        ('account_id.id', '=', x_NivelCuenta2.id),
                                                        ('move_id.state', '=', 'posted'),
                                                        ('date', '<=', self.end_date),
                                                        ('balance', '!=', 0),
                                                        ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
                                                    if x_control_c2 != 0:
                                                        contador += 1
                                            if (x_control_gc != 0) or (x_NivelGrupoCuenta.code_prefix_start == '30103' and x_utilidad_ejercicio != 0) or contador != 0:
                                                a_imprimir.append([])
                                                a_imprimir[x_altura].append(x_NivelI.code_prefix_start) # Nivel I   1
                                                a_imprimir[x_altura].append(x_NivelII.code_prefix_start) # Nivel II 101
                                                a_imprimir[x_altura].append(x_NivelGrupoCuenta.code_prefix_start)  # Nivel grupo cuenta balance general
                                                a_imprimir[x_altura].append(x_NivelGrupoCuenta.code_prefix_start) # Codigo Nivel
                                                if x_NivelII.code_prefix_start in ['301']:
                                                    a_imprimir[x_altura].append('')  # Espacio para cantidades
                                                    a_imprimir[x_altura].append(x_NivelGrupoCuenta.name)  # Nombre Nivel
                                                    a_imprimir[x_altura].append(0)  # Celda valor 1
                                                    a_imprimir[x_altura].append(0)  # Celda valor 2
                                                    if x_NivelI.code_prefix_start == '3':
                                                        if x_NivelGrupoCuenta.code_prefix_start == '30103':
                                                            a_imprimir[x_altura].append(x_control_gc + x_utilidad_ejercicio)  # Celda valor 3
                                                        else:
                                                            a_imprimir[x_altura].append(x_control_gc)  # Celda valor 3
                                                    else:
                                                        a_imprimir[x_altura].append(x_control_gc)  # Celda valor 2
                                                    a_imprimir[x_altura].append('foot_nivel_ii')  # Tipo de fila
                                                    a_imprimir[x_altura].append('')  # Cuenta desglozada
                                                    x_altura += 1
                                                    continue
                                                # Aqui deberia ir un else
                                                a_imprimir[x_altura].append('')  # Espacio para cantidades
                                                a_imprimir[x_altura].append(x_NivelGrupoCuenta.name) # Nombre Nivel
                                                a_imprimir[x_altura].append(0) # Celda valor 1
                                                a_imprimir[x_altura].append(0) # Celda valor 2
                                                a_imprimir[x_altura].append(0) # Celda valor 3
                                                a_imprimir[x_altura].append('head_nivel_gc')  # Tipo de fila
                                                a_imprimir[x_altura].append('')  # Cuenta desglozada
                                                x_altura += 1
                                                NivelCuenta = self.env['account.account'].search(
                                                    [('group_id.id', 'in', x_NivelGrupoCuenta.ids)],
                                                    order="code asc")
                                                if NivelCuenta:
                                                    for x_NivelCuenta in NivelCuenta:
                                                        x_control_c = sum(self.env['account.move.line'].search([
                                                            ('account_id.id', '=', x_NivelCuenta.id),
                                                            ('move_id.state', '=', 'posted'),
                                                            ('date', '<=', self.end_date),
                                                            ('balance', '!=', 0),
                                                            ('company_id.id', '=', self.company_id.id)]).mapped('balance'))
                                                            #('move_id.journal_id.name', '!=', 'Partida de Cierre')]).mapped('balance'))
                                                        if (x_control_c != 0) or (x_NivelCuenta.code == '3010301' and x_utilidad_ejercicio != 0):
                                                            a_imprimir.append([])
                                                            a_imprimir[x_altura].append(x_NivelI.code_prefix_start) # Nivel I   1
                                                            a_imprimir[x_altura].append(x_NivelII.code_prefix_start) # Nivel II 101
                                                            a_imprimir[x_altura].append(x_NivelGrupoCuenta.code_prefix_start)  # Nivel grupo cuenta balance general
                                                            a_imprimir[x_altura].append(x_NivelCuenta.code) # Codigo Nivel
                                                            a_imprimir[x_altura].append('')  # Espacio para cantidades
                                                            a_imprimir[x_altura].append(x_NivelCuenta.name) # Nombre Nivel

                                                            if x_NivelGrupoCuenta.code_prefix_start in ['10103', '10202', '20103', '20101', '20201'] or (x_NivelGrupoCuenta.code_prefix_start == '10201' and x_NivelCuenta.code == '1020105'): # Para desglozar Cuentas por cobrar comerciales y no comerciales
                                                                a_imprimir[x_altura].append(0) # Celda valor 1
                                                                a_imprimir[x_altura].append('') # Celda valor 2
                                                                a_imprimir[x_altura].append(0) # Celda valor 3
                                                                a_imprimir[x_altura].append('nivel_c')  # Tipo de fila
                                                                a_imprimir[x_altura].append('')  # Cuenta desglozada
                                                                x_altura += 1
                                                                x_desglozar = None
                                                                x_desglozar = self.env['account.move.line'].read_group([
                                                                        ('account_id.group_id.id', 'in',x_NivelGrupoCuenta.ids),
                                                                        ('account_id.code', '=', x_NivelCuenta.code),
                                                                        ('move_id.state', '=', 'posted'),
                                                                        ('date', '<=', self.end_date),
                                                                        ('balance', '!=', 0),
                                                                        ('company_id.id', '=', self.company_id.id),
                                                                        #('move_id.journal_id.name', '!=', 'Partida de Cierre'),
                                                                        ('partner_id', '!=', False)],
                                                                        fields=['account_id.code', 'balance', 'partner_id.name'],
                                                                        groupby=['partner_id', 'account_id'])

                                                                if x_desglozar: # Si hay registros para desglozar
                                                                    for x_desglozar_cxc in x_desglozar: # Recorremos los registros para desglozar
                                                                        if x_desglozar_cxc['balance'] != 0:
                                                                            a_imprimir.append([])
                                                                            a_imprimir[x_altura].append(x_NivelI.code_prefix_start)  # Nivel I   1
                                                                            a_imprimir[x_altura].append(x_NivelII.code_prefix_start)  # Nivel II 101
                                                                            a_imprimir[x_altura].append(x_NivelGrupoCuenta.code_prefix_start)  # Nivel grupo cuenta balance general
                                                                            a_imprimir[x_altura].append(x_NivelCuenta.code)  # Codigo Nivel
                                                                            a_imprimir[x_altura].append('')  # Espacio para cantidades
                                                                            partner_id_tuple = x_desglozar_cxc.get('partner_id')
                                                                            partner_name = partner_id_tuple[1] if partner_id_tuple else False
                                                                            if partner_name:
                                                                                a_imprimir[x_altura].append(str(partner_name))  # Nombre Nivel
                                                                            else:
                                                                                a_imprimir[x_altura].append('')  # Nombre Nivel
                                                                            a_imprimir[x_altura].append(x_desglozar_cxc['balance'])  # Celda valor 1
                                                                            a_imprimir[x_altura].append(0)  # Celda valor 2
                                                                            a_imprimir[x_altura].append(0)  # Celda valor 3
                                                                            a_imprimir[x_altura].append('nivel_d')  # Tipo de fila
                                                                            a_imprimir[x_altura].append(x_NivelCuenta.code)  # Cuenta desglozada
                                                                            x_altura += 1
                                                                x_desglozar_ii = None
                                                                x_desglozar_ii = self.env['account.move.line'].search([
                                                                    ('account_id.group_id.id', 'in', x_NivelGrupoCuenta.ids),
                                                                    ('account_id.code', '=', x_NivelCuenta.code),
                                                                    ('move_id.state', '=', 'posted'),
                                                                    ('date', '<=', self.end_date),
                                                                    ('balance', '!=', 0),
                                                                    ('company_id.id', '=', self.company_id.id),
                                                                    #('move_id.journal_id.name', '!=','Partida de Cierre'),
                                                                    ('partner_id', '=', False)])
                                                                if x_desglozar_ii: # Si hay registros para desglozar
                                                                    for x_desglozar_cxc_ii in x_desglozar_ii: # Recorremos los registros para desglozar
                                                                        a_imprimir.append([])
                                                                        a_imprimir[x_altura].append(x_NivelI.code_prefix_start)  # Nivel I   1
                                                                        a_imprimir[x_altura].append(x_NivelII.code_prefix_start)  # Nivel II 101
                                                                        a_imprimir[x_altura].append(x_NivelGrupoCuenta.code_prefix_start)  # Nivel grupo cuenta balance general
                                                                        a_imprimir[x_altura].append(x_NivelCuenta.code)  # Codigo Nivel
                                                                        a_imprimir[x_altura].append('')  # Espacio para cantidades
                                                                        a_imprimir[x_altura].append(x_desglozar_cxc_ii.move_id.ref)  # Referencia de movimiento
                                                                        a_imprimir[x_altura].append(x_desglozar_cxc_ii.balance)  # Celda valor 1
                                                                        a_imprimir[x_altura].append(0)  # Celda valor 2
                                                                        a_imprimir[x_altura].append(0)  # Celda valor 3
                                                                        a_imprimir[x_altura].append('nivel_d')  # Tipo de fila
                                                                        a_imprimir[x_altura].append(x_NivelCuenta.code)  # Cuenta desglozada
                                                                        x_altura += 1

                                                                a_imprimir.append([])
                                                                a_imprimir[x_altura].append(x_NivelI.code_prefix_start)  # Nivel I   1
                                                                a_imprimir[x_altura].append(x_NivelII.code_prefix_start)  # Nivel II 101
                                                                a_imprimir[x_altura].append(x_NivelGrupoCuenta.code_prefix_start)  # Nivel grupo cuenta balance general
                                                                a_imprimir[x_altura].append(x_NivelCuenta.code)  # Codigo Nivel
                                                                a_imprimir[x_altura].append('')  # Espacio para cantidades
                                                                a_imprimir[x_altura].append('Suma de ' + x_NivelCuenta.name)  # Nombre Nivel

                                                            # DESDE AQUI ---------------------------------------------------------------------------
                                                            if x_NivelGrupoCuenta.code_prefix_start == '10104':  # Para desglozar Cuentas por cobrar comerciales y no comerciales
                                                                a_imprimir[x_altura].append(0)  # Celda valor 1
                                                                a_imprimir[x_altura].append('')  # Celda valor 2
                                                                a_imprimir[x_altura].append(0)  # Celda valor 3
                                                                a_imprimir[x_altura].append('nivel_c')  # Tipo de fila
                                                                a_imprimir[x_altura].append('')  # Cuenta desglozada
                                                                x_altura += 1
                                                                x_desglozar = None
                                                                x_desglozar = self.env['account.move.line'].read_group([
                                                                    ('account_id.group_id.id', 'in', x_NivelGrupoCuenta.ids),
                                                                    ('account_id.code', '=', x_NivelCuenta.code),
                                                                    ('move_id.state', '=', 'posted'),
                                                                    ('date', '<=', self.end_date),
                                                                    ('balance', '!=', 0),
                                                                    ('company_id.id', '=', self.company_id.id),
                                                                    #('move_id.journal_id.name', '!=', 'Partida de Cierre'),
                                                                    ('product_id', '!=', False)],
                                                                    fields=['account_id.code', 'balance', 'product_id.name', 'quantity'],
                                                                    groupby=['product_id', 'account_id'])
                                                                if x_desglozar:  # Si hay registros para desglozar
                                                                    for x_desglozar_cxc in x_desglozar:  # Recorremos los registros para desglozar
                                                                        if x_desglozar_cxc['balance'] != 0:
                                                                            a_imprimir.append([])
                                                                            a_imprimir[x_altura].append(x_NivelI.code_prefix_start)  # Nivel I   1
                                                                            a_imprimir[x_altura].append(x_NivelII.code_prefix_start)  # Nivel II 101
                                                                            a_imprimir[x_altura].append(x_NivelGrupoCuenta.code_prefix_start)  # Nivel grupo cuenta balance general
                                                                            a_imprimir[x_altura].append(x_NivelCuenta.code)  # Codigo Nivel
                                                                            a_imprimir[x_altura].append(x_desglozar_cxc['quantity'])  # Celda valor 1
                                                                            product_id_tuple = x_desglozar_cxc.get('product_id')
                                                                            product_name = product_id_tuple[1] if product_id_tuple else False
                                                                            if product_name:
                                                                                a_imprimir[x_altura].append(str(product_name))  # Nombre Nivel
                                                                            else:
                                                                                a_imprimir[x_altura].append('')
                                                                            a_imprimir[x_altura].append(x_desglozar_cxc['balance'])  # Celda valor 1
                                                                            a_imprimir[x_altura].append(0)  # Celda valor 2
                                                                            a_imprimir[x_altura].append(0)  # Celda valor 3
                                                                            a_imprimir[x_altura].append('nivel_d')  # Tipo de fila
                                                                            a_imprimir[x_altura].append(x_NivelCuenta.code)  # Cuenta desglozada
                                                                            x_altura += 1
                                                                x_desglozar_ii = None
                                                                x_desglozar_ii = self.env['account.move.line'].search(
                                                                    [('account_id.group_id.id', 'in', x_NivelGrupoCuenta.ids),
                                                                    ('account_id.code', '=', x_NivelCuenta.code),
                                                                    ('move_id.state', '=', 'posted'),
                                                                    ('date', '<=', self.end_date),
                                                                    ('balance', '!=', 0),
                                                                    ('company_id.id', '=', self.company_id.id),
                                                                    #('move_id.journal_id.name', '!=', 'Partida de Cierre'),
                                                                    ('product_id', '=', False)])
                                                                if x_desglozar_ii:  # Si hay registros para desglozar
                                                                    for x_desglozar_cxc_ii in x_desglozar_ii:  # Recorremos los registros para desglozar
                                                                        a_imprimir.append([])
                                                                        a_imprimir[x_altura].append(x_NivelI.code_prefix_start)  # Nivel I   1
                                                                        a_imprimir[x_altura].append(x_NivelII.code_prefix_start)  # Nivel II 101
                                                                        a_imprimir[x_altura].append(x_NivelGrupoCuenta.code_prefix_start)  # Nivel grupo cuenta balance general
                                                                        a_imprimir[x_altura].append(x_NivelCuenta.code)  # Codigo Nivel
                                                                        a_imprimir[x_altura].append('')  # Espacio para cantidades
                                                                        a_imprimir[x_altura].append(x_desglozar_cxc_ii.move_id.ref)  # Referencia de movimiento
                                                                        a_imprimir[x_altura].append(x_desglozar_cxc_ii.balance)  # Celda valor 1
                                                                        a_imprimir[x_altura].append(0)  # Celda valor 2
                                                                        a_imprimir[x_altura].append(0)  # Celda valor 3
                                                                        a_imprimir[x_altura].append('nivel_d')  # Tipo de fila
                                                                        a_imprimir[x_altura].append(x_NivelCuenta.code)  # Cuenta desglozada
                                                                        x_altura += 1

                                                                a_imprimir.append([])
                                                                a_imprimir[x_altura].append(x_NivelI.code_prefix_start)  # Nivel I   1
                                                                a_imprimir[x_altura].append(x_NivelII.code_prefix_start)  # Nivel II 101
                                                                a_imprimir[x_altura].append(x_NivelGrupoCuenta.code_prefix_start)  # Nivel grupo cuenta balance general
                                                                a_imprimir[x_altura].append(x_NivelCuenta.code)  # Codigo Nivel
                                                                a_imprimir[x_altura].append('')  # Espacio para cantidades
                                                                a_imprimir[x_altura].append('Suma de '+x_NivelCuenta.name)  # Nombre Nivel
                                                                # HASTa ACA ----------------------------------------------------------------------------

                                                            a_imprimir[x_altura].append(0)  # Celda valor 1
                                                            if x_NivelI.code_prefix_start == '3':
                                                                if x_NivelCuenta.code == '3010301':
                                                                    a_imprimir[x_altura].append(x_control_c + x_utilidad_ejercicio) # Celda valor 2
                                                                else:
                                                                    a_imprimir[x_altura].append(x_control_c) # Celda valor 2
                                                            else:
                                                                a_imprimir[x_altura].append(x_control_c) # Celda valor 2
                                                            a_imprimir[x_altura].append(0) # Celda valor 3
                                                            a_imprimir[x_altura].append('nivel_c')  # Tipo de fila
                                                            a_imprimir[x_altura].append('')  # cuenta desglozada
                                                            x_altura += 1
                                                # Pie de cuenta
                                                a_imprimir.append([])
                                                a_imprimir[x_altura].append(x_NivelI.code_prefix_start) # Nivel I   1
                                                a_imprimir[x_altura].append(x_NivelII.code_prefix_start) # Nivel II 101
                                                a_imprimir[x_altura].append(x_NivelGrupoCuenta.code_prefix_start)  # Nivel grupo cuenta balance general
                                                a_imprimir[x_altura].append('')  # Codigo Nivel
                                                a_imprimir[x_altura].append('')  # Espacio para cantidades
                                                a_imprimir[x_altura].append(x_NivelGrupoCuenta.name) # Nombre Nivel
                                                a_imprimir[x_altura].append(0) # Celda valor 1
                                                if x_NivelI.code_prefix_start == '3':
                                                    if x_NivelGrupoCuenta.code_prefix_start == '30103':
                                                        a_imprimir[x_altura].append(x_control_gc + x_utilidad_ejercicio) # Celda valor 2
                                                    else:
                                                        a_imprimir[x_altura].append(x_control_gc) # Celda valor 2
                                                else:
                                                    a_imprimir[x_altura].append(x_control_gc) # Celda valor 2
                                                a_imprimir[x_altura].append(0) # Celda valor 3
                                                a_imprimir[x_altura].append('foot_nivel_gc')  # Tipo de fila
                                                a_imprimir[x_altura].append('')  # cuenta desglozada
                                                x_altura += 1
                                    a_imprimir.append([])
                                    a_imprimir[x_altura].append(x_NivelI.code_prefix_start) # Nivel I   1
                                    a_imprimir[x_altura].append(x_NivelII.code_prefix_start) # Nivel II 101
                                    a_imprimir[x_altura].append('')  # Nivel grupo cuenta balance general
                                    a_imprimir[x_altura].append('')  # Codigo Nivel
                                    a_imprimir[x_altura].append('')  # Espacio para cantidades
                                    a_imprimir[x_altura].append('   Suma '+ x_NivelII.name) # Nombre Nivel
                                    a_imprimir[x_altura].append(0) # Celda valor 1
                                    a_imprimir[x_altura].append(0) # Celda valor 2
                                    if x_NivelI.code_prefix_start == '3':
                                        if x_NivelII.code_prefix_start == '301':
                                            a_imprimir[x_altura].append(x_control_ii + x_utilidad_ejercicio) # Celda valor 3
                                        else:
                                            a_imprimir[x_altura].append(x_control_ii) # Celda valor 3
                                    else:
                                        a_imprimir[x_altura].append(x_control_ii) # Celda valor 3
                                    a_imprimir[x_altura].append('foot_nivel_ii')  # Tipo de fila
                                    a_imprimir[x_altura].append('')  # cuenta desglozada
                                    x_altura += 1
                        a_imprimir.append([])
                        a_imprimir[x_altura].append(x_NivelI.code_prefix_start) # Nivel I   1
                        a_imprimir[x_altura].append(x_NivelII.code_prefix_start) # Nivel II 101
                        a_imprimir[x_altura].append('')  # Nivel grupo cuenta balance general
                        a_imprimir[x_altura].append('') # Codigo Nivel
                        a_imprimir[x_altura].append('')  # Espacio para cantidades
                        a_imprimir[x_altura].append('   SUMA TOTAL DEL ' + x_NivelI.name) # Nombre Nivel
                        a_imprimir[x_altura].append(0) # Celda valor 1
                        a_imprimir[x_altura].append(0) # Celda valor 2
                        if x_NivelI.code_prefix_start == '3':
                            if x_NivelI.code_prefix_start == '3':
                                a_imprimir[x_altura].append(x_control_i + x_utilidad_ejercicio) # Celda valor 3
                            else:
                                a_imprimir[x_altura].append(x_control_i) # Celda valor 3
                        else:
                            a_imprimir[x_altura].append(x_control_i) # Celda valor 3
                        a_imprimir[x_altura].append('foot_nivel_i')  # Tipo de fila
                        a_imprimir[x_altura].append('')  # cuenta desglozada
                        x_altura += 1
            x_NiveliInicial += 1

        a_imprimir.append([])
        a_imprimir[x_altura].append('') # Nivel I   1
        a_imprimir[x_altura].append('') # Nivel II 101
        a_imprimir[x_altura].append('')  # Nivel grupo cuenta balance general
        a_imprimir[x_altura].append('') # Codigo Nivel
        a_imprimir[x_altura].append('')  # Espacio para cantidades
        a_imprimir[x_altura].append('   SUMA TOTAL DEL PASIVO Y CAPITAL') # Nombre Nivel
        a_imprimir[x_altura].append(0) # Celda valor 1
        a_imprimir[x_altura].append(0) # Celda valor 2
        a_imprimir[x_altura].append(x_pasivo_capital) # Celda valor 3
        a_imprimir[x_altura].append('utilidad_ejercicio')  # Tipo de fila
        a_imprimir[x_altura].append('')  # cuenta desglozada

        if a_imprimir:
            x_recorre = 0
            while x_recorre < len(a_imprimir):

                if x_row_page < x_max_rows:  # Estamos en ciclo
                    # ---------------------------- Encabezado ----------------------------------------------------------
                    if x_row_page == 0:  # Nueva pagina

                        worksheet.write(x_rows, 5, "Folio: " + str(self.folio + x_page), frmt_folio)
                        x_rows += 1
                        x_row_page += 1

                        worksheet.merge_range(x_rows, 0, x_rows, 5, self.company_id.name,
                                              frmt_encabezado)  # Encabezado
                        x_rows += 1
                        x_row_page += 1

                        worksheet.merge_range(x_rows, 0, x_rows, 5, "NIT: " + self.company_id.partner_id.vat,
                                              frmt_encabezado)  # Encabezado
                        x_rows += 1
                        x_row_page += 1

                        worksheet.merge_range(x_rows, 0, x_rows, 5, "Libro de Inventario", frmt_encabezado)  # Encabezado
                        x_rows += 1
                        x_row_page += 1

                        worksheet.merge_range(x_rows, 0, x_rows, 5,
                                              str("Al " + str(self.end_date.day) + " de " + thMes + " de " + str(
                                                  self.end_date.year)), frmt_encabezado)  # Encabezado
                        x_rows += 1
                        x_row_page += 1

                        worksheet.merge_range(x_rows, 0, x_rows, 5, "(EXPRESADO EN QUETZALES)",
                                              frmt_encabezado)  # Encabezado
                        x_rows += 1
                        x_row_page += 1
                        # Aca es solo para cerrar el marco
                        worksheet.write(x_rows, 0, '', frmt_borde_superior)
                        worksheet.write(x_rows, 1, '', frmt_borde_superior)
                        worksheet.write(x_rows, 2, '', frmt_borde_superior)
                        worksheet.write(x_rows, 3, '', frmt_borde_superior)
                        worksheet.write(x_rows, 4, '', frmt_borde_superior)
                        worksheet.write(x_rows, 5, '', frmt_borde_superior)
                        x_rows += 1
                        x_row_page += 1

                        if a_imprimir[x_recorre][9] == 'head_nivel_i' \
                                or a_imprimir[x_recorre][9] == 'head_nivel_ii' \
                                or a_imprimir[x_recorre][9] == 'head_nivel_gc':
                            worksheet.write(x_rows, 0, '', debe_haber_vacio)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][5], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 3, '', debe_haber_vacio)
                            worksheet.write(x_rows, 4, '', debe_haber_vacio)
                            worksheet.write(x_rows, 5, '', debe_haber_vacio)
                        elif a_imprimir[x_recorre][9] == 'nivel_c':
                            worksheet.write(x_rows, 0, '', debe_haber_vacio)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][5], frmt_cuenta)
                            worksheet.write(x_rows, 3, '', debe_haber_vacio)
                            worksheet.write(x_rows, 4, a_imprimir[x_recorre][7], debe_haber)
                            worksheet.write(x_rows, 5, '', debe_haber_vacio)
                        elif a_imprimir[x_recorre][9] == 'nivel_d':
                            if a_imprimir[x_recorre][4] == '':
                                worksheet.write(x_rows, 0, '', debe_haber_vacio)
                            else:
                                worksheet.write(x_rows, 0, a_imprimir[x_recorre][4], debe_haber_vacio)
                            worksheet.write(x_rows, 1, '', frmt_codigo)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][5], frmt_cuenta)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber)
                            worksheet.write(x_rows, 4, '', debe_haber_vacio)
                            worksheet.write(x_rows, 5, '', debe_haber_vacio)
                        elif a_imprimir[x_recorre][9] == 'foot_nivel_gc':
                            worksheet.write(x_rows, 0, '', debe_haber_vacio)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][5], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 3, '', debe_haber_vacio_gc)
                            worksheet.write(x_rows, 4, '', debe_haber_vacio_gc)
                            worksheet.write(x_rows, 5, a_imprimir[x_recorre][7], debe_haber_gc)
                        elif a_imprimir[x_recorre][9] == 'foot_nivel_ii':
                            worksheet.write(x_rows, 0, '', debe_haber_vacio)
                            worksheet.write(x_rows, 1, '', frmt_codigo)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][5], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 3, '', debe_haber_nivel_ii)
                            worksheet.write(x_rows, 4, '', debe_haber_nivel_ii)
                            worksheet.write(x_rows, 5, a_imprimir[x_recorre][8], debe_haber_nivel_ii)
                        elif a_imprimir[x_recorre][9] == 'foot_nivel_i':
                            worksheet.write(x_rows, 0, '', debe_haber_vacio)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][5], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 3, '', debe_haber_nivel_ii)
                            worksheet.write(x_rows, 4, '', debe_haber_nivel_ii)
                            worksheet.write(x_rows, 5, a_imprimir[x_recorre][8], debe_haber_nivel_i)
                        else:  # a_imprimir[x_recorre][2] == 'utilidad_ejercicio': # utilidad ejercicio
                            worksheet.write(x_rows, 0, '', debe_haber_vacio)
                            worksheet.write(x_rows, 1, '', frmt_codigo_utilidad_ejercicio)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][5], frmt_utilidad_ejercicio)
                            worksheet.write(x_rows, 3, '', debe_utilidad_ejercicio)
                            worksheet.write(x_rows, 4, '', debe_utilidad_ejercicio)
                            worksheet.write(x_rows, 5, a_imprimir[x_recorre][8], haber_utilidad_ejercicio)
                        x_rows += 1
                        x_row_page += 1

                    # ---------------------------- Fin Encabezado ----------------------------------------------------------
                    elif x_row_page > 0 and x_row_page == x_max_rows - 1:  # Estamos en la penultima linea
                        x_row_page = 0
                        worksheet.merge_range(x_rows, 0, x_rows, 2, "VAN", frmt_van)
                        worksheet.write(x_rows, 3, float(x_suma_nivel_d), debe_haber_van_vienen)
                        worksheet.write(x_rows, 4, float(x_suma_nivel_c), debe_haber_van_vienen)
                        worksheet.write(x_rows, 5, float(x_suma_nivel_gc), debe_haber_van_vienen)
                        # Encabezado 1
                        x_rows += 1
                        #x_row_page += 1
                        x_page += 1

                        worksheet.write(x_rows, 5, "Folio: " + str(self.folio + x_page), frmt_folio)
                        x_rows += 1
                        x_row_page += 1

                        worksheet.merge_range(x_rows, 0, x_rows, 5, self.company_id.name,
                                              frmt_encabezado)  # Encabezado
                        x_rows += 1
                        x_row_page += 1

                        worksheet.merge_range(x_rows, 0, x_rows, 5, "NIT: " + self.company_id.partner_id.vat,
                                              frmt_encabezado)  # Encabezado
                        x_rows += 1
                        x_row_page += 1

                        worksheet.merge_range(x_rows, 0, x_rows, 5, "Libro de Inventario",
                                              frmt_encabezado)  # Encabezado
                        x_rows += 1
                        x_row_page += 1

                        worksheet.merge_range(x_rows, 0, x_rows, 5,
                                              str("Al " + str(self.end_date.day) + " de " + thMes + " de " + str(
                                                  self.end_date.year)), frmt_encabezado)  # Encabezado
                        x_rows += 1
                        x_row_page += 1

                        worksheet.merge_range(x_rows, 0, x_rows, 5, "(EXPRESADO EN QUETZALES)",
                                              frmt_encabezado)  # Encabezado
                        x_rows += 1
                        x_row_page += 1

                        worksheet.write(x_rows, 0, '', frmt_borde_superior)
                        worksheet.write(x_rows, 1, '', frmt_borde_superior)
                        worksheet.write(x_rows, 2, '', frmt_borde_superior)
                        worksheet.write(x_rows, 3, '', frmt_borde_superior)
                        worksheet.write(x_rows, 4, '', frmt_borde_superior)
                        worksheet.write(x_rows, 5, '', frmt_borde_superior)
                        x_rows += 1
                        x_row_page += 1

                        worksheet.merge_range(x_rows, 0, x_rows, 2, "VIENEN", frmt_van)
                        worksheet.write(x_rows, 3, float(x_suma_nivel_d), debe_haber_van_vienen)
                        worksheet.write(x_rows, 4, float(x_suma_nivel_c), debe_haber_van_vienen)
                        worksheet.write(x_rows, 5, float(x_suma_nivel_gc), debe_haber_van_vienen)
                        x_rows += 1
                        x_row_page += 1

                        if a_imprimir[x_recorre][9] == 'head_nivel_i' \
                                or a_imprimir[x_recorre][9] == 'head_nivel_ii' \
                                or a_imprimir[x_recorre][9] == 'head_nivel_gc':
                            worksheet.write(x_rows, 0, '', debe_haber_vacio)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][5], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 3, '', debe_haber_vacio)
                            worksheet.write(x_rows, 4, '', debe_haber_vacio)
                            worksheet.write(x_rows, 5, '', debe_haber_vacio)
                        elif a_imprimir[x_recorre][9] == 'nivel_c':
                            worksheet.write(x_rows, 0, '', debe_haber_vacio)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][5], frmt_cuenta)
                            worksheet.write(x_rows, 3, '', debe_haber_vacio)
                            worksheet.write(x_rows, 4, a_imprimir[x_recorre][7], debe_haber)
                            worksheet.write(x_rows, 5, '', debe_haber_vacio)
                        elif a_imprimir[x_recorre][9] == 'nivel_d':
                            if a_imprimir[x_recorre][4] == '':
                                worksheet.write(x_rows, 0, '', debe_haber_vacio)
                            else:
                                worksheet.write(x_rows, 0, a_imprimir[x_recorre][4], debe_haber_vacio)
                            worksheet.write(x_rows, 1, '', frmt_codigo)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][5], frmt_cuenta)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber)
                            worksheet.write(x_rows, 4, '', debe_haber_vacio)
                            worksheet.write(x_rows, 5, '', debe_haber_vacio)
                        elif a_imprimir[x_recorre][9] == 'foot_nivel_gc':
                            worksheet.write(x_rows, 0, '', debe_haber_vacio)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][5], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 3, '', debe_haber_vacio_gc)
                            worksheet.write(x_rows, 4, '', debe_haber_vacio_gc)
                            worksheet.write(x_rows, 5, a_imprimir[x_recorre][7], debe_haber_gc)
                        elif a_imprimir[x_recorre][9] == 'foot_nivel_ii':
                            worksheet.write(x_rows, 0, '', debe_haber_vacio)
                            worksheet.write(x_rows, 1, '', frmt_codigo)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][5], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 3, '', debe_haber_nivel_ii)
                            worksheet.write(x_rows, 4, '', debe_haber_nivel_ii)
                            worksheet.write(x_rows, 5, a_imprimir[x_recorre][8], debe_haber_nivel_ii)
                        elif a_imprimir[x_recorre][9] == 'foot_nivel_i':
                            worksheet.write(x_rows, 0, '', debe_haber_vacio)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][5], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 3, '', debe_haber_nivel_ii)
                            worksheet.write(x_rows, 4, '', debe_haber_nivel_ii)
                            worksheet.write(x_rows, 5, a_imprimir[x_recorre][8], debe_haber_nivel_i)
                        else:  # a_imprimir[x_recorre][2] == 'utilidad_ejercicio': # utilidad ejercicio
                            worksheet.write(x_rows, 0, '', debe_haber_vacio)
                            worksheet.write(x_rows, 1, '', frmt_codigo_utilidad_ejercicio)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][5], frmt_utilidad_ejercicio)
                            worksheet.write(x_rows, 3, '', debe_utilidad_ejercicio)
                            worksheet.write(x_rows, 4, '', debe_utilidad_ejercicio)
                            worksheet.write(x_rows, 5, a_imprimir[x_recorre][8], haber_utilidad_ejercicio)
                        x_rows += 1
                        x_row_page += 1

                    else:  # No estamos en la ultima linea, estamos en la misma cuenta
                        if a_imprimir[x_recorre][9] == 'head_nivel_i' \
                                or a_imprimir[x_recorre][9] == 'head_nivel_ii' \
                                or a_imprimir[x_recorre][9] == 'head_nivel_gc':
                            worksheet.write(x_rows, 0, '', debe_haber_vacio)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][5], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 3, '', debe_haber_vacio)
                            worksheet.write(x_rows, 4, '', debe_haber_vacio)
                            worksheet.write(x_rows, 5, '', debe_haber_vacio)
                        elif a_imprimir[x_recorre][9] == 'nivel_c':
                            worksheet.write(x_rows, 0, '', debe_haber_vacio)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][5], frmt_cuenta)
                            worksheet.write(x_rows, 3, '', debe_haber_vacio)
                            worksheet.write(x_rows, 4, a_imprimir[x_recorre][7], debe_haber)
                            worksheet.write(x_rows, 5, '', debe_haber_vacio)
                        elif a_imprimir[x_recorre][9] == 'nivel_d':
                            if a_imprimir[x_recorre][4] == '':
                                worksheet.write(x_rows, 0, '', debe_haber_vacio)
                            else:
                                worksheet.write(x_rows, 0, a_imprimir[x_recorre][4], debe_haber_vacio)
                            worksheet.write(x_rows, 1, '', frmt_codigo)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][5], frmt_cuenta)
                            worksheet.write(x_rows, 3, a_imprimir[x_recorre][6], debe_haber)
                            worksheet.write(x_rows, 4, '', debe_haber_vacio)
                            worksheet.write(x_rows, 5, '', debe_haber_vacio)
                        elif a_imprimir[x_recorre][9] == 'foot_nivel_gc':
                            worksheet.write(x_rows, 0, '', debe_haber_vacio)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][5], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 3, '', debe_haber_vacio_gc)
                            worksheet.write(x_rows, 4, '', debe_haber_vacio_gc)
                            worksheet.write(x_rows, 5, a_imprimir[x_recorre][7], debe_haber_gc)
                        elif a_imprimir[x_recorre][9] == 'foot_nivel_ii':
                            worksheet.write(x_rows, 0, '', debe_haber_vacio)
                            worksheet.write(x_rows, 1, '', frmt_codigo)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][5], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 3, '', debe_haber_nivel_ii)
                            worksheet.write(x_rows, 4, '', debe_haber_nivel_ii)
                            worksheet.write(x_rows, 5, a_imprimir[x_recorre][8], debe_haber_nivel_ii)
                        elif a_imprimir[x_recorre][9] == 'foot_nivel_i':
                            worksheet.write(x_rows, 0, '', debe_haber_vacio)
                            worksheet.write(x_rows, 1, a_imprimir[x_recorre][3], frmt_codigo)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][5], frmt_cuenta_head_foot)
                            worksheet.write(x_rows, 3, '', debe_haber_nivel_ii)
                            worksheet.write(x_rows, 4, '', debe_haber_nivel_ii)
                            worksheet.write(x_rows, 5, a_imprimir[x_recorre][8], debe_haber_nivel_i)
                        else:  # a_imprimir[x_recorre][2] == 'utilidad_ejercicio': # utilidad ejercicio
                            worksheet.write(x_rows, 0, '', debe_haber_vacio)
                            worksheet.write(x_rows, 1, '', frmt_codigo_utilidad_ejercicio)
                            worksheet.write(x_rows, 2, a_imprimir[x_recorre][5], frmt_utilidad_ejercicio)
                            worksheet.write(x_rows, 3, '', debe_utilidad_ejercicio)
                            worksheet.write(x_rows, 4, '', debe_utilidad_ejercicio)
                            worksheet.write(x_rows, 5, a_imprimir[x_recorre][8], haber_utilidad_ejercicio)
                        x_rows += 1
                        x_row_page += 1

                if x_ctrl_nivel_i == a_imprimir[x_recorre][0] \
                        and x_ctrl_nivel_ii == a_imprimir[x_recorre][1] \
                        and x_ctrl_nivel_gc == a_imprimir[x_recorre][2] \
                        and x_ctrl_nivel_c == a_imprimir[x_recorre][3] \
                        and x_ctrl_nivel_d == a_imprimir[x_recorre][10]:
                    x_suma_nivel_d += float(a_imprimir[x_recorre][6])
                    if a_imprimir[x_recorre][7] == '':
                        x_suma_nivel_c += 0 + float(a_imprimir[x_recorre][6])
                        x_suma_nivel_gc += 0 + float(a_imprimir[x_recorre][6])
                    else:
                        x_suma_nivel_gc += float(a_imprimir[x_recorre][7]) + float(a_imprimir[x_recorre][6])
                        x_suma_nivel_c += float(a_imprimir[x_recorre][7]) + float(a_imprimir[x_recorre][6])


                elif x_ctrl_nivel_i == a_imprimir[x_recorre][0] \
                        and x_ctrl_nivel_ii == a_imprimir[x_recorre][1] \
                        and x_ctrl_nivel_gc == a_imprimir[x_recorre][2] \
                        and x_ctrl_nivel_c == a_imprimir[x_recorre][3] \
                        and x_ctrl_nivel_d != a_imprimir[x_recorre][10]:

                    x_suma_nivel_d = 0
                    if a_imprimir[x_recorre][7] == '':
                        x_suma_nivel_c += 0
                        x_suma_nivel_gc += 0
                    else:
                        x_suma_nivel_c += float(a_imprimir[x_recorre][7])
                        x_suma_nivel_gc += float(a_imprimir[x_recorre][7])

                elif x_ctrl_nivel_i == a_imprimir[x_recorre][0] \
                        and x_ctrl_nivel_ii == a_imprimir[x_recorre][1]\
                        and x_ctrl_nivel_gc == a_imprimir[x_recorre][2]\
                        and x_ctrl_nivel_c != a_imprimir[x_recorre][3]\
                        and a_imprimir[x_recorre][3] != '':
                    x_suma_nivel_d = 0
                    x_suma_nivel_c = 0
                    if a_imprimir[x_recorre][7] == '':
                        x_suma_nivel_gc += 0
                    else:
                        x_suma_nivel_gc += float(a_imprimir[x_recorre][7])

                elif x_ctrl_nivel_i == a_imprimir[x_recorre][0] \
                        and x_ctrl_nivel_ii == a_imprimir[x_recorre][1]\
                        and x_ctrl_nivel_gc == a_imprimir[x_recorre][2]\
                        and x_ctrl_nivel_c != a_imprimir[x_recorre][3]\
                        and a_imprimir[x_recorre][3] == '':
                    x_suma_nivel_d = 0
                    x_suma_nivel_c = 0
                    if a_imprimir[x_recorre][7] == '':
                        x_suma_nivel_gc += 0
                    else:
                        x_suma_nivel_gc += float(a_imprimir[x_recorre][7])

                elif x_ctrl_nivel_i == a_imprimir[x_recorre][0] \
                        and x_ctrl_nivel_ii == a_imprimir[x_recorre][1]\
                        and x_ctrl_nivel_gc != a_imprimir[x_recorre][2]:
                    x_suma_nivel_d = 0
                    x_suma_nivel_c = 0
                    x_suma_nivel_gc = 0
                else:
                    x_suma_nivel_d = 0
                    x_suma_nivel_c = 0
                    x_suma_nivel_gc = 0
                x_ctrl_nivel_i = a_imprimir[x_recorre][0]
                x_ctrl_nivel_ii = a_imprimir[x_recorre][1]
                x_ctrl_nivel_gc = a_imprimir[x_recorre][2]
                x_ctrl_nivel_c = a_imprimir[x_recorre][3]
                x_ctrl_nivel_d = a_imprimir[x_recorre][10]
                x_recorre += 1
            certifica = str(self.certificacion)
            text1 = '______________________' \
                    '\n' + self.representante + \
                    '\nRepresentante Legal'
            text2 = '______________________' \
                    '\n' + self.contador + \
                    '\nContador'

            options1 = {
                'width': 205,
                'height': 100,
                'x_offset': 0,
                'y_offset': 0,

                'font': {'color': 'black',
                         'font': 'Arial',
                         'size': 10,
                         'bold': True,
                         },
                'align': {'vertical': 'bottom',
                          'horizontal': 'center'
                          },

            }
            options2 = {
                'width': 205,
                'height': 100,
                'x_offset': 0,
                'y_offset': 0,

                'font': {'color': 'black',
                         'font': 'Arial',
                         'size': 10,
                         'bold': True,
                         },
                'align': {'vertical': 'bottom',
                          'horizontal': 'center'
                          },

            }
            cert_options = {
                'width': 615,
                'height': 100,
                'x_offset': 0,
                'y_offset': 0,

                'font': {'color': 'black',
                         'font': 'Arial',
                         'size': 10,
                         'bold': True,
                         },
                'align': {'vertical': 'top',
                          'horizontal': 'left'
                          },

            }
            cell = xl_rowcol_to_cell(x_rows + 2, 0)
            worksheet.insert_textbox(cell, certifica, cert_options)
            cell = xl_rowcol_to_cell(x_rows + 7, 0)
            worksheet.insert_textbox(cell, text1, options1)
            cell = xl_rowcol_to_cell(x_rows + 7, 3)
            worksheet.insert_textbox(cell, text2, options2)
        workbook.close()
        self.write({
            'state': 'get',
            'data': base64.b64encode(open(xls_path, 'rb').read()),
            'name': xls_filename
        })
        return {
            'name': 'Libro de Inventario',
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new'
        }
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: