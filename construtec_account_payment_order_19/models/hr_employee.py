from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    enterprise_employee_ref = fields.Char(
        string='Referencia de Empleado en Enterprise', readonly=True, copy=False, index=True,
        help='Id del empleado en la instalación Enterprise de origen. Uso técnico interno para '
             'no duplicar el registro en cada sincronización - los empleados de esta instalación '
             'siempre se crean en Enterprise, nunca aquí.')
