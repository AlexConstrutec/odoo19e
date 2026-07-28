from odoo import api, fields, models

MESES = [
    ('1', 'Enero'), ('2', 'Febrero'), ('3', 'Marzo'), ('4', 'Abril'),
    ('5', 'Mayo'), ('6', 'Junio'), ('7', 'Julio'), ('8', 'Agosto'),
    ('9', 'Septiembre'), ('10', 'Octubre'), ('11', 'Noviembre'), ('12', 'Diciembre'),
]


class HrDiasLaboradosMes(models.Model):
    _name = 'hr.dias.laborados.mes'
    _description = 'Días laborados oficiales por mes (Informe del Empleador)'
    _order = 'anio, mes'

    anio = fields.Integer(string='Año', required=True)
    mes = fields.Selection(MESES, string='Mes', required=True)
    dias_calendario = fields.Integer(string='Días Calendario', required=True)
    descanso_semanal = fields.Integer(string='Descanso Semanal', required=True)
    asueto = fields.Integer(string='Asueto', required=True)
    total_ausencia = fields.Integer(string='Total Ausencia')
    dias_laborados = fields.Integer(string='Días Laborados', required=True)

    _sql_constraints = [
        ('anio_mes_unique', 'unique(anio, mes)', 'Ya existe un registro de días laborados para ese año y mes.'),
    ]

    @api.model
    def get_dias_laborados(self, date_start, date_end=None):
        """Suma los días laborados oficiales entre date_start y date_end (mismo año que date_end)."""
        if not date_start:
            return 0
        date_end = date_end or fields.Date.today()
        mes_inicio = 1 if date_start.year < date_end.year else date_start.month
        registros = self.search([
            ('anio', '=', date_end.year),
            ('mes', 'in', [str(m) for m in range(mes_inicio, date_end.month + 1)]),
        ])
        return sum(registros.mapped('dias_laborados'))
