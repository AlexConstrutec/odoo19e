# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Costo del empleado por mes, día y hora (2026-11-17, F3).

Se calcula en Enterprise (donde están el sueldo y la planilla) y se trae a Community con el pull de
empleados; allí nunca se calcula, solo se conserva lo que llega. Los tres campos y los parámetros
son del grupo "Costos de personal": ni siquiera un Jefe de equipo los puede leer."""
from odoo import api, fields, models

GRUPO_COSTOS = 'construtec_account_payment_order_19.group_costos_personal'


class ResCompany(models.Model):
    _inherit = 'res.company'

    costo_patronal_pct = fields.Float(
        string='Cargas patronales (%)', default=12.67, groups=GRUPO_COSTOS,
        help='IGSS patronal 10.67 % + IRTRA 1 % + INTECAP 1 %, sobre el sueldo base (`wage`).')
    costo_provisiones_pct = fields.Float(
        string='Provisiones (%)', default=29.16, groups=GRUPO_COSTOS,
        help='Aguinaldo 8.33 % + Bono 14 8.33 % + Indemnización 8.33 % + Vacaciones 4.17 %, sobre el '
             'sueldo base (`wage`).')
    costo_dias_mes = fields.Float(
        string='Días hábiles por mes', default=22.0, groups=GRUPO_COSTOS,
        help='Divisor del costo mensual para obtener el costo por día.')
    costo_horas_dia = fields.Float(
        string='Horas por día', default=8.0, groups=GRUPO_COSTOS,
        help='Divisor del costo por día para obtener el costo por hora.')


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    costo_mensual = fields.Monetary(
        string='Costo mensual', currency_field='currency_id', compute='_compute_costo_personal',
        store=True, readonly=False, groups=GRUPO_COSTOS,
        help='Sueldo base + bonificación + cargas patronales + provisiones, por mes.')
    costo_dia = fields.Monetary(
        string='Costo por día', currency_field='currency_id', compute='_compute_costo_personal',
        store=True, readonly=False, groups=GRUPO_COSTOS,
        help='Costo mensual entre los días hábiles por mes de la compañía.')
    costo_hora = fields.Monetary(
        string='Costo por hora', currency_field='currency_id', compute='_compute_costo_personal',
        store=True, readonly=False, groups=GRUPO_COSTOS,
        help='Costo por día entre las horas por día de la compañía.')

    def _costo_bonificacion(self):
        """Bonificaciones que suman al costo mensual. Gancho: en Enterprise lo amplía
        `construtec_hr_employee_19` (bonificación incentivo)."""
        self.ensure_one()
        return 0.0

    @api.depends('wage', 'company_id.costo_patronal_pct', 'company_id.costo_provisiones_pct',
                 'company_id.costo_dias_mes', 'company_id.costo_horas_dia',
                 'company_id.payment_order_role')
    def _compute_costo_personal(self):
        for emp in self:
            company = emp.company_id.sudo()
            if company.payment_order_role == 'solicitante':
                # Community: lo escribe el pull de empleados; aquí nunca se calcula.
                emp.costo_mensual = emp.costo_mensual
                emp.costo_dia = emp.costo_dia
                emp.costo_hora = emp.costo_hora
                continue
            sueldo = emp.sudo().wage or 0.0
            mensual = (sueldo + emp._costo_bonificacion()
                       + sueldo * (company.costo_patronal_pct or 0.0) / 100.0
                       + sueldo * (company.costo_provisiones_pct or 0.0) / 100.0)
            dias = company.costo_dias_mes or 22.0
            horas = company.costo_horas_dia or 8.0
            emp.costo_mensual = mensual
            emp.costo_dia = mensual / dias
            emp.costo_hora = mensual / dias / horas
