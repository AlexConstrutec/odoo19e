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
    tipo_cuenta_raw = fields.Selection(
        [('monetaria', 'Monetaria'), ('ahorro', 'Ahorro')],
        string='Tipo de Cuenta (todos, interno)', groups='hr.group_hr_manager', copy=False,
        help='Sincronizado desde Enterprise (`res.partner.bank.tipo_cuenta` de la cuenta '
             'bancaria principal del empleado, ver res_partner_bank.py) - mismo criterio y '
             'mismas restricciones que `cuenta_bancaria_raw`/`banco_nombre_raw`.')

    cuenta_bancaria = fields.Char(
        string='Cuenta Bancaria', compute='_compute_mi_info_bancaria', compute_sudo=True,
        help='Solo resuelve a un valor real cuando este es el empleado vinculado al usuario '
             'actual (self.env.user) - para cualquier otro empleado, queda vacío sin importar '
             'los permisos que tenga el usuario. Ver cuenta_bancaria_raw para el dato real.')
    banco_nombre = fields.Char(
        string='Banco', compute='_compute_mi_info_bancaria', compute_sudo=True)
    tipo_cuenta = fields.Selection(
        [('monetaria', 'Monetaria'), ('ahorro', 'Ahorro')],
        string='Tipo de Cuenta', compute='_compute_mi_info_bancaria', compute_sudo=True)

    @api.depends('user_id', 'cuenta_bancaria_raw', 'banco_nombre_raw', 'tipo_cuenta_raw')
    @api.depends_context('uid')
    def _compute_mi_info_bancaria(self):
        for employee in self:
            if employee.user_id and employee.user_id == self.env.user:
                employee.cuenta_bancaria = employee.sudo().cuenta_bancaria_raw
                employee.banco_nombre = employee.sudo().banco_nombre_raw
                employee.tipo_cuenta = employee.sudo().tipo_cuenta_raw
            else:
                employee.cuenta_bancaria = False
                employee.banco_nombre = False
                employee.tipo_cuenta = False

    _WORK_CONTACT_FIELDS = ('work_phone', 'mobile_phone', 'work_email')

    def write(self, vals):
        """Preserva work_phone/mobile_phone/work_email al vincular user_id a CUALQUIER empleado.

        Decisión explícita del usuario: teléfonos y correos deben vivir en los campos NATIVOS
        de hr.employee (work_phone/mobile_phone/work_email/private_phone/private_email), no en
        campos propios - para que "viajen de ficha a ficha" usando el modelo estándar de Odoo.
        El problema: work_phone/mobile_phone/work_email son todos `compute + store + inverse`,
        resueltos desde `work_contact_id` (`work_phone`/`work_email` desde
        `_compute_work_contact_details`, `..\\odoo\\addons\\hr\\models\\hr_employee.py:822`).
        En cuanto se asigna `user_id` a un empleado, el propio `write()`/`create()` de
        hr.employee (`_sync_user()`/`_remove_work_contact_id()`, mismo archivo, líneas
        1314-1334) REEMPLAZA `work_contact_id` por el partner del usuario recién vinculado -
        que no tiene ni teléfono ni correo - borrando en silencio lo que ya había ahí. Confirmado
        con un test real antes de este fix.

        Bug real encontrado en producción (2026-09-24): la primera versión de este fix acotaba
        la protección a `self.filtered('enterprise_employee_ref')` - "solo empleados
        sincronizados, nunca empleados reales de Community, que no deberían existir de todas
        formas" - un razonamiento que pasó por alto que **ningún empleado real de Enterprise
        tiene `enterprise_employee_ref` tampoco** (ese campo solo existe para identificar un
        espejo EN Community hacia su origen en Enterprise - un empleado genuino, en cualquiera
        de las dos ediciones, simplemente no lo tiene). Resultado: la protección nunca se
        activaba para ningún empleado real de Enterprise - cada vez que RR.HH. vinculaba un
        usuario nuevo a un empleado aquí mismo (el flujo normal de alta), su `work_email` se
        borraba sin protección, y el siguiente pull periódico de Community copiaba fielmente ese
        vacío, "borrando" el correo también ahí - el síntoma reportado por el usuario ("se
        borran los correos... cuando se sincroniza"), aunque el borrado real ocurre aquí, al
        vincular el usuario, no durante la sincronización en sí (la sincronización solo propaga
        el daño ya hecho). Reproducido con un test real (empleado sin `enterprise_employee_ref`,
        `work_email` puesto a mano, vincular `user_id` -> `work_email` queda `False`) antes de
        aplicar este fix. **La protección ahora aplica a CUALQUIER empleado** cuando `user_id`
        está en `vals`, sin filtrar por `enterprise_employee_ref` - es un `write()` defensivo
        (guarda-y-reaplica solo si el valor se perdió), seguro de aplicar siempre.

        `private_phone`/`private_email` NO necesitan este tratamiento - son `Char` simples sin
        `compute`/`inverse`, no dependen de `work_contact_id`."""
        synced = self if 'user_id' in vals else self.browse()
        values_before = {emp.id: {f: emp[f] for f in self._WORK_CONTACT_FIELDS} for emp in synced}
        res = super().write(vals)
        for emp_id, before in values_before.items():
            employee = self.browse(emp_id)
            employee_vals = {f: v for f, v in before.items() if v and not employee[f]}
            if employee_vals:
                employee.write(employee_vals)
        return res
