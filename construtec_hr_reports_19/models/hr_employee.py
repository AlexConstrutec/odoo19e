from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

from odoo import fields, models

MESES = {
    1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril', 5: 'Mayo', 6: 'Junio',
    7: 'Julio', 8: 'Agosto', 9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre',
}

BUCKET_BY_CODE = {
    'BASIC': 'base',
    'BONIN': 'bon_incentivo',
    'BOFIJ': 'bon_fija',
    'MDOA': 'otras_bonif',
    'MDOAS': 'otras_bonif',
    'BONPRO': 'otras_bonif',
    'MDOP': 'otras_bonif',
    'BHE': 'otras_bonif',
    'OTREN': 'otras_bonif',
    'MDOALIM': 'otras_bonif',
    'VHEB': 'horas_extras',
    'IGSSLABR': 'igss',
    'ISRASA': 'isr',
}
BUCKET_KEYS = ('base', 'bon_incentivo', 'bon_fija', 'otras_bonif', 'horas_extras', 'igss', 'isr')
PROMEDIO_FIELDS = (
    'x_promedio_salario_str', 'x_igss_promedio_str', 'x_salario_base_promedio_str',
    'x_bonificacion_incentivo_promedio_str', 'x_horas_extras_promedio_str', 'x_isr_promedio_str',
    'x_total_deducciones_promedio_str', 'x_total_devengado_promedio_str',
)


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    x_promedio_salario_str = fields.Char(string='Salario Promedio', readonly=True, compute='_compute_promedios')
    x_igss_promedio_str = fields.Char(string='IGSS Promedio', readonly=True, compute='_compute_promedios')
    x_salario_base_promedio_str = fields.Char(
        string='Salario Base Promedio', readonly=True, compute='_compute_promedios')
    x_bonificacion_incentivo_promedio_str = fields.Char(
        string='Bonif. Incentivo Promedio', readonly=True, compute='_compute_promedios')
    x_horas_extras_promedio_str = fields.Char(
        string='Horas Extras Promedio', readonly=True, compute='_compute_promedios')
    x_isr_promedio_str = fields.Char(string='ISR Promedio', readonly=True, compute='_compute_promedios')
    x_total_deducciones_promedio_str = fields.Char(
        string='Total Deducciones Promedio', readonly=True, compute='_compute_promedios')
    x_total_devengado_promedio_str = fields.Char(
        string='Total Devengado Promedio', readonly=True, compute='_compute_promedios')

    def _compute_promedios(self):
        """Promedio de los últimos 3 meses completos (excluye nóminas de prestaciones/aguinaldo/complemento).

        Reconstruye "meses completos" combinando dos nóminas quincenales consecutivas (1-15 y 16-fin) o
        tomando directamente una nómina que ya cubre el mes completo (1-fin).
        """
        for employee in self:
            today = datetime.now()
            payslips = self.env['hr.payslip'].search([
                ('employee_id', '=', employee.id),
                ('date_from', '>=', today - timedelta(days=120)),
                ('struct_id', '!=', False),
                ('payslip_run_id', 'not like', '%PRESTACIONES%'),
                ('payslip_run_id', 'not like', '%AGUINALDO%'),
                ('payslip_run_id', 'not like', '%COMPLEMENTO%'),
                ('state', 'in', ['validated', 'paid']),
            ], order='date_from asc')

            totals = dict.fromkeys(BUCKET_KEYS, 0.0)
            months_found = 0

            if payslips:
                cursor = today.replace(day=1) - relativedelta(months=3)
                mes, anio = cursor.month, cursor.year
                mes_completo = 0
                pendiente = dict.fromkeys(BUCKET_KEYS, 0.0)

                for _iteracion in range(3):
                    for payslip in payslips:
                        if not (payslip.date_from.month == mes and payslip.date_from.year == anio
                                and payslip.date_to.month == mes and payslip.date_to.year == anio):
                            continue

                        ausencias = sum(
                            wd.number_of_days for wd in payslip.worked_days_line_ids
                            if wd.work_entry_type_id.is_leave)
                        if ausencias > 12:
                            mes_completo = 0
                            continue

                        if payslip.date_from.day == 1 and payslip.date_to.day >= 28:
                            mes_completo = 2
                        elif payslip.date_from.day == 1 and payslip.date_to.day == 15:
                            mes_completo = 1
                        elif payslip.date_from.day == 16 and payslip.date_to.day >= 28 and mes_completo == 1:
                            mes_completo = 2

                        gross = sum(line.total for line in payslip.line_ids if line.code == 'GROSS')
                        if gross <= 0:
                            continue

                        montos = dict.fromkeys(BUCKET_KEYS, 0.0)
                        for line in payslip.line_ids:
                            bucket = BUCKET_BY_CODE.get(line.code)
                            if bucket:
                                montos[bucket] += line.total

                        if mes_completo == 1 and payslip.date_from.day == 1 and payslip.date_to.day == 15:
                            pendiente = montos
                        elif mes_completo == 2 and payslip.date_from.day == 16 and payslip.date_to.day >= 30:
                            for key in BUCKET_KEYS:
                                totals[key] += montos[key] + pendiente[key]
                            pendiente = dict.fromkeys(BUCKET_KEYS, 0.0)
                            months_found += 1
                            mes_completo = 0
                        elif mes_completo == 2 and payslip.date_from.day == 1 and payslip.date_to.day >= 30:
                            for key in BUCKET_KEYS:
                                totals[key] += montos[key]
                            months_found += 1
                            mes_completo = 0

                    mes += 1
                    if mes > 12:
                        mes = 1
                        anio += 1

            if months_found:
                avg = {key: totals[key] / months_found for key in BUCKET_KEYS}
                salario = avg['base'] + avg['bon_incentivo'] + avg['bon_fija'] + avg['otras_bonif'] + avg['horas_extras']
                employee.x_promedio_salario_str = '{:,.2f}'.format(salario)
                employee.x_igss_promedio_str = '{:,.2f}'.format(avg['igss'])
                employee.x_salario_base_promedio_str = '{:,.2f}'.format(avg['base'])
                employee.x_bonificacion_incentivo_promedio_str = '{:,.2f}'.format(
                    avg['bon_incentivo'] + avg['bon_fija'] + avg['otras_bonif'])
                employee.x_horas_extras_promedio_str = '{:,.2f}'.format(avg['horas_extras'])
                employee.x_isr_promedio_str = '{:,.2f}'.format(avg['isr'])
                employee.x_total_deducciones_promedio_str = '{:,.2f}'.format(avg['igss'] + avg['isr'])
                employee.x_total_devengado_promedio_str = '{:,.2f}'.format(salario - (avg['igss'] + avg['isr']))
            else:
                for field_name in PROMEDIO_FIELDS:
                    employee[field_name] = '0.00'

    def get_current_date(self):
        today = fields.Date.today()
        return f'{today.day} de {MESES[today.month]} del {today.year}'

    def get_fecha_constancia_laboral(self):
        inicio = self._get_first_contract_date()
        return f'el {inicio.day}/{inicio.month}/{inicio.year}' if inicio else ''

    def get_format_date_contrat_end(self):
        fin = self.departure_date or fields.Date.today()
        return f'al {fin.day}/{fin.month}/{fin.year}'

    def getSalario(self):
        self.ensure_one()
        version = self.version_id
        if not version:
            return 0.0
        total = version.wage + version.x_bonificacion_incentivo + version.x_bonificacion_fija \
            + version.x_bonificacion_productividad
        return round(total, 2)

    def getIGSS(self):
        self.ensure_one()
        return round(self.version_id.wage * 0.0483, 2) if self.version_id else 0.0
