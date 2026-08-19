from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    enterprise_employee_ref = fields.Char(
        string='Referencia de Empleado en Enterprise', readonly=True, copy=False, index=True,
        help='Id del empleado en la instalación Enterprise de origen. Uso técnico interno para '
             'no duplicar el registro en cada sincronización - los empleados de esta instalación '
             'siempre se crean en Enterprise, nunca aquí.')

    cuenta_bancaria_raw = fields.Char(
        string='Cuenta Bancaria (todos, interno)', groups='hr.group_hr_manager', copy=False,
        help='Sincronizado desde Enterprise para TODOS los empleados. Restringido a RR.HH. a '
             'propósito - un usuario normal nunca debe poder leer la cuenta bancaria de otro '
             'empleado por aquí. Ver el campo público "Cuenta Bancaria" (self-scoped) para el '
             'uso normal en Solicitudes de Pago.')
    banco_nombre_raw = fields.Char(
        string='Banco (todos, interno)', groups='hr.group_hr_manager', copy=False)

    cuenta_bancaria = fields.Char(
        string='Cuenta Bancaria', compute='_compute_mi_info_bancaria', compute_sudo=True,
        help='Solo resuelve a un valor real cuando este es el empleado vinculado al usuario '
             'actual (self.env.user) - para cualquier otro empleado, queda vacío sin importar '
             'los permisos que tenga el usuario. Ver cuenta_bancaria_raw para el dato real.')
    banco_nombre = fields.Char(
        string='Banco', compute='_compute_mi_info_bancaria', compute_sudo=True)

    @api.depends('user_id', 'cuenta_bancaria_raw', 'banco_nombre_raw')
    def _compute_mi_info_bancaria(self):
        for employee in self:
            if employee.user_id and employee.user_id == self.env.user:
                employee.cuenta_bancaria = employee.sudo().cuenta_bancaria_raw
                employee.banco_nombre = employee.sudo().banco_nombre_raw
            else:
                employee.cuenta_bancaria = False
                employee.banco_nombre = False
