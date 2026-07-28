#from idlelib.mainmenu import menudefs

from odoo import models, fields
from datetime import datetime, timedelta  # Esto es necesario si necesitas trabajar con objetos datetime


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    x_promedio_salario_str = fields.Char(string='Salario Promedio s', readonly=True, compute='_compute_promedios')
    x_igss_promedio_str = fields.Char(string='IGSS Promedio s', readonly=True)
    x_salario_base_promedio_str = fields.Char(string='Salario base Promedio s', readonly=True)
    x_bonificacion_incentivo_promedio_str = fields.Char(string='Bonif Incentivo Promedio s', readonly=True)
    x_horas_extras_promedio_str = fields.Char(string='Horas Extras Promedio s', readonly=True)
    x_isr_promedio_str = fields.Char(string='ISR Promedio s', readonly=True)
    x_total_deducciones_promedio_str = fields.Char(string='Total Deducciones Promedio s', readonly=True)
    x_total_devengado_promedio_str = fields.Char(string='Total Devengado Promedio s', readonly=True)

    def _compute_promedios(self):
        for record in self:
            currentMonth = datetime.now()
            thDividendo = 0
            thDividendoIgss = 0
            # Nuevos Promedios
            thDividendoBase = 0
            thDividendoBonIncentivo = 0
            thDividendoBonFij = 0
            thDividendoOtrasBonif = 0
            thDividendoHorasExtras = 0
            thDividendoIsr = 0
            thDividendoTotalDeduccion = 0
            thDividendoPromLiqMensual = 0

            thAuxDividendo = 0
            thAuxDividendoIgss = 0
            # Nuevos promedios
            thAuxDividendoBase = 0
            thAuxDividendoBonIncentivo = 0
            thAuxDividendoBonFij = 0
            thAuxDividendoOtrasBonif = 0
            thAuxDividendoHorasExtras = 0
            thAuxDividendoIsr = 0
            thAuxDividendoTotalDeduccion = 0
            thAuxDividendoPromLiqMensual = 0

            thDivisor = 0
            thDivisorIgss = 0
            # Nuevos promedios
            thDivisorBase = 0
            thDivisorBonIncentivo = 0
            thDivisorBonFij = 0
            thDivisorOtrasBonif = 0
            thDivisorHorasExtras = 0
            thDivisorIsr = 0
            thDivisorTotalDeduccion = 0
            thDivisorPromLiqMensual = 0

            thCount = self.env['hr.payslip'].search_count(
                [('employee_id', '=', self.id), ('date_from', '>=', currentMonth - timedelta(days=105)),
                 ('struct_id', '!=', False),
                 ('payslip_run_id', 'not like', '%PRESTACIONES%'),
                    ('payslip_run_id', 'not like', '%AGUINALDO%'), ('payslip_run_id', 'not like', '%COMPLEMENTO%'),
                    ('state', '=', 'done')])
            thAuxMes = 0
            thMes = 0
            thAnio = 0
            thItera = 0
            if (thCount > 0):
                employee_salary = self.env['hr.payslip'].search(
                    [('employee_id', '=', self.id), ('date_from', '>=', currentMonth - timedelta(days=120)),
                     ('struct_id', '!=', False),
                     ('payslip_run_id', 'not like', '%PRESTACIONES%'),
                     ('payslip_run_id', 'not like', '%AGUINALDO%'), ('payslip_run_id', 'not like', '%COMPLEMENTO%'),
                     ('state', '=', 'done')], order="date_from asc")
                thMesCompleto = 0  # Esta variable es para tomar en cuenta nominas de mes completo ejemplo 2 quincenas 1 al 15 y 16 al 30
                thAuxMes = currentMonth.month - 1
                if (thAuxMes == 0):  # Enero
                    thAnio = currentMonth.year - 1
                    thMes = 10
                if (thAuxMes == 1):  # Febrero
                    thAnio = currentMonth.year - 1
                    thMes = 11
                if (thAuxMes == 2):  # Marzo
                    thAnio = currentMonth.year - 1
                    thMes = 12
                if (thAuxMes > 2 and thAuxMes <= 12):  # Abril en adelante
                    thAnio = currentMonth.year
                    thMes = thAuxMes
                    thMes = thMes - 2
                while thItera < 3:
                    for reco in employee_salary:
                        # ----------------------------------- Mes actual: Enero Meses involucrados: Octubre, Noviembre, Diciembre ------------------------------------------------
                        if ((reco.date_from.month == thMes and reco.date_from.year == thAnio) and (
                                reco.date_to.month == thMes and reco.date_to.year == thAnio)):
                            # Calculo de ausencias
                            thAusencias = []
                            for worked_day in reco.worked_days_line_ids:
                                if worked_day.work_entry_type_id.is_leave:
                                    thAusencias.append(worked_day)
                            # Contar las ausencias
                            thCountAusencias = sum([worked_day.number_of_days for worked_day in thAusencias])
                            if thCountAusencias <= 12:
                                # Calculo de quincenas
                                if (reco.date_from.day == 1 and reco.date_to.day >= 28):
                                    thMesCompleto = 2
                                if (reco.date_from.day == 1 and reco.date_to.day == 15):
                                    thMesCompleto = 1
                                if (reco.date_from.day == 16 and reco.date_to.day >= 28 and thMesCompleto == 1):
                                    thMesCompleto = 2
                                # Asignacion de dividendo y divisor para promediar
                                thMonto = 0
                                thIgss = 0
                                # Nuevos promedios
                                thBase = 0
                                thBonIncentivo = 0
                                thBonFij = 0
                                thOtrasBonif = 0
                                thHorasExtras = 0
                                thIsr = 0
                                thTotalDeduccion = 0
                                thPromLiqMensual = 0
                                for line in reco.line_ids:
                                    if line.code == 'GROSS':
                                        thMonto += line.total
                                if thMonto > 0:
                                    for line in reco.line_ids:
                                        if line.code == 'IGSSLABR':
                                            thIgss += line.total
                                        if line.code == 'BASIC':
                                            thBase += line.total
                                        if line.code == 'BONIN':
                                            thBonIncentivo += line.total
                                        if line.code == 'BOFIJ':
                                            thBonFij += line.total
                                        if line.code in ['MDOA', 'MDOAS', 'BONPRO', 'MDOP', 'BHE', 'OTREN',
                                                         'MDOALIM']:
                                            thOtrasBonif += line.total
                                        if line.code == 'VHEB':
                                            thHorasExtras += line.total
                                        if line.code == 'ISRASA':
                                            thIsr += line.total
                                        if line.code == 'NET':
                                            thPromLiqMensual += line.total
                                    thTotalDeduccion = thIsr + thIgss
                                    # Quincena
                                    if (thMesCompleto == 1 and (reco.date_from.day == 1 and reco.date_to.day == 15)):
                                        thAuxDividendo = thMonto
                                        thAuxDividendoIgss = thIgss
                                        # Nuevos promedios
                                        thAuxDividendoBase = thBase
                                        thAuxDividendoBonIncentivo = thBonIncentivo
                                        thAuxDividendoBonFij = thBonFij
                                        thAuxDividendoOtrasBonif = thOtrasBonif
                                        thAuxDividendoHorasExtras = thHorasExtras
                                        thAuxDividendoIsr = thIsr
                                        thAuxDividendoTotalDeduccion = thTotalDeduccion
                                        thAuxDividendoPromLiqMensual = thPromLiqMensual

                                    # Quincena 2
                                    if (thMesCompleto == 2 and (reco.date_from.day == 16 and reco.date_to.day >= 30)):
                                        thDividendo += thMonto + thAuxDividendo
                                        thDividendoIgss += thIgss + thAuxDividendoIgss
                                        # Nuevos promedios
                                        thDividendoBase += thBase + thAuxDividendoBase
                                        thDividendoBonIncentivo += thBonIncentivo + thAuxDividendoBonIncentivo
                                        thDividendoBonFij += thBonFij + thAuxDividendoBonFij
                                        thDividendoOtrasBonif += thOtrasBonif + thAuxDividendoOtrasBonif
                                        thDividendoHorasExtras += thHorasExtras + thAuxDividendoHorasExtras
                                        thDividendoIsr += thIsr + thAuxDividendoIsr
                                        thDividendoTotalDeduccion += thTotalDeduccion + thAuxDividendoTotalDeduccion
                                        thDividendoPromLiqMensual += thPromLiqMensual + thAuxDividendoPromLiqMensual

                                        thAuxDividendo = 0
                                        thAuxDividendoIgss = 0
                                        # Nuevos promedios
                                        thAuxDividendoBase = 0
                                        thAuxDividendoBonIncentivo = 0
                                        thAuxDividendoBonFij = 0
                                        thAuxDividendoOtrasBonif = 0
                                        thAuxDividendoHorasExtras = 0
                                        thAuxDividendoIsr = 0
                                        thAuxDividendoTotalDeduccion = 0
                                        thAuxDividendoPromLiqMensual = 0

                                        thDivisor += 1
                                        thDivisorIgss += 1
                                        # Nuevos promedios
                                        thDivisorBase += 1
                                        thDivisorBonIncentivo += 1
                                        thDivisorBonFij += 1
                                        thDivisorOtrasBonif += 1
                                        thDivisorHorasExtras += 1
                                        thDivisorIsr += 1
                                        thDivisorTotalDeduccion += 1
                                        thDivisorPromLiqMensual += 1

                                        thMesCompleto = 0
                                    # Mes completo
                                    if (thMesCompleto == 2 and (reco.date_from.day == 1 and reco.date_to.day >= 30)):
                                        thDividendo += thMonto
                                        thDividendoIgss += thIgss
                                        # Nuevo promedio
                                        thDividendoBase += thBase
                                        thDividendoBonIncentivo += thBonIncentivo
                                        thDividendoBonFij += thBonFij
                                        thDividendoOtrasBonif += thOtrasBonif
                                        thDividendoHorasExtras += thHorasExtras
                                        thDividendoIsr += thIsr
                                        thDividendoTotalDeduccion += thTotalDeduccion
                                        thDividendoPromLiqMensual += thPromLiqMensual

                                        thDivisor += 1
                                        thDivisorIgss += 1
                                        # Nuevo promedio
                                        thDivisorBase += 1
                                        thDivisorBonIncentivo += 1
                                        thDivisorBonFij += 1
                                        thDivisorOtrasBonif += 1
                                        thDivisorHorasExtras += 1
                                        thDivisorIsr += 1
                                        thDivisorTotalDeduccion += 1
                                        thDivisorPromLiqMensual += 1

                                        thMesCompleto = 0
                            else:
                                thMesCompleto = 0
                    if ((thMes > 0 and thMes <= 12) and thAnio == currentMonth.year):
                        thMes += 1
                    if (thMes == 12 and thAnio == currentMonth.year - 1):
                        thMes = 1
                        thAnio = currentMonth.year
                    if (thMes == 11 and thAnio == currentMonth.year - 1):
                        thMes = 12
                    if (thMes == 10 and thAnio == currentMonth.year - 1):
                        thMes = 11
                    thItera += 1
                    # Ultima comprobacion para no dividir entre ceros
            if (thDividendo > 0 and thDivisor > 0):
                record.x_promedio_salario_str = '{:,.2f}'.format(
                    (thDividendoBase / thDivisorBase) +
                    (thDividendoBonIncentivo / thDivisorBonIncentivo) +
                    (thDividendoBonFij / thDivisorBonFij) +
                    (thDividendoOtrasBonif / thDivisorOtrasBonif) +
                    (thDividendoHorasExtras / thDivisorHorasExtras))
                record.x_igss_promedio_str = '{:,.2f}'.format((thDividendoIgss / thDivisorIgss))
                record.x_salario_base_promedio_str = '{:,.2f}'.format((thDividendoBase / thDivisorBase))
                record.x_bonificacion_incentivo_promedio_str = '{:,.2f}'.format(
                    (thDividendoBonIncentivo / thDivisorBonIncentivo) +
                    (thDividendoBonFij / thDivisorBonFij) +
                    (thDividendoOtrasBonif / thDivisorOtrasBonif))
                record.x_horas_extras_promedio_str = '{:,.2f}'.format((thDividendoHorasExtras / thDivisorHorasExtras))
                record.x_isr_promedio_str = '{:,.2f}'.format((thDividendoIsr / thDivisorIsr))
                record.x_total_deducciones_promedio_str = '{:,.2f}'.format(
                    (thDividendoIgss / thDivisorIgss) + (thDividendoIsr / thDivisorIsr))
                record.x_total_devengado_promedio_str = '{:,.2f}'.format(
                    ((thDividendoBase / thDivisorBase) +
                     (thDividendoBonIncentivo / thDivisorBonIncentivo) +
                     (thDividendoBonFij / thDivisorBonFij) +
                     (thDividendoOtrasBonif / thDivisorOtrasBonif) +
                     (thDividendoHorasExtras / thDivisorHorasExtras)
                     ) -
                    ((thDividendoIgss / thDivisorIgss) +
                     (thDividendoIsr / thDivisorIsr)))
            else:
                record.x_promedio_salario_str = format(0.00000, ".2f")
                record.x_igss_promedio_str = format(0.00000, ".2f")
                record.x_salario_base_promedio_str = format(0.00000, ".2f")
                record.x_bonificacion_incentivo_promedio_str = format(0.00000, ".2f")
                record.x_horas_extras_promedio_str = format(0.00000, ".2f")
                record.x_isr_promedio_str = format(0.00000, ".2f")
                record.x_total_deducciones_promedio_str = format(0.00000, ".2f")
                record.x_total_devengado_promedio_str = format(0.00000, ".2f")

    def get_current_date(self):
        mes = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
               9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"}
        today = fields.Date.today()
        dia = today.day
        mes = mes[today.month]
        anio = today.year
        formatted_date = f"{dia} de {mes} del {anio}"
        return formatted_date

    def get_fecha_constancia_laboral(self):
        dia = self.first_contract_date.day if self.first_contract_date else ""
        mes = self.first_contract_date.month if self.first_contract_date else ""
        anio = self.first_contract_date.year if self.first_contract_date else ""
        format = f"{dia}/{mes}/{anio}"
        mensaje = "el " + format if format else ""
        return mensaje

    def get_fecha_constancia_laboral_no_vigente(self):
        dia = self.first_contract_date.day if self.first_contract_date else ""
        mes = self.first_contract_date.month if self.first_contract_date else ""
        anio = self.first_contract_date.year if self.first_contract_date else ""
        format = f"{dia}/{mes}/{anio}"
        mensaje = "el " + format if format else ""
        return mensaje

    def get_format_date_contrat_end(self):
        if self.departure_date:
            dia = self.departure_date.day
            mes = self.departure_date.month
            anio = self.departure_date.year
            format = f"{dia}/{mes}/{anio}"
            mensaje = "al " + format if format else ""
            return mensaje
        else:
            today = fields.Date.today()
            dia = today.day
            mes = today.month
            anio = today.year
            formatted_date = f"{dia}/{mes}/{anio}"
            mensaje = "al " + formatted_date if formatted_date else ""
            return mensaje

    def getSalario(self):
        salario = 0
        bonificacion_incentivo = 0
        bono_fijo = 0
        bonificacion_product = 0
        total = 0
        for record in self:
            salario = record.contract_id.wage if record.contract_id else 0
            bonificacion_incentivo = record.contract_id.bonificacion_incentivo if record.contract_id else 0
            bono_fijo = record.contract_id.bonificacion_fija if record.contract_id else 0
            bonificacion_product = record.contract_id.bonificacion_productividad if record.contract_id else 0
            total = salario + bonificacion_incentivo + bono_fijo + bonificacion_product
            break
        return round(total, 2)

    def getIGSS(self):
        # igss = self.slip_ids[0].line_ids.filtered(lambda x: x.code == 'IGSSLABR').total if self.slip_ids else 0
        igss = 0
        for record in self:
            igss = record.contract_id.wage * 0.0483 if record.contract_id else 0
            break
        return round(igss, 2)