from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval

CODE_PYTHON_DEFAULT = '''
# Variables disponibles (nombre tecnico exacto de los campos en hr.version):
#   employee: hr.employee del empleado
#   version: hr.version (contrato vigente del empleado)
#   wage
#   x_bonificacion_fija
#   x_bonificacion_incentivo
#   x_bonificacion_extra
#   x_bonificacion_productividad
#   x_horas_extra_valor
#
# Asigna a "result" el valor unitario de la hora extra de esta jornada.
result = wage / 30 / 8
'''.lstrip()


class HrOvertimeShift(models.Model):
    _name = 'hr.overtime.shift'
    _description = 'Jornada de Hora Extra'
    _order = 'name'

    name = fields.Char(string='Jornada', required=True)
    active = fields.Boolean(string='Activo', default=True)
    amount_select = fields.Selection([
        ('fix', 'Monto Fijo'),
        ('code', 'Código Python'),
    ], string='Cálculo del Valor Hora', default='fix', required=True,
        help='Monto Fijo: se escribe el valor a mano en cada registro de Horas Extra. '
             'Código Python: el valor se calcula solo con una fórmula que puede usar wage, '
             'x_bonificacion_fija, x_bonificacion_incentivo, x_bonificacion_extra, '
             'x_bonificacion_productividad y x_horas_extra_valor (nombre técnico exacto de '
             'los campos del contrato del empleado). Cualquier empleado puede usar cualquier '
             'jornada — no hace falta configurarla antes por empleado.')
    code_python = fields.Text(string='Código Python', default=CODE_PYTHON_DEFAULT)

    def _eval_code_python(self, employee):
        self.ensure_one()
        version = employee.current_version_id
        localdict = {
            'employee': employee,
            'version': version,
            'wage': version.wage or 0.0,
            'x_bonificacion_fija': version.x_bonificacion_fija or 0.0,
            'x_bonificacion_incentivo': version.x_bonificacion_incentivo or 0.0,
            'x_bonificacion_extra': version.x_bonificacion_extra or 0.0,
            'x_bonificacion_productividad': version.x_bonificacion_productividad or 0.0,
            'x_horas_extra_valor': version.x_horas_extra_valor or 0.0,
            'result': 0.0,
        }
        try:
            safe_eval(self.code_python, localdict, mode='exec')
        except Exception as e:
            raise UserError(self.env._(
                'Error en el código Python de la jornada "%(jornada)s": %(error)s',
                jornada=self.name, error=e,
            ))
        return float(localdict.get('result') or 0.0)


class HrOvertime(models.Model):
    _name = 'hr.overtime'
    _description = 'Horas Extra'
    _order = 'date desc'

    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True, ondelete='cascade')
    date = fields.Date(string='Fecha', required=True, default=fields.Date.context_today)
    shift_id = fields.Many2one('hr.overtime.shift', string='Jornada', required=True)
    amount_select = fields.Selection(related='shift_id.amount_select', string='Cálculo', readonly=True)
    number_of_hours = fields.Float(string='Cant. Horas', required=True)
    unit_amount_manual = fields.Float(string='Monto Unitario (manual)')
    unit_amount = fields.Float(
        string='Monto Unitario', compute='_compute_unit_amount',
        inverse='_inverse_unit_amount', store=True, readonly=False)
    total_amount = fields.Float(
        string='Monto Total', compute='_compute_total_amount', store=True, readonly=True)
    name = fields.Char(string='Descripción', compute='_compute_name', store=True, readonly=True)

    # Metodo separado de _compute_total_amount a proposito: si algun dia se crea
    # un hr.overtime pasando 'unit_amount' directamente (ej. una carga masiva),
    # Odoo no vuelve a ejecutar el compute de ese campo, pero total_amount tiene
    # su propio metodo y sigue calculandose igual.
    @api.depends(
        'shift_id.amount_select', 'shift_id.code_python', 'unit_amount_manual',
        'employee_id.current_version_id.wage',
        'employee_id.current_version_id.x_bonificacion_fija',
        'employee_id.current_version_id.x_bonificacion_incentivo',
        'employee_id.current_version_id.x_bonificacion_extra',
        'employee_id.current_version_id.x_bonificacion_productividad',
        'employee_id.current_version_id.x_horas_extra_valor',
    )
    def _compute_unit_amount(self):
        for overtime in self:
            if overtime.shift_id.amount_select == 'code' and overtime.shift_id.code_python and overtime.employee_id:
                overtime.unit_amount = overtime.shift_id._eval_code_python(overtime.employee_id)
            else:
                overtime.unit_amount = overtime.unit_amount_manual

    @api.depends('unit_amount', 'number_of_hours')
    def _compute_total_amount(self):
        for overtime in self:
            overtime.total_amount = overtime.unit_amount * overtime.number_of_hours

    def _inverse_unit_amount(self):
        for overtime in self:
            if overtime.shift_id.amount_select != 'code':
                overtime.unit_amount_manual = overtime.unit_amount

    @api.depends('employee_id.name', 'date')
    def _compute_name(self):
        for overtime in self:
            overtime.name = f'{overtime.employee_id.name} - {overtime.date}' if overtime.employee_id and overtime.date else ''
