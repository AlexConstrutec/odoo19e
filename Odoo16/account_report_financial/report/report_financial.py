# -*- coding: utf-8 -*-
##############################################################################
#
# Copyright 2023 SIESA
#
##############################################################################
import calendar

import pytz
import time
from operator import itemgetter
from itertools import groupby
from odoo import models, fields, api
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT, float_round
from datetime import datetime, date


class account_report_financial(models.AbstractModel):
    _name = 'report.account_report_financial.report_financial'
    _description = "Reporte Libro Diario"

    def get_libro_diario_papertura(self, record):
        anio = record.anio
        mes_de = record.mes_de
        mes_a = record.mes_a
        company_id = record.company_id.id
        SecuenciasBank = self.env['account.journal'].search([('type', '=', 'bank')]).mapped('code')

        # Construir la condición dinámica para excluir esos códigos, solo si hay valores en SecuenciasBank
        if SecuenciasBank:
            exclusion_bancos = " AND ".join([f"am.name NOT LIKE '{code}%'" for code in SecuenciasBank])
        else:
            exclusion_bancos = ""  # Si no hay diarios "bank", no agregamos ninguna condición
        fecha_inicio = date(anio, int(mes_de), 1)
        ultimo_dia_mes_a = calendar.monthrange(anio, int(mes_a))[1]
        fecha_fin = date(anio, int(mes_a), ultimo_dia_mes_a)

        # Búsqueda de los asientos que cumplen con todos los criterios
        NoIncluirAsientos = self.env['account.move'].search([
            ('date', '>=', fecha_inicio),
            ('date', '<=', fecha_fin),
        ]).filtered(lambda move: (
                len(move.line_ids) == 2 and
                len(set(move.line_ids.mapped('account_id'))) == 1 and
                sum(move.line_ids.mapped('debit')) == sum(move.line_ids.mapped('credit'))
        ))
        query = '''
                            select 
		                        distinct
		                        Consulta.Fecha Fecha,
		                        Consulta.Partida Partida,
		                        Consulta.Codigo Codigo,
		                        Consulta.Cuenta Cuenta,
		                        Consulta.Debe,
		                        Consulta.Haber,
		                        Consulta.Empresa,
		                        Consulta.Nit
	                        from
		                        (
			                        select 
				                        am.date Fecha,
				                        -- am.x_name_partida Partida,
				                        am.partida_contable Partida,
				                        aa.code Codigo,
				                        aa."name" Cuenta,
				                        sum(aml.debit) Debe,
	 			                        sum(aml.credit) Haber,
				                        cc."name" Empresa,
				                        rp.vat Nit
			                        from account_move_line aml
			                        inner join account_move am on am.id = aml.move_id and am.id not in (''' + ','.join(map(str, NoIncluirAsientos.ids if NoIncluirAsientos else [0])) + ''')
			                        inner join account_account aa on aa.id = aml.account_id		
			                        left join res_company cc on aml.company_id = cc.id
			                        inner join res_partner rp on rp.id = cc.partner_id
			                        inner join account_journal aj on aj.id = am.journal_id
			                        where
			                        
			                            -- am.name not like 'BNK%' and am.name not like 'BAM%' and
				                        -- aml.debit>0 ''' + (f"AND {exclusion_bancos} " if exclusion_bancos else "") + ''' AND
				                        aj.name = 'Partida de Apertura'and
				                        -- (aml.move_name like '%Partida de Apertura%' or aml.move_name like '%APERT%') and
				                        am.company_id = '''+str(company_id)+''' and
 				                        am.state like 'posted' and
				 		                am.date between 
 										to_date(
 														concat(
 																		
 																		'01 ',
 																		Case
 																			when '''+str(mes_de)+''' =1 then 'Jan'
 																			when '''+str(mes_de)+''' =2 then 'Feb'
 																			when '''+str(mes_de)+''' =3 then 'Mar'
 																			when '''+str(mes_de)+''' =4 then 'Apr'
 																			when '''+str(mes_de)+''' =5 then 'May'
 																			when '''+str(mes_de)+''' =6 then 'Jun'
 																			when '''+str(mes_de)+''' =7 then 'Jul'
 																			when '''+str(mes_de)+''' =8 then 'Aug'
 																			when '''+str(mes_de)+''' =9 then 'Sep'
 																			when '''+str(mes_de)+''' =10 then 'Oct'
 																			when '''+str(mes_de)+''' =11 then 'Nov'
 																			else 'Dec' end,
 																		' ',
 																		'''+str(anio)+'''
 																	),
 														'DD Mon YYYY'
 													) 
 								        and 
 									        to_date(
 													concat(
 																	extract(
 																					day from(
 																										date_trunc(
 																															'month', 
 																															to_date(
 																																			concat(
 																																							'01 ',
 																																							Case
 																																								when '''+str(mes_a)+''' =1 then 'Jan'
 																																								when '''+str(mes_a)+''' =2 then 'Feb'
 																																								when '''+str(mes_a)+''' =3 then 'Mar'
 																																								when '''+str(mes_a)+''' =4 then 'Apr'
 																																								when '''+str(mes_a)+''' =5 then 'May'
 																																								when '''+str(mes_a)+''' =6 then 'Jun'
 																																								when '''+str(mes_a)+''' =7 then 'Jul'
 																																								when '''+str(mes_a)+''' =8 then 'Aug'
 																																								when '''+str(mes_a)+''' =9 then 'Sep'
 																																								when '''+str(mes_a)+''' =10 then 'Oct'
 																																								when '''+str(mes_a)+''' =11 then 'Nov'
 																																								else 'Dec' end,
 																																							' ',
 																																							'''+str(anio)+'''
 																																						),
 																																			'DD Mon YYYY'
 																																		)
 																															) + interval '1 month - 1 day'
 																			 						)
 														  						 ),
 																	' ',
 																	Case
 																			when '''+str(mes_a)+''' =1 then 'Jan'
 																			when '''+str(mes_a)+''' =2 then 'Feb'
 																			when '''+str(mes_a)+''' =3 then 'Mar'
 																			when '''+str(mes_a)+''' =4 then 'Apr'
 																			when '''+str(mes_a)+''' =5 then 'May'
 																			when '''+str(mes_a)+''' =6 then 'Jun'
 																			when '''+str(mes_a)+''' =7 then 'Jul'
 																			when '''+str(mes_a)+''' =8 then 'Aug'
 																			when '''+str(mes_a)+''' =9 then 'Sep'
 																			when '''+str(mes_a)+''' =10 then 'Oct'
 																			when '''+str(mes_a)+''' =11 then 'Nov'
 																			else 'Dec' end,
 																	' ',
 																	'''+str(anio)+'''
 															),
 												'DD Mon YYYY'
 											)
			group by
				am.date,
				-- am.x_name_partida,
				am.partida_contable,
				aa.code,
				aa."name",
				cc."name",
				rp.vat
 			
			union all
			select 
				am.date Fecha,
				-- am.x_name_partida Partida,
				am.partida_contable Partida,
				aa.code Codigo,
				aa."name" Cuenta,
				sum(aml.debit) Debe,
	 			sum(aml.credit) Haber,
				cc."name" Empresa,
				rp.vat Nit
			from account_move_line aml
			inner join account_move am on am.id = aml.move_id and am.id not in (''' + ','.join(map(str, NoIncluirAsientos.ids if NoIncluirAsientos else [0])) + ''')
			inner join account_account aa on aa.id = aml.account_id		
			left join res_company cc on aml.company_id = cc.id
			inner join res_partner rp on rp.id = cc.partner_id
			inner join account_journal aj on aj.id = am.journal_id
			where
			
			    -- am.name not like 'BNK%' and am.name not like 'BAM%' and
				-- aml.credit>0 ''' + (f"AND {exclusion_bancos} " if exclusion_bancos else "") + ''' AND
				aj.name = 'Partida de Apertura' and
				-- (aml.move_name like '%Partida de Apertura%' or aml.move_name like '%APERT%') and
				am.company_id =  '''+str(company_id)+''' and
 				am.state like 'posted' and
				
 				 		am.date between 
 										to_date(
 														concat(
 																		
 																		'01 ',
 																		Case
 																			when '''+str(mes_de)+''' =1 then 'Jan'
 																			when '''+str(mes_de)+''' =2 then 'Feb'
 																			when '''+str(mes_de)+''' =3 then 'Mar'
 																			when '''+str(mes_de)+''' =4 then 'Apr'
 																			when '''+str(mes_de)+''' =5 then 'May'
 																			when '''+str(mes_de)+''' =6 then 'Jun'
 																			when '''+str(mes_de)+''' =7 then 'Jul'
 																			when '''+str(mes_de)+''' =8 then 'Aug'
 																			when '''+str(mes_de)+''' =9 then 'Sep'
 																			when '''+str(mes_de)+''' =10 then 'Oct'
 																			when '''+str(mes_de)+''' =11 then 'Nov'
 																			else 'Dec' end,
 																		' ',
 																		'''+str(anio)+'''
 																	),
 														'DD Mon YYYY'
 													) 
 								and 
 									to_date(
 													concat(
 																	extract(
 																					day from(
 																										date_trunc(
 																															'month', 
 																															to_date(
 																																			concat(
 																																							'01 ',
 																																							Case
 																																								when '''+str(mes_a)+''' =1 then 'Jan'
 																																								when '''+str(mes_a)+''' =2 then 'Feb'
 																																								when '''+str(mes_a)+''' =3 then 'Mar'
 																																								when '''+str(mes_a)+''' =4 then 'Apr'
 																																								when '''+str(mes_a)+''' =5 then 'May'
 																																								when '''+str(mes_a)+''' =6 then 'Jun'
 																																								when '''+str(mes_a)+''' =7 then 'Jul'
 																																								when '''+str(mes_a)+''' =8 then 'Aug'
 																																								when '''+str(mes_a)+''' =9 then 'Sep'
 																																								when '''+str(mes_a)+''' =10 then 'Oct'
 																																								when '''+str(mes_a)+''' =11 then 'Nov'
 																																								else 'Dec' end,
 																																							' ',
 																																							'''+str(anio)+'''
 																																						),
 																																			'DD Mon YYYY'
 																																		)
 																															) + interval '1 month - 1 day'
 																			 						)
 														  						 ),
 																	' ',
 																	Case
 																			when '''+str(mes_a)+''' =1 then 'Jan'
 																			when '''+str(mes_a)+''' =2 then 'Feb'
 																			when '''+str(mes_a)+''' =3 then 'Mar'
 																			when '''+str(mes_a)+''' =4 then 'Apr'
 																			when '''+str(mes_a)+''' =5 then 'May'
 																			when '''+str(mes_a)+''' =6 then 'Jun'
 																			when '''+str(mes_a)+''' =7 then 'Jul'
 																			when '''+str(mes_a)+''' =8 then 'Aug'
 																			when '''+str(mes_a)+''' =9 then 'Sep'
 																			when '''+str(mes_a)+''' =10 then 'Oct'
 																			when '''+str(mes_a)+''' =11 then 'Nov'
 																			else 'Dec' end,
 																	' ',
 																	'''+str(anio)+'''
 															),
 												'DD Mon YYYY'
 											)
			group by
				am.date,
				-- am.x_name_partida,
				am.partida_contable,
				aa.code,
				aa."name",
				cc."name",
				rp.vat
 			
	) as Consulta
	order by 
	Consulta.Fecha,
	Consulta.Haber,
	Consulta.Codigo
	asc '''

        self._cr.execute(query, False)
        values = self._cr.dictfetchall()
        return values
    def get_libro_diario_cierre(self, record):
        SecuenciasBank = self.env['account.journal'].search([('type', '=', 'bank')]).mapped('code')

        # Construir la condición dinámica para excluir esos códigos, solo si hay valores en SecuenciasBank
        if SecuenciasBank:
            exclusion_bancos = " AND ".join([f"am.name NOT LIKE '{code}%'" for code in SecuenciasBank])
        else:
            exclusion_bancos = ""  # Si no hay diarios "bank", no agregamos ninguna condición

        anio = record.anio
        mes_de = record.mes_de
        mes_a = record.mes_a
        company_id = record.company_id.id
        fecha_inicio = date(anio, int(mes_de), 1)
        ultimo_dia_mes_a = calendar.monthrange(anio, int(mes_a))[1]
        fecha_fin = date(anio, int(mes_a), ultimo_dia_mes_a)

        # Búsqueda de los asientos que cumplen con todos los criterios
        NoIncluirAsientos = self.env['account.move'].search([
            ('date', '>=', fecha_inicio),
            ('date', '<=', fecha_fin),
        ]).filtered(lambda move: (
                len(move.line_ids) == 2 and
                len(set(move.line_ids.mapped('account_id'))) == 1 and
                sum(move.line_ids.mapped('debit')) == sum(move.line_ids.mapped('credit'))
        ))
        no_incluir_ids = NoIncluirAsientos.ids
        if no_incluir_ids:
            filtro_sql = f"am.id NOT IN ({', '.join(map(str, no_incluir_ids))})"
        else:
            filtro_sql = "1=1"  # No hay IDs que excluir, así que no se filtra nada
        query = '''
                            select 
		                        distinct
		                        Consulta.Fecha Fecha,
		                        Consulta.Partida Partida,
		                        Consulta.Codigo Codigo,
		                        Consulta.Cuenta Cuenta,
		                        Consulta.Debe,
		                        Consulta.Haber,
		                        Consulta.Empresa,
		                        Consulta.Nit
	                        from
		                        (
			                        select 
				                        am.date Fecha,
				                        -- am.x_name_partida Partida,
				                        am.partida_contable Partida,
				                        aa.code Codigo,
				                        aa."name" Cuenta,
				                        sum(aml.debit) Debe,
	 			                        sum(aml.credit) Haber,
				                        cc."name" Empresa,
				                        rp.vat Nit
			                        from account_move_line aml
			                        inner join account_move am on am.id = aml.move_id AND ''' + filtro_sql + '''
			                        inner join account_account aa on aa.id = aml.account_id		
			                        left join res_company cc on aml.company_id = cc.id
			                        inner join res_partner rp on rp.id = cc.partner_id
			                        inner join account_journal aj on aj.id = am.journal_id
			                        where
			                        
			                            -- am.name not like 'BNK%' and am.name not like 'BAM%' and
				                        -- aml.debit>0 ''' + (f"AND {exclusion_bancos} " if exclusion_bancos else "") + ''' AND
				                        aj.name = 'Partida de Cierre' and
				                        --(aml.move_name like '%CIERR%' or aml.move_name like '%Partida de Cierre%') and
				                        am.company_id = '''+str(company_id)+''' and
 				                        am.state like 'posted' and
				 		                am.date between 
 										to_date(
 														concat(
 																		
 																		'01 ',
 																		Case
 																			when '''+str(mes_de)+''' =1 then 'Jan'
 																			when '''+str(mes_de)+''' =2 then 'Feb'
 																			when '''+str(mes_de)+''' =3 then 'Mar'
 																			when '''+str(mes_de)+''' =4 then 'Apr'
 																			when '''+str(mes_de)+''' =5 then 'May'
 																			when '''+str(mes_de)+''' =6 then 'Jun'
 																			when '''+str(mes_de)+''' =7 then 'Jul'
 																			when '''+str(mes_de)+''' =8 then 'Aug'
 																			when '''+str(mes_de)+''' =9 then 'Sep'
 																			when '''+str(mes_de)+''' =10 then 'Oct'
 																			when '''+str(mes_de)+''' =11 then 'Nov'
 																			else 'Dec' end,
 																		' ',
 																		'''+str(anio)+'''
 																	),
 														'DD Mon YYYY'
 													) 
 								        and 
 									        to_date(
 													concat(
 																	extract(
 																					day from(
 																										date_trunc(
 																															'month', 
 																															to_date(
 																																			concat(
 																																							'01 ',
 																																							Case
 																																								when '''+str(mes_a)+''' =1 then 'Jan'
 																																								when '''+str(mes_a)+''' =2 then 'Feb'
 																																								when '''+str(mes_a)+''' =3 then 'Mar'
 																																								when '''+str(mes_a)+''' =4 then 'Apr'
 																																								when '''+str(mes_a)+''' =5 then 'May'
 																																								when '''+str(mes_a)+''' =6 then 'Jun'
 																																								when '''+str(mes_a)+''' =7 then 'Jul'
 																																								when '''+str(mes_a)+''' =8 then 'Aug'
 																																								when '''+str(mes_a)+''' =9 then 'Sep'
 																																								when '''+str(mes_a)+''' =10 then 'Oct'
 																																								when '''+str(mes_a)+''' =11 then 'Nov'
 																																								else 'Dec' end,
 																																							' ',
 																																							'''+str(anio)+'''
 																																						),
 																																			'DD Mon YYYY'
 																																		)
 																															) + interval '1 month - 1 day'
 																			 						)
 														  						 ),
 																	' ',
 																	Case
 																			when '''+str(mes_a)+''' =1 then 'Jan'
 																			when '''+str(mes_a)+''' =2 then 'Feb'
 																			when '''+str(mes_a)+''' =3 then 'Mar'
 																			when '''+str(mes_a)+''' =4 then 'Apr'
 																			when '''+str(mes_a)+''' =5 then 'May'
 																			when '''+str(mes_a)+''' =6 then 'Jun'
 																			when '''+str(mes_a)+''' =7 then 'Jul'
 																			when '''+str(mes_a)+''' =8 then 'Aug'
 																			when '''+str(mes_a)+''' =9 then 'Sep'
 																			when '''+str(mes_a)+''' =10 then 'Oct'
 																			when '''+str(mes_a)+''' =11 then 'Nov'
 																			else 'Dec' end,
 																	' ',
 																	'''+str(anio)+'''
 															),
 												'DD Mon YYYY'
 											)
			group by
				am.date,
				-- am.x_name_partida,
				am.partida_contable,
				aa.code,
				aa."name",
				cc."name",
				rp.vat
 			
			union all
			select 
				am.date Fecha,
				-- am.x_name_partida Partida,
				am.partida_contable Partida,
				aa.code Codigo,
				aa."name" Cuenta,
				sum(aml.debit) Debe,
	 			sum(aml.credit) Haber,
				cc."name" Empresa,
				rp.vat Nit
			from account_move_line aml
			inner join account_move am on am.id = aml.move_id AND ''' + filtro_sql + '''
			inner join account_account aa on aa.id = aml.account_id		
			left join res_company cc on aml.company_id = cc.id
			inner join res_partner rp on rp.id = cc.partner_id
			inner join account_journal aj on aj.id = am.journal_id
			where
			    
			    -- am.name not like 'BNK%' and am.name not like 'BAM%' and
				-- aml.credit>0 ''' + (f"AND {exclusion_bancos} " if exclusion_bancos else "") + ''' AND
                aj.name = 'Partida de Cierre' and
                -- (aml.move_name like '%CIERR%' or aml.move_name like '%Partida de Cierre%') and
				am.company_id =  '''+str(company_id)+''' and
 				am.state like 'posted' and
				
 				 		am.date between 
 										to_date(
 														concat(
 																		
 																		'01 ',
 																		Case
 																			when '''+str(mes_de)+''' =1 then 'Jan'
 																			when '''+str(mes_de)+''' =2 then 'Feb'
 																			when '''+str(mes_de)+''' =3 then 'Mar'
 																			when '''+str(mes_de)+''' =4 then 'Apr'
 																			when '''+str(mes_de)+''' =5 then 'May'
 																			when '''+str(mes_de)+''' =6 then 'Jun'
 																			when '''+str(mes_de)+''' =7 then 'Jul'
 																			when '''+str(mes_de)+''' =8 then 'Aug'
 																			when '''+str(mes_de)+''' =9 then 'Sep'
 																			when '''+str(mes_de)+''' =10 then 'Oct'
 																			when '''+str(mes_de)+''' =11 then 'Nov'
 																			else 'Dec' end,
 																		' ',
 																		'''+str(anio)+'''
 																	),
 														'DD Mon YYYY'
 													) 
 								and 
 									to_date(
 													concat(
 																	extract(
 																					day from(
 																										date_trunc(
 																															'month', 
 																															to_date(
 																																			concat(
 																																							'01 ',
 																																							Case
 																																								when '''+str(mes_a)+''' =1 then 'Jan'
 																																								when '''+str(mes_a)+''' =2 then 'Feb'
 																																								when '''+str(mes_a)+''' =3 then 'Mar'
 																																								when '''+str(mes_a)+''' =4 then 'Apr'
 																																								when '''+str(mes_a)+''' =5 then 'May'
 																																								when '''+str(mes_a)+''' =6 then 'Jun'
 																																								when '''+str(mes_a)+''' =7 then 'Jul'
 																																								when '''+str(mes_a)+''' =8 then 'Aug'
 																																								when '''+str(mes_a)+''' =9 then 'Sep'
 																																								when '''+str(mes_a)+''' =10 then 'Oct'
 																																								when '''+str(mes_a)+''' =11 then 'Nov'
 																																								else 'Dec' end,
 																																							' ',
 																																							'''+str(anio)+'''
 																																						),
 																																			'DD Mon YYYY'
 																																		)
 																															) + interval '1 month - 1 day'
 																			 						)
 														  						 ),
 																	' ',
 																	Case
 																			when '''+str(mes_a)+''' =1 then 'Jan'
 																			when '''+str(mes_a)+''' =2 then 'Feb'
 																			when '''+str(mes_a)+''' =3 then 'Mar'
 																			when '''+str(mes_a)+''' =4 then 'Apr'
 																			when '''+str(mes_a)+''' =5 then 'May'
 																			when '''+str(mes_a)+''' =6 then 'Jun'
 																			when '''+str(mes_a)+''' =7 then 'Jul'
 																			when '''+str(mes_a)+''' =8 then 'Aug'
 																			when '''+str(mes_a)+''' =9 then 'Sep'
 																			when '''+str(mes_a)+''' =10 then 'Oct'
 																			when '''+str(mes_a)+''' =11 then 'Nov'
 																			else 'Dec' end,
 																	' ',
 																	'''+str(anio)+'''
 															),
 												'DD Mon YYYY'
 											)
			group by
				am.date,
				-- am.x_name_partida,
				am.partida_contable,
				aa.code,
				aa."name",
				cc."name",
				rp.vat
 			
	) as Consulta
	order by 
	Consulta.Fecha,
	Consulta.Haber,
	Consulta.Codigo
	asc '''

        self._cr.execute(query, False)
        values = self._cr.dictfetchall()
        return values
    def get_libro_diario(self, record):
            anio = record.anio
            mes_de = record.mes_de
            mes_a = record.mes_a
            company_id = record.company_id.id
            SecuenciasBank = self.env['account.journal'].search([('type', '=', 'bank')]).mapped('code')

            # Construir la condición dinámica para excluir esos códigos, solo si hay valores en SecuenciasBank
            if SecuenciasBank:
                exclusion_bancos = " AND ".join([f"am.name NOT LIKE '{code}%'" for code in SecuenciasBank])
            else:
                exclusion_bancos = ""  # Si no hay diarios "bank", no agregamos ninguna condición

            fecha_inicio = date(anio, int(mes_de), 1)
            ultimo_dia_mes_a = calendar.monthrange(anio, int(mes_a))[1]
            fecha_fin = date(anio, int(mes_a), ultimo_dia_mes_a)

            # Búsqueda de los asientos que cumplen con todos los criterios
            NoIncluirAsientos = self.env['account.move'].search([
                ('date', '>=', fecha_inicio),
                ('date', '<=', fecha_fin),
            ]).filtered(lambda move: (
                    len(move.line_ids) == 2 and
                    len(set(move.line_ids.mapped('account_id'))) == 1 and
                    sum(move.line_ids.mapped('debit')) == sum(move.line_ids.mapped('credit'))
            ))
            no_incluir_ids = NoIncluirAsientos.ids
            if no_incluir_ids:
                filtro_sql = f"am.id NOT IN ({', '.join(map(str, no_incluir_ids))})"
            else:
                filtro_sql = "1=1"  # No hay IDs que excluir, así que no se filtra nada

            query = '''
                            select 
		                        distinct
		                        Consulta.Fecha Fecha,
		                        Consulta.Partida Partida,
		                        Consulta.Codigo Codigo,
		                        Consulta.Cuenta Cuenta,
		                        Consulta.Debe,
		                        Consulta.Haber,
		                        Consulta.Empresa,
		                        Consulta.Nit
	                        from
		                        (
			                        select 
				                        am.date Fecha,
				                        -- am.x_name_partida Partida,
				                        am.partida_contable Partida,
				                        aa.code Codigo,
				                        aa."name" Cuenta,
				                        sum(aml.debit) Debe,
	 			                        sum(aml.credit) Haber,
				                        cc."name" Empresa,
				                        rp.vat Nit
			                        from account_move_line aml
			                        inner join account_move am on am.id = aml.move_id AND ''' + filtro_sql + '''
			                        inner join account_account aa on aa.id = aml.account_id		
			                        left join res_company cc on aml.company_id = cc.id
			                        inner join res_partner rp on rp.id = cc.partner_id
			                        where
			                        
			                            -- am.name not like 'BNK%' and am.name not like 'BAM%' and
				                        -- aml.debit>0 ''' + (f"AND {exclusion_bancos} " if exclusion_bancos else "") + ''' AND
				                        am.company_id = '''+str(company_id)+''' and
 				                        am.state like 'posted' and
				 		                am.date between 
 										to_date(
 														concat(
 																		
 																		'01 ',
 																		Case
 																			when '''+str(mes_de)+''' =1 then 'Jan'
 																			when '''+str(mes_de)+''' =2 then 'Feb'
 																			when '''+str(mes_de)+''' =3 then 'Mar'
 																			when '''+str(mes_de)+''' =4 then 'Apr'
 																			when '''+str(mes_de)+''' =5 then 'May'
 																			when '''+str(mes_de)+''' =6 then 'Jun'
 																			when '''+str(mes_de)+''' =7 then 'Jul'
 																			when '''+str(mes_de)+''' =8 then 'Aug'
 																			when '''+str(mes_de)+''' =9 then 'Sep'
 																			when '''+str(mes_de)+''' =10 then 'Oct'
 																			when '''+str(mes_de)+''' =11 then 'Nov'
 																			else 'Dec' end,
 																		' ',
 																		'''+str(anio)+'''
 																	),
 														'DD Mon YYYY'
 													) 
 								        and 
 									        to_date(
 													concat(
 																	extract(
 																					day from(
 																										date_trunc(
 																															'month', 
 																															to_date(
 																																			concat(
 																																							'01 ',
 																																							Case
 																																								when '''+str(mes_a)+''' =1 then 'Jan'
 																																								when '''+str(mes_a)+''' =2 then 'Feb'
 																																								when '''+str(mes_a)+''' =3 then 'Mar'
 																																								when '''+str(mes_a)+''' =4 then 'Apr'
 																																								when '''+str(mes_a)+''' =5 then 'May'
 																																								when '''+str(mes_a)+''' =6 then 'Jun'
 																																								when '''+str(mes_a)+''' =7 then 'Jul'
 																																								when '''+str(mes_a)+''' =8 then 'Aug'
 																																								when '''+str(mes_a)+''' =9 then 'Sep'
 																																								when '''+str(mes_a)+''' =10 then 'Oct'
 																																								when '''+str(mes_a)+''' =11 then 'Nov'
 																																								else 'Dec' end,
 																																							' ',
 																																							'''+str(anio)+'''
 																																						),
 																																			'DD Mon YYYY'
 																																		)
 																															) + interval '1 month - 1 day'
 																			 						)
 														  						 ),
 																	' ',
 																	Case
 																			when '''+str(mes_a)+''' =1 then 'Jan'
 																			when '''+str(mes_a)+''' =2 then 'Feb'
 																			when '''+str(mes_a)+''' =3 then 'Mar'
 																			when '''+str(mes_a)+''' =4 then 'Apr'
 																			when '''+str(mes_a)+''' =5 then 'May'
 																			when '''+str(mes_a)+''' =6 then 'Jun'
 																			when '''+str(mes_a)+''' =7 then 'Jul'
 																			when '''+str(mes_a)+''' =8 then 'Aug'
 																			when '''+str(mes_a)+''' =9 then 'Sep'
 																			when '''+str(mes_a)+''' =10 then 'Oct'
 																			when '''+str(mes_a)+''' =11 then 'Nov'
 																			else 'Dec' end,
 																	' ',
 																	'''+str(anio)+'''
 															),
 												'DD Mon YYYY'
 											)
			group by
				am.date,
				-- am.x_name_partida,
				am.partida_contable,
				aa.code,
				aa."name",
				cc."name",
				rp.vat
 			
			union all
			select 
				am.date Fecha,
				-- am.x_name_partida Partida,
				am.partida_contable Partida,
				aa.code Codigo,
				aa."name" Cuenta,
				sum(aml.debit) Debe,
	 			sum(aml.credit) Haber,
				cc."name" Empresa,
				rp.vat Nit
			from account_move_line aml
			inner join account_move am on am.id = aml.move_id AND ''' + filtro_sql + '''
			inner join account_account aa on aa.id = aml.account_id		
			left join res_company cc on aml.company_id = cc.id
			inner join res_partner rp on rp.id = cc.partner_id
			where
			
			    -- am.name not like 'BNK%' and am.name not like 'BAM%' and
				-- aml.credit>0 ''' + (f"AND {exclusion_bancos} " if exclusion_bancos else "") + ''' AND
				am.company_id =  '''+str(company_id)+''' and
 				am.state like 'posted' and
				
 				 		am.date between 
 										to_date(
 														concat(
 																		
 																		'01 ',
 																		Case
 																			when '''+str(mes_de)+''' =1 then 'Jan'
 																			when '''+str(mes_de)+''' =2 then 'Feb'
 																			when '''+str(mes_de)+''' =3 then 'Mar'
 																			when '''+str(mes_de)+''' =4 then 'Apr'
 																			when '''+str(mes_de)+''' =5 then 'May'
 																			when '''+str(mes_de)+''' =6 then 'Jun'
 																			when '''+str(mes_de)+''' =7 then 'Jul'
 																			when '''+str(mes_de)+''' =8 then 'Aug'
 																			when '''+str(mes_de)+''' =9 then 'Sep'
 																			when '''+str(mes_de)+''' =10 then 'Oct'
 																			when '''+str(mes_de)+''' =11 then 'Nov'
 																			else 'Dec' end,
 																		' ',
 																		'''+str(anio)+'''
 																	),
 														'DD Mon YYYY'
 													) 
 								and 
 									to_date(
 													concat(
 																	extract(
 																					day from(
 																										date_trunc(
 																															'month', 
 																															to_date(
 																																			concat(
 																																							'01 ',
 																																							Case
 																																								when '''+str(mes_a)+''' =1 then 'Jan'
 																																								when '''+str(mes_a)+''' =2 then 'Feb'
 																																								when '''+str(mes_a)+''' =3 then 'Mar'
 																																								when '''+str(mes_a)+''' =4 then 'Apr'
 																																								when '''+str(mes_a)+''' =5 then 'May'
 																																								when '''+str(mes_a)+''' =6 then 'Jun'
 																																								when '''+str(mes_a)+''' =7 then 'Jul'
 																																								when '''+str(mes_a)+''' =8 then 'Aug'
 																																								when '''+str(mes_a)+''' =9 then 'Sep'
 																																								when '''+str(mes_a)+''' =10 then 'Oct'
 																																								when '''+str(mes_a)+''' =11 then 'Nov'
 																																								else 'Dec' end,
 																																							' ',
 																																							'''+str(anio)+'''
 																																						),
 																																			'DD Mon YYYY'
 																																		)
 																															) + interval '1 month - 1 day'
 																			 						)
 														  						 ),
 																	' ',
 																	Case
 																			when '''+str(mes_a)+''' =1 then 'Jan'
 																			when '''+str(mes_a)+''' =2 then 'Feb'
 																			when '''+str(mes_a)+''' =3 then 'Mar'
 																			when '''+str(mes_a)+''' =4 then 'Apr'
 																			when '''+str(mes_a)+''' =5 then 'May'
 																			when '''+str(mes_a)+''' =6 then 'Jun'
 																			when '''+str(mes_a)+''' =7 then 'Jul'
 																			when '''+str(mes_a)+''' =8 then 'Aug'
 																			when '''+str(mes_a)+''' =9 then 'Sep'
 																			when '''+str(mes_a)+''' =10 then 'Oct'
 																			when '''+str(mes_a)+''' =11 then 'Nov'
 																			else 'Dec' end,
 																	' ',
 																	'''+str(anio)+'''
 															),
 												'DD Mon YYYY'
 											)
			group by
				am.date,
				-- am.x_name_partida,
				am.partida_contable,
				aa.code,
				aa."name",
				cc."name",
				rp.vat
 			
	) as Consulta
	order by 
	Consulta.Fecha,
	Consulta.Haber,
	Consulta.Codigo
	asc
                            '''
            self._cr.execute(query, False)
            values = self._cr.dictfetchall()
            return values
    def get_libro_diario_dif(self, record):
            anio = record.anio
            mes_de = record.mes_de
            mes_a = record.mes_a
            company_id = record.company_id.id
            SecuenciasBank = self.env['account.journal'].search([('type', '=', 'bank')]).mapped('code')

            # Construir la condición dinámica para excluir esos códigos, solo si hay valores en SecuenciasBank
            if SecuenciasBank:
                exclusion_bancos = " AND ".join([f"am.name NOT LIKE '{code}%'" for code in SecuenciasBank])
            else:
                exclusion_bancos = ""  # Si no hay diarios "bank", no agregamos ninguna condición

            fecha_inicio = date(anio, int(mes_de), 1)
            ultimo_dia_mes_a = calendar.monthrange(anio, int(mes_a))[1]
            fecha_fin = date(anio, int(mes_a), ultimo_dia_mes_a)

            # Búsqueda de los asientos que cumplen con todos los criterios
            NoIncluirAsientos = self.env['account.move'].search([
                ('date', '>=', fecha_inicio),
                ('date', '<=', fecha_fin),
            ]).filtered(lambda move: (
                    len(move.line_ids) == 2 and
                    len(set(move.line_ids.mapped('account_id'))) == 1 and
                    sum(move.line_ids.mapped('debit')) == sum(move.line_ids.mapped('credit'))
            ))
            no_incluir_ids = NoIncluirAsientos.ids
            if no_incluir_ids:
                filtro_sql = f"am.id NOT IN ({', '.join(map(str, no_incluir_ids))})"
            else:
                filtro_sql = "1=1"  # No hay IDs que excluir, así que no se filtra nada

            query = '''
                            select 
		                        distinct
		                        Consulta.Fecha Fecha,
		                        Consulta.Partida Partida,
		                        Consulta.Codigo Codigo,
		                        Consulta.Cuenta Cuenta,
		                        Consulta.Debe,
		                        Consulta.Haber,
		                        Consulta.Empresa,
		                        Consulta.Nit
	                        from
		                        (
			                        select 
				                        am.date Fecha,
				                        -- am.x_name_partida Partida,
				                        am.partida_contable Partida,
				                        aa.code Codigo,
				                        aa."name" Cuenta,
				                        sum(aml.debit) Debe,
	 			                        sum(aml.credit) Haber,
				                        cc."name" Empresa,
				                        rp.vat Nit
			                        from account_move_line aml
			                        inner join account_move am on am.id = aml.move_id AND ''' + filtro_sql + '''
			                        inner join account_account aa on aa.id = aml.account_id		
			                        left join res_company cc on aml.company_id = cc.id
			                        inner join res_partner rp on rp.id = cc.partner_id
			                        inner join account_journal aj on aj.id = am.journal_id
			                        where
			                        
			                            -- am.name not like 'BNK%' and am.name not like 'BAM%' and
				                        -- aml.debit>0 ''' + (f"AND {exclusion_bancos} " if exclusion_bancos else "") + ''' AND
				                        aj.name not in ('Partida de Apertura', 'Partida de Cierre') and
				                        -- (aml.move_name not like '%Partida de Apertura%' or aml.move_name not like '%APERT%' ) and
				                        -- (aml.move_name not like '%Partida de Cierre%' or aml.move_name not like '%CIERR%'  ) and
				                        am.company_id = '''+str(company_id)+''' and
 				                        am.state like 'posted' and
				 		                am.date between 
 										to_date(
 														concat(
 																		
 																		'01 ',
 																		Case
 																			when '''+str(mes_de)+''' =1 then 'Jan'
 																			when '''+str(mes_de)+''' =2 then 'Feb'
 																			when '''+str(mes_de)+''' =3 then 'Mar'
 																			when '''+str(mes_de)+''' =4 then 'Apr'
 																			when '''+str(mes_de)+''' =5 then 'May'
 																			when '''+str(mes_de)+''' =6 then 'Jun'
 																			when '''+str(mes_de)+''' =7 then 'Jul'
 																			when '''+str(mes_de)+''' =8 then 'Aug'
 																			when '''+str(mes_de)+''' =9 then 'Sep'
 																			when '''+str(mes_de)+''' =10 then 'Oct'
 																			when '''+str(mes_de)+''' =11 then 'Nov'
 																			else 'Dec' end,
 																		' ',
 																		'''+str(anio)+'''
 																	),
 														'DD Mon YYYY'
 													) 
 								        and 
 									        to_date(
 													concat(
 																	extract(
 																					day from(
 																										date_trunc(
 																															'month', 
 																															to_date(
 																																			concat(
 																																							'01 ',
 																																							Case
 																																								when '''+str(mes_a)+''' =1 then 'Jan'
 																																								when '''+str(mes_a)+''' =2 then 'Feb'
 																																								when '''+str(mes_a)+''' =3 then 'Mar'
 																																								when '''+str(mes_a)+''' =4 then 'Apr'
 																																								when '''+str(mes_a)+''' =5 then 'May'
 																																								when '''+str(mes_a)+''' =6 then 'Jun'
 																																								when '''+str(mes_a)+''' =7 then 'Jul'
 																																								when '''+str(mes_a)+''' =8 then 'Aug'
 																																								when '''+str(mes_a)+''' =9 then 'Sep'
 																																								when '''+str(mes_a)+''' =10 then 'Oct'
 																																								when '''+str(mes_a)+''' =11 then 'Nov'
 																																								else 'Dec' end,
 																																							' ',
 																																							'''+str(anio)+'''
 																																						),
 																																			'DD Mon YYYY'
 																																		)
 																															) + interval '1 month - 1 day'
 																			 						)
 														  						 ),
 																	' ',
 																	Case
 																			when '''+str(mes_a)+''' =1 then 'Jan'
 																			when '''+str(mes_a)+''' =2 then 'Feb'
 																			when '''+str(mes_a)+''' =3 then 'Mar'
 																			when '''+str(mes_a)+''' =4 then 'Apr'
 																			when '''+str(mes_a)+''' =5 then 'May'
 																			when '''+str(mes_a)+''' =6 then 'Jun'
 																			when '''+str(mes_a)+''' =7 then 'Jul'
 																			when '''+str(mes_a)+''' =8 then 'Aug'
 																			when '''+str(mes_a)+''' =9 then 'Sep'
 																			when '''+str(mes_a)+''' =10 then 'Oct'
 																			when '''+str(mes_a)+''' =11 then 'Nov'
 																			else 'Dec' end,
 																	' ',
 																	'''+str(anio)+'''
 															),
 												'DD Mon YYYY'
 											)
			group by
				am.date,
				-- am.x_name_partida,
				am.partida_contable,
				aa.code,
				aa."name",
				cc."name",
				rp.vat
 			
			union all
			select 
				am.date Fecha,
				-- am.x_name_partida Partida,
				am.partida_contable Partida,
				aa.code Codigo,
				aa."name" Cuenta,
				sum(aml.debit) Debe,
	 			sum(aml.credit) Haber,
				cc."name" Empresa,
				rp.vat Nit
			from account_move_line aml
			inner join account_move am on am.id = aml.move_id AND ''' + filtro_sql + '''
			inner join account_account aa on aa.id = aml.account_id		
			left join res_company cc on aml.company_id = cc.id
			inner join res_partner rp on rp.id = cc.partner_id
			inner join account_journal aj on aj.id = am.journal_id
			where
			
			    -- am.name not like 'BNK%' and am.name not like 'BAM%' and
				-- aml.credit>0 ''' + (f"AND {exclusion_bancos} " if exclusion_bancos else "") + ''' AND
                aj.name not in ('Partida de Apertura', 'Partida de Cierre') and
                -- (aml.move_name not like '%Partida de Apertura%' or aml.move_name not like '%APERT%' ) and
                -- (aml.move_name not like '%Partida de Cierre%' or aml.move_name not like '%CIERR%'  ) and
				am.company_id =  '''+str(company_id)+''' and
 				am.state like 'posted' and
				
 				 		am.date between 
 										to_date(
 														concat(
 																		
 																		'01 ',
 																		Case
 																			when '''+str(mes_de)+''' =1 then 'Jan'
 																			when '''+str(mes_de)+''' =2 then 'Feb'
 																			when '''+str(mes_de)+''' =3 then 'Mar'
 																			when '''+str(mes_de)+''' =4 then 'Apr'
 																			when '''+str(mes_de)+''' =5 then 'May'
 																			when '''+str(mes_de)+''' =6 then 'Jun'
 																			when '''+str(mes_de)+''' =7 then 'Jul'
 																			when '''+str(mes_de)+''' =8 then 'Aug'
 																			when '''+str(mes_de)+''' =9 then 'Sep'
 																			when '''+str(mes_de)+''' =10 then 'Oct'
 																			when '''+str(mes_de)+''' =11 then 'Nov'
 																			else 'Dec' end,
 																		' ',
 																		'''+str(anio)+'''
 																	),
 														'DD Mon YYYY'
 													) 
 								and 
 									to_date(
 													concat(
 																	extract(
 																					day from(
 																										date_trunc(
 																															'month', 
 																															to_date(
 																																			concat(
 																																							'01 ',
 																																							Case
 																																								when '''+str(mes_a)+''' =1 then 'Jan'
 																																								when '''+str(mes_a)+''' =2 then 'Feb'
 																																								when '''+str(mes_a)+''' =3 then 'Mar'
 																																								when '''+str(mes_a)+''' =4 then 'Apr'
 																																								when '''+str(mes_a)+''' =5 then 'May'
 																																								when '''+str(mes_a)+''' =6 then 'Jun'
 																																								when '''+str(mes_a)+''' =7 then 'Jul'
 																																								when '''+str(mes_a)+''' =8 then 'Aug'
 																																								when '''+str(mes_a)+''' =9 then 'Sep'
 																																								when '''+str(mes_a)+''' =10 then 'Oct'
 																																								when '''+str(mes_a)+''' =11 then 'Nov'
 																																								else 'Dec' end,
 																																							' ',
 																																							'''+str(anio)+'''
 																																						),
 																																			'DD Mon YYYY'
 																																		)
 																															) + interval '1 month - 1 day'
 																			 						)
 														  						 ),
 																	' ',
 																	Case
 																			when '''+str(mes_a)+''' =1 then 'Jan'
 																			when '''+str(mes_a)+''' =2 then 'Feb'
 																			when '''+str(mes_a)+''' =3 then 'Mar'
 																			when '''+str(mes_a)+''' =4 then 'Apr'
 																			when '''+str(mes_a)+''' =5 then 'May'
 																			when '''+str(mes_a)+''' =6 then 'Jun'
 																			when '''+str(mes_a)+''' =7 then 'Jul'
 																			when '''+str(mes_a)+''' =8 then 'Aug'
 																			when '''+str(mes_a)+''' =9 then 'Sep'
 																			when '''+str(mes_a)+''' =10 then 'Oct'
 																			when '''+str(mes_a)+''' =11 then 'Nov'
 																			else 'Dec' end,
 																	' ',
 																	'''+str(anio)+'''
 															),
 												'DD Mon YYYY'
 											)
			group by
				am.date,
				-- am.x_name_partida,
				am.partida_contable,
				aa.code,
				aa."name",
				cc."name",
				rp.vat
 			
	) as Consulta
	order by 
	Consulta.Fecha,
	Consulta.Haber,
	Consulta.Codigo
	asc
                            '''
            self._cr.execute(query, False)
            values = self._cr.dictfetchall()
            return values

    def get_libro_mayor(self, record):
        anio = record.anio
        mes_de = record.mes_de
        mes_a = record.mes_a
        company_id = record.company_id.id
        SecuenciasBank = self.env['account.journal'].search([('type', '=', 'bank')]).mapped('code')
        fecha_inicio = date(anio, int(mes_de), 1)
        ultimo_dia_mes_a = calendar.monthrange(anio, int(mes_a))[1]
        fecha_fin = date(anio, int(mes_a), ultimo_dia_mes_a)

        # Búsqueda de los asientos que cumplen con todos los criterios
        NoIncluirAsientos = self.env['account.move'].search([
            ('date', '>=', fecha_inicio),
            ('date', '<=', fecha_fin),
        ]).filtered(lambda move: (
                len(move.line_ids) == 2 and
                len(set(move.line_ids.mapped('account_id'))) == 1 and
                sum(move.line_ids.mapped('debit')) == sum(move.line_ids.mapped('credit'))
        ))
        no_incluir_ids = NoIncluirAsientos.ids
        if no_incluir_ids:
            filtro_sql = f"am.id NOT IN ({', '.join(map(str, no_incluir_ids))})"
        else:
            filtro_sql = "1=1"  # No hay IDs que excluir, así que no se filtra nada

        # Construir la condición dinámica para excluir esos códigos, solo si hay valores en SecuenciasBank
        if SecuenciasBank:
            exclusion_bancos = " AND ".join([f"am.name NOT LIKE '{code}%'" for code in SecuenciasBank])
        else:
            exclusion_bancos = ""  # Si no hay diarios "bank", no agregamos ninguna condición

        self._cr.execute('''
select 
		QueryTotal.partidadebe,
		to_char(QueryTotal.fechadebe, 'DD-MM-YYYY') fechadebe,
		QueryTotal.idcuentadebe,
		QueryTotal.codigodebe,
		QueryTotal.cuentadebe,
		QueryTotal.saldodebe,
		QueryTotal.debe,
		QueryTotal.partidahaber,
		to_char(QueryTotal.fechahaber, 'DD-MM-YYYY') fechaHaber,
		QueryTotal.idcuentahaber,
		QueryTotal.codigohaber,
		QueryTotal.cuentahaber,
		QueryTotal.saldohaber,
		QueryTotal.haber,
		QueryTotal.idempresa,
		QueryTotal.empresa,
		QueryTotal.nit
from ( 
select 
		coalesce(Debe.partida,Haber.Partida)                                             partidadebe,
		-- coalesce(to_char(Debe.fecha, 'YYYY-MM-DD'),  to_char(Haber.fecha, 'YYYY-MM-DD')) fechadebe,
		coalesce(Debe.fecha,  Haber.fecha) fechadebe,
		Debe.idcuenta                                                                    idcuentadebe,
		coalesce(Debe.codigo, Haber.codigo)                                              codigodebe,
		coalesce(Debe.cuenta, Haber.cuenta)                                              cuentadebe,
		Saldo.saldodebe                                                                  saldodebe,
		coalesce(Debe.debe,0)                                                            debe,
		coalesce(Haber.partida,Debe.partida)                                             partidahaber,
		-- coalesce(to_char(Haber.fecha,'YYYY-MM-DD'),  to_char(Debe.fecha,'YYYY-MM-DD'))   fechahaber,
		coalesce(Haber.fecha,  Debe.fecha)   fechahaber,
		Haber.idcuenta                                                                   idcuentahaber,
		coalesce(Haber.codigo, Debe.codigo)                                              codigohaber,
		coalesce(Haber.cuenta, Debe.cuenta)                                              cuentahaber,
		Saldo.saldohaber                                                                 saldohaber,
		coalesce(Haber.haber, 0)                                                         haber,
		coalesce(Debe.idempresa, Haber.idempresa)                                        idempresa,
		coalesce(Debe.empresa, Haber.empresa)                                            empresa,
		coalesce(Debe.nit,Haber.nit)                                                     nit
	from
		(
			select 
				am.date Fecha,
				-- am.x_name_partida Partida,
				am.partida_contable Partida,
				aa.id IdCuenta,
				aa.code Codigo,
				aa."name" Cuenta,
				sum(aml.debit) Debe,
	 			sum(aml.credit) Haber,
				sum(aml.balance) balance,
				cc.id IdEmpresa,
				cc."name" Empresa,
				rp.vat Nit
			from account_move_line aml
			inner join account_move am on am.id = aml.move_id AND ''' + filtro_sql + '''
			inner join account_account aa on aa.id = aml.account_id		
			left join res_company cc on aml.company_id = cc.id
			inner join res_partner rp on rp.id = cc.partner_id
			where
			
			    -- am.name not like 'BNK%' and am.name not like 'BAM%' and
			    Case
 				    when '''+str(mes_de)+''' =1 then am.journal_id != 41
 				else
             		am.journal_id is not null
 				end and 
 				-- ''' + (f"AND {exclusion_bancos} " if exclusion_bancos else "") + ''' AND
				am.company_id = ''' + str(company_id) + '''  and
 				am.state like 'posted' and
				
 				 		am.date between 
 										to_date(
 														concat(
 																		
 																		'01 ',
 																		Case
 																			when ''' + str(mes_de) + ''' =1 then 'Jan'
 																			when ''' + str(mes_de) + ''' =2 then 'Feb'
 																			when ''' + str(mes_de) + ''' =3 then 'Mar'
 																			when ''' + str(mes_de) + ''' =4 then 'Apr'
 																			when ''' + str(mes_de) + ''' =5 then 'May'
 																			when ''' + str(mes_de) + ''' =6 then 'Jun'
 																			when ''' + str(mes_de) + ''' =7 then 'Jul'
 																			when ''' + str(mes_de) + ''' =8 then 'Aug'
 																			when ''' + str(mes_de) + ''' =9 then 'Sep'
 																			when ''' + str(mes_de) + ''' =10 then 'Oct'
 																			when ''' + str(mes_de) + ''' =11 then 'Nov'
 																			else 'Dec' end,
 																		' ',
 																		''' + str(anio) + '''
 																	),
 														'DD Mon YYYY'
 													) 
 								and 
 									to_date(
 													concat(
 																	extract(
 																					day from(
 																										date_trunc(
 																															'month', 
 																															to_date(
 																																			concat(
 																																							'01 ',
 																																							Case
 																																								when ''' + str(mes_a) + ''' =1 then 'Jan'
 																																								when ''' + str(mes_a) + ''' =2 then 'Feb'
 																																								when ''' + str(mes_a) + ''' =3 then 'Mar'
 																																								when ''' + str(mes_a) + ''' =4 then 'Apr'
 																																								when ''' + str(mes_a) + ''' =5 then 'May'
 																																								when ''' + str(mes_a) + ''' =6 then 'Jun'
 																																								when ''' + str(mes_a) + ''' =7 then 'Jul'
 																																								when ''' + str(mes_a) + ''' =8 then 'Aug'
 																																								when ''' + str(mes_a) + ''' =9 then 'Sep'
 																																								when ''' + str(mes_a) + ''' =10 then 'Oct'
 																																								when ''' + str(mes_a) + ''' =11 then 'Nov'
 																																								else 'Dec' end,
 																																							' ',
 																																							''' + str(anio) + '''
 																																						),
 																																			'DD Mon YYYY'
 																																		)
 																															) + interval '1 month - 1 day'
 																			 						)
 														  						 ),
 																	' ',
 																	Case
 																			when ''' + str(mes_a) + ''' =1 then 'Jan'
 																			when ''' + str(mes_a) + ''' =2 then 'Feb'
 																			when ''' + str(mes_a) + ''' =3 then 'Mar'
 																			when ''' + str(mes_a) + ''' =4 then 'Apr'
 																			when ''' + str(mes_a) + ''' =5 then 'May'
 																			when ''' + str(mes_a) + ''' =6 then 'Jun'
 																			when ''' + str(mes_a) + ''' =7 then 'Jul'
 																			when ''' + str(mes_a) + ''' =8 then 'Aug'
 																			when ''' + str(mes_a) + ''' =9 then 'Sep'
 																			when ''' + str(mes_a) + ''' =10 then 'Oct'
 																			when ''' + str(mes_a) + ''' =11 then 'Nov'
 																			else 'Dec' end,
 																	' ',
 																	''' + str(anio) + '''
 															),
 												'DD Mon YYYY'
 											)
			group by
				am.date,
				-- am.x_name_partida,
				am.partida_contable,
				aa.id,
				aa.code,
				aa."name",
				cc.id,
				cc."name",
				rp.vat
			having sum(debit) > 0 
			order by 
				aa.code,
				am.date,
				am.partida_contable,
				sum(debit) asc
			) as Debe
			full outer join 
			(
				select 
				am.date Fecha,
				-- am.x_name_partida Partida,
				am.partida_contable Partida,
				aa.id IdCuenta,
				aa.code Codigo,
				aa."name" Cuenta,
				sum(aml.debit) Debe,
	 			sum(aml.credit) Haber,
				sum(aml.balance) balance,
				cc.id IdEmpresa,
				cc."name" Empresa,
				rp.vat Nit
			from account_move_line aml
			inner join account_move am on am.id = aml.move_id and ''' + filtro_sql + '''
			inner join account_account aa on aa.id = aml.account_id		
			left join res_company cc on aml.company_id = cc.id
			inner join res_partner rp on rp.id = cc.partner_id
			where

			    -- am.name not like 'BNK%' and am.name not like 'BAM%' and
			    Case
 				    when '''+str(mes_de)+''' =1 then am.journal_id != 41
 				else
             		am.journal_id is not null
 				end and 
 				-- ''' + (f"AND {exclusion_bancos} " if exclusion_bancos else "") + ''' AND
				am.company_id = ''' + str(company_id) + '''  and
 				am.state like 'posted' and
				
 				 		am.date between 
 										to_date(
 														concat(
 																		
 																		'01 ',
 																		Case
 																			when ''' + str(mes_de) + ''' =1 then 'Jan'
 																			when ''' + str(mes_de) + ''' =2 then 'Feb'
 																			when ''' + str(mes_de) + ''' =3 then 'Mar'
 																			when ''' + str(mes_de) + ''' =4 then 'Apr'
 																			when ''' + str(mes_de) + ''' =5 then 'May'
 																			when ''' + str(mes_de) + ''' =6 then 'Jun'
 																			when ''' + str(mes_de) + ''' =7 then 'Jul'
 																			when ''' + str(mes_de) + ''' =8 then 'Aug'
 																			when ''' + str(mes_de) + ''' =9 then 'Sep'
 																			when ''' + str(mes_de) + ''' =10 then 'Oct'
 																			when ''' + str(mes_de) + ''' =11 then 'Nov'
 																			else 'Dec' end,
 																		' ',
 																		''' + str(anio) + '''
 																	),
 														'DD Mon YYYY'
 													) 
 								and 
 									to_date(
 													concat(
 																	extract(
 																					day from(
 																										date_trunc(
 																															'month', 
 																															to_date(
 																																			concat(
 																																							'01 ',
 																																							Case
 																																								when ''' + str(mes_a) + ''' =1 then 'Jan'
 																																								when ''' + str(mes_a) + ''' =2 then 'Feb'
 																																								when ''' + str(mes_a) + ''' =3 then 'Mar'
 																																								when ''' + str(mes_a) + ''' =4 then 'Apr'
 																																								when ''' + str(mes_a) + ''' =5 then 'May'
 																																								when ''' + str(mes_a) + ''' =6 then 'Jun'
 																																								when ''' + str(mes_a) + ''' =7 then 'Jul'
 																																								when ''' + str(mes_a) + ''' =8 then 'Aug'
 																																								when ''' + str(mes_a) + ''' =9 then 'Sep'
 																																								when ''' + str(mes_a) + ''' =10 then 'Oct'
 																																								when ''' + str(mes_a) + ''' =11 then 'Nov'
 																																								else 'Dec' end,
 																																							' ',
 																																							''' + str(anio) + '''
 																																						),
 																																			'DD Mon YYYY'
 																																		)
 																															) + interval '1 month - 1 day'
 																			 						)
 														  						 ),
 																	' ',
 																	Case
 																			when ''' + str(mes_a) + ''' =1 then 'Jan'
 																			when ''' + str(mes_a) + ''' =2 then 'Feb'
 																			when ''' + str(mes_a) + ''' =3 then 'Mar'
 																			when ''' + str(mes_a) + ''' =4 then 'Apr'
 																			when ''' + str(mes_a) + ''' =5 then 'May'
 																			when ''' + str(mes_a) + ''' =6 then 'Jun'
 																			when ''' + str(mes_a) + ''' =7 then 'Jul'
 																			when ''' + str(mes_a) + ''' =8 then 'Aug'
 																			when ''' + str(mes_a) + ''' =9 then 'Sep'
 																			when ''' + str(mes_a) + ''' =10 then 'Oct'
 																			when ''' + str(mes_a) + ''' =11 then 'Nov'
 																			else 'Dec' end,
 																	' ',
 																	''' + str(anio) + '''
 															),
 												'DD Mon YYYY'
 											)
			group by
				am.date,
				-- am.x_name_partida,
				am.partida_contable,
				aa.id,
				aa.code,
				aa."name",
				cc.id,
				cc."name",
				rp.vat
			having sum(credit) > 0
			order by 
				aa.code,
				am.date,
				am.partida_contable,
				sum(credit) asc
			) as Haber 
			on Debe.codigo = Haber.codigo 
			and Debe.cuenta = Haber.Cuenta 
			and Debe.fecha = Haber.fecha 
			and Debe.idempresa = Haber.idempresa
			left join 
				 (
					 select 
					 	aa.id idcuenta,
					 	coalesce(Fin_SaldoCuentaDebe(aa.id,
							to_date(
 														concat(
 																		
 																		'01 ',
 																		Case
 																			when ''' + str(mes_de) + ''' =1 then 'Jan'
 																			when ''' + str(mes_de) + ''' =2 then 'Feb'
 																			when ''' + str(mes_de) + ''' =3 then 'Mar'
 																			when ''' + str(mes_de) + ''' =4 then 'Apr'
 																			when ''' + str(mes_de) + ''' =5 then 'May'
 																			when ''' + str(mes_de) + ''' =6 then 'Jun'
 																			when ''' + str(mes_de) + ''' =7 then 'Jul'
 																			when ''' + str(mes_de) + ''' =8 then 'Aug'
 																			when ''' + str(mes_de) + ''' =9 then 'Sep'
 																			when ''' + str(mes_de) + ''' =10 then 'Oct'
 																			when ''' + str(mes_de) + ''' =11 then 'Nov'
 																			else 'Dec' end,
 																		' ',
 																		''' + str(anio) + '''
 																	),
 														'DD Mon YYYY'
 													)
							,aa.company_id),0) SaldoDebe,
						coalesce(Fin_SaldoCuentaHaber(aa.id,
							to_date(
 														concat(
 																		
 																		'01 ',
 																		Case
 																			when ''' + str(mes_de) + ''' =1 then 'Jan'
 																			when ''' + str(mes_de) + ''' =2 then 'Feb'
 																			when ''' + str(mes_de) + ''' =3 then 'Mar'
 																			when ''' + str(mes_de) + ''' =4 then 'Apr'
 																			when ''' + str(mes_de) + ''' =5 then 'May'
 																			when ''' + str(mes_de) + ''' =6 then 'Jun'
 																			when ''' + str(mes_de) + ''' =7 then 'Jul'
 																			when ''' + str(mes_de) + ''' =8 then 'Aug'
 																			when ''' + str(mes_de) + ''' =9 then 'Sep'
 																			when ''' + str(mes_de) + ''' =10 then 'Oct'
 																			when ''' + str(mes_de) + ''' =11 then 'Nov'
 																			else 'Dec' end,
 																		' ',
 																		''' + str(anio) + '''
 																	),
 														'DD Mon YYYY'
 													)
							,aa.company_id),0) SaldoHaber
					 from account_account aa
					 where aa.company_id = ''' + str(company_id) + '''
					 order by aa.code asc
				 ) as Saldo on Saldo.idcuenta = Debe.idcuenta or Saldo.idcuenta = Haber.idcuenta ) as QueryTotal order by QueryTotal.codigodebe asc, QueryTotal.fechadebe asc, QueryTotal.fechahaber asc ''', False)
        values = self._cr.dictfetchall()
        return values

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
