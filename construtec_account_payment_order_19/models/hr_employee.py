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
    @api.depends_context('uid')
    def _compute_mi_info_bancaria(self):
        for employee in self:
            if employee.user_id and employee.user_id == self.env.user:
                employee.cuenta_bancaria = employee.sudo().cuenta_bancaria_raw
                employee.banco_nombre = employee.sudo().banco_nombre_raw
            else:
                employee.cuenta_bancaria = False
                employee.banco_nombre = False

    _WORK_CONTACT_FIELDS = ('work_phone', 'mobile_phone', 'work_email')

    def write(self, vals):
        """Preserva work_phone/mobile_phone/work_email al vincular user_id a un empleado
        sincronizado.

        Decisión explícita del usuario: teléfonos y correos deben vivir en los campos NATIVOS
        de hr.employee (work_phone/mobile_phone/work_email/private_phone/private_email), no en
        campos propios - para que "viajen de ficha a ficha" usando el modelo estándar de Odoo.
        El problema: work_phone/mobile_phone/work_email son todos `compute + store + inverse`,
        resueltos desde `work_contact_id` (`work_phone`/`work_email` desde
        `_compute_work_contact_details`, `..\\odoo\\addons\\hr\\models\\hr_employee.py:822`).
        En cuanto se asigna `user_id` a un empleado, el propio `write()`/`create()` de
        hr.employee (`_sync_user()`/`_remove_work_contact_id()`, mismo archivo, líneas
        1314-1334) REEMPLAZA `work_contact_id` por el partner del usuario recién vinculado -
        que no tiene ni teléfono ni correo - borrando en silencio lo que ya habíamos
        sincronizado desde Enterprise. Confirmado con un test real antes de este fix. Aquí se
        toma una foto de los valores antes del write() del núcleo y se reaplican después si el
        núcleo los dejó vacíos - solo para empleados sincronizados (`enterprise_employee_ref`),
        nunca para empleados reales de Community (que no deberían existir de todas formas, pero
        por si acaso).

        `private_phone`/`private_email` NO necesitan este tratamiento - son `Char` simples sin
        `compute`/`inverse`, no dependen de `work_contact_id`."""
        synced = self.filtered('enterprise_employee_ref') if 'user_id' in vals else self.browse()
        values_before = {emp.id: {f: emp[f] for f in self._WORK_CONTACT_FIELDS} for emp in synced}
        res = super().write(vals)
        for emp_id, before in values_before.items():
            employee = self.browse(emp_id)
            employee_vals = {f: v for f, v in before.items() if v and not employee[f]}
            if employee_vals:
                employee.write(employee_vals)
        return res
