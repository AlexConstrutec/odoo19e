import logging

from odoo import api, fields, models

from ..tools.enterprise_sync_api import (
    EnterpriseSyncError, create_employee_in_enterprise, push_employee_personal_data,
)

_logger = logging.getLogger(__name__)

# Mismos catálogos/códigos que Enterprise (construtec_hr_employee_19/models/hr_employee_selections.py)
# - duplicados a propósito aquí, mismo criterio ya usado en este módulo para MARITAL_CODE/SEX_CODE
# y similares (catálogo chico, cada base mantiene su propia copia en vez de compartir un módulo
# solo para esto). Si se agrega/cambia una opción en Enterprise, hay que replicarla aquí también.
DISCAPACIDAD = [
    ('1', 'Ninguna'),
    ('2', 'Discapacidad auditiva'),
    ('3', 'Discapacidad visual'),
    ('4', 'Discapacidad múltiple'),
    ('5', 'Discapacidad física o motora'),
    ('6', 'Discapacidad intelectual'),
    ('7', 'Otra'),
]
# Verificado 2026-09-17 - fuente: "Formato_Informe Empleados.xlsx", descargado por el
# usuario directamente del sistema electrónico de MITRAB (informeynomina2989.mintrabajo.gob.gt),
# transcrito de sus hojas de catálogo "Pueblo_pertenencia"/"Comunidad_lingüistica". Reemplaza
# dos intentos previos sin esta fuente (ver hr_employee_selections.py en Enterprise).
PUEBLO_PERTENENCIA = [
    ('1', 'Maya'),
    ('2', 'Garífuna'),
    ('3', 'Xinka'),
    ('4', 'Afrodescendiente / creole / afromestizo'),
    ('5', 'Ladino'),
    ('6', 'Extranjero'),
]
# Solo cubre los 22 idiomas mayas (código 99 = "No aplica") - NO hay código propio
# para español/garífuna/xinka/idioma extranjero en este catálogo. DEBE quedar
# idéntico, código por código, a la copia de Enterprise - el write() de este módulo
# empuja el NÚMERO, no la etiqueta, así que un desfase corrompería el dato en
# silencio al sincronizar.
COMUNIDAD_LINGUISTICA = [
    ('1', "Achi'"), ('2', 'Akateka'), ('3', 'Awakateka'), ('4', "Ch'orti'"),
    ('5', 'Chalchiteka'), ('6', 'Chuj'), ('7', "Itza'"), ('8', 'Ixil'), ('9', 'Jakalteka'),
    ('10', "K'iche'"), ('11', 'Kaqchikel'), ('12', 'Mam'), ('13', 'Mopan'), ('14', 'Poqomam'),
    ('15', "Poqomchi'"), ('16', "Q'anjob'al"), ('17', "Q'eqchi'"), ('18', 'Sakapulteka'),
    ('19', 'Sipakapense'), ('20', 'Tektiteka'), ('21', "Tz'utujil"), ('22', 'Uspanteka'),
    ('99', 'No aplica'),
]
# Idéntico a NIVEL_ACADEMICO en Enterprise (hr_employee_selections.py) - reemplaza el `certificate`
# nativo de Odoo (solo 5 opciones genéricas en inglés: Graduate/Bachelor/Master/Doctor/Other) por
# los 13 niveles reales del catálogo "Nivel_Educativo" de MITRAB. Reutiliza a propósito las claves
# nativas donde coinciden ('other'/'graduate'/'bachelor'/'master'/'doctor') y usa el código MITRAB
# tal cual como clave para los niveles que Odoo no tenía (Primaria/Básico/Diversificado
# incompleto, Estudiante/Técnico universitario, Postgrado) - así el valor guardado YA ES el
# código que espera el Informe del Empleador para esos niveles, sin traducción aparte (ver
# `construtec_hr_reports_19::report_informe_empleador.py` en Enterprise, `CERTIFICATE_CODE`).
# DEBE quedar idéntico a la copia de Enterprise por la misma razón que los catálogos de arriba.
NIVEL_ACADEMICO = [
    ('other', 'Ninguno'),
    ('2', 'Primaria Incompleta'),
    ('3', 'Primaria Completa'),
    ('4', 'Básico Incompleto'),
    ('5', 'Básico Completo'),
    ('6', 'Diversificado Incompleto'),
    ('graduate', 'Diversificado Completo'),
    ('8', 'Estudiante Universitario'),
    ('9', 'Técnico Universitario'),
    ('bachelor', 'Licenciatura'),
    ('11', 'Postgrado'),
    ('master', 'Maestría'),
    ('doctor', 'Doctorado'),
]

# Campos "personales" que se editan aquí (Community) y se empujan hacia Enterprise - ver
# _sync_personal_data_to_enterprise() y el método receptor whitelisted en Enterprise
# (hr_employee.py::sync_personal_data_from_community(), mismo nombre de lista allá,
# PERSONAL_DATA_FIELDS). Pedido explícito del usuario: personas sin privilegios de nómina en
# Enterprise (y sin cuenta ahí) cargan estos datos desde Community; Enterprise sigue siendo
# dueño de todo lo demás (salario, banco, estado laboral/baja).
PERSONAL_DATA_FIELDS = (
    'primer_nombre', 'segundo_nombre', 'tercer_nombre', 'primer_apellido', 'segundo_apellido',
    'apellido_casada', 'discapacidad', 'nit', 'igss', 'pueblo_pertenencia', 'comunidad_linguistica',
    'marital', 'sex', 'birthday', 'children', 'identification_id', 'permit_no', 'certificate',
    'study_field', 'country_id', 'country_of_birth', 'municipio_nombre',
)


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

    # --- Datos personales, editables aquí, empujados hacia Enterprise (ver PERSONAL_DATA_FIELDS
    # arriba y _sync_personal_data_to_enterprise() más abajo). country_id/country_of_birth
    # (Nacionalidad/País de Origen), marital/sex/birthday/children/identification_id/permit_no/
    # certificate/study_field YA son campos nativos de hr.employee (Community también tiene el
    # módulo core `hr`, no hace falta duplicarlos) - solo se agregan aquí los que sí son
    # exclusivos de construtec_hr_employee_19 (Enterprise-only) más "Lugar de Nacimiento" como
    # texto libre (no hay catálogo de municipios en Community, se resuelve por nombre del otro
    # lado - ver sync_personal_data_from_community() en Enterprise).
    primer_nombre = fields.Char(string='Primer nombre')
    segundo_nombre = fields.Char(string='Segundo nombre')
    tercer_nombre = fields.Char(string='Tercer nombre')
    primer_apellido = fields.Char(string='Primer apellido')
    segundo_apellido = fields.Char(string='Segundo apellido')
    apellido_casada = fields.Char(string='Apellido de casada')
    discapacidad = fields.Selection(DISCAPACIDAD, string='Discapacidad', default='1')
    nit = fields.Char(string='NIT')
    igss = fields.Char(string='Número de afiliación al IGSS')
    municipio_nombre = fields.Char(
        string='Lugar de Nacimiento (Municipio)',
        help='Texto libre - Community no tiene el catálogo de municipios de Enterprise. Al '
             'sincronizar, Enterprise intenta resolverlo contra su propio catálogo por nombre '
             'exacto; si no encuentra uno igual, queda para que RR.HH. lo resuelva a mano allá.')
    pueblo_pertenencia = fields.Selection(PUEBLO_PERTENENCIA, string='Pueblo de pertenencia')
    comunidad_linguistica = fields.Selection(COMUNIDAD_LINGUISTICA, string='Comunidad Lingüística')
    # Sobrescribe el `certificate` nativo (Selection normal, no `_inherits` - se puede reemplazar
    # la lista igual que ya hace Enterprise) - ver NIVEL_ACADEMICO arriba para el porqué.
    certificate = fields.Selection(NIVEL_ACADEMICO, string='Nivel académico', default='other')

    personal_data_sync_state = fields.Selection(
        [('pendiente', 'Pendiente'), ('enviado', 'Enviado'), ('error', 'Error')],
        string='Sincronización de Datos Personales', default='pendiente', copy=False)
    personal_data_sync_error = fields.Char(string='Detalle del Error', copy=False)
    # Lista separada por comas de los campos de PERSONAL_DATA_FIELDS pendientes de empujar -
    # ver el bug real documentado en write()/_prepare_personal_data_sync_vals() de más abajo
    # (2026-09-17): nunca se manda un snapshot completo, solo los campos que de verdad
    # cambiaron - este campo recuerda cuáles son, para que un reintento (botón o cron) mande
    # exactamente esos y ningún otro, incluso si mientras tanto otros campos de este mismo
    # empleado siguen en blanco en Community por no haber sido llenados todavía.
    personal_data_sync_pending_fields = fields.Char(copy=False)

    def _prepare_personal_data_sync_vals(self, fields_to_push):
        """Arma el payload SOLO con los campos en `fields_to_push` (subconjunto de
        PERSONAL_DATA_FIELDS) - nunca un snapshot completo de todos los campos.

        Bug real de producción (2026-09-17): la versión original leía TODOS los campos de
        PERSONAL_DATA_FIELDS sin importar cuáles habían cambiado, y los mandaba todos en cada
        push. Para un empleado que ya existía antes de esta funcionalidad, la mayoría de estos
        campos seguían en blanco en Community (nunca se hizo un backfill desde Enterprise) -
        así que editar UN SOLO campo (ej. `comunidad_linguistica`) empujaba también, en blanco,
        primer_nombre/segundo_nombre/tercer_nombre/primer_apellido/segundo_apellido/
        apellido_casada/identification_id, BORRANDO en Enterprise datos reales que ya existían
        ahí. Ver la sección de este bug en el CLAUDE.md del módulo."""
        self.ensure_one()
        vals = {}
        for f in fields_to_push:
            if f == 'birthday':
                # date no es serializable a JSON (`requests.post(json=...)` truena) - se manda
                # como texto ISO; Enterprise lo pasa tal cual a write(), que sí lo acepta así.
                vals['birthday'] = self.birthday.isoformat() if self.birthday else False
            elif f == 'country_id':
                vals['nacionalidad_code'] = self.country_id.code or False
            elif f == 'country_of_birth':
                vals['pais_origen_code'] = self.country_of_birth.code or False
            elif f == 'municipio_nombre':
                vals['municipio_nombre'] = self.municipio_nombre or False
            else:
                vals[f] = self[f]
        return vals

    def _create_employee_in_enterprise(self):
        """Crea este empleado (que todavía NO existe en Enterprise - sin `enterprise_employee_ref`)
        allá, a partir de un alta hecha aquí en Community por alguien con
        `group_construtec_employee_data_entry` - decisión explícita del usuario 2026-09-18: la
        puerta de entrada para dar de alta colaboradores puede ser Community, no solo
        Enterprise (antes de esto, los empleados SOLO se creaban en Enterprise).

        Manda TODOS los campos de PERSONAL_DATA_FIELDS que ya estén cargados (no solo un
        delta - a diferencia de una edición posterior, aquí no hay nada existente en Enterprise
        que se pueda pisar, el registro todavía no existe del otro lado) más `name`/`job_title`/
        `department_id` (nombre, no id - Enterprise resuelve/crea el departamento por nombre) y
        la compañía real de Enterprise (`enterprise_company_ref`, ya resuelta contra el catálogo
        de compañías que Community ya sincroniza)."""
        self.ensure_one()
        company = self.company_id
        if company.payment_order_role != 'solicitante' or not company.payment_order_sync_enabled:
            return
        vals = self._prepare_personal_data_sync_vals(PERSONAL_DATA_FIELDS)
        vals['name'] = self.name
        vals['job_title'] = self.job_title or False
        vals['department_name'] = self.department_id.name or False
        vals['company_ref'] = company.payment_order_default_company_id.enterprise_company_ref or False
        try:
            new_ref = create_employee_in_enterprise(
                company.payment_order_sync_url, company.payment_order_sync_db,
                company.payment_order_sync_login, company.payment_order_sync_api_key, vals)
        except EnterpriseSyncError as exc:
            _logger.warning('Error creando el empleado %s en Enterprise: %s', self.id, exc)
            self.write({'personal_data_sync_state': 'error', 'personal_data_sync_error': str(exc)})
        else:
            self.write({
                'enterprise_employee_ref': str(new_ref),
                'personal_data_sync_state': 'enviado', 'personal_data_sync_error': False,
                'personal_data_sync_pending_fields': False,
            })

    def _sync_personal_data_to_enterprise(self):
        """Empuja SOLO los campos listados en `personal_data_sync_pending_fields` de cada
        empleado (nunca todos los de PERSONAL_DATA_FIELDS) - ver write() más abajo, que es
        quien llena ese campo con lo que de verdad cambió antes de llamar aquí.

        Un empleado sin `enterprise_employee_ref` todavía no existe en Enterprise - en vez de
        actualizar, hay que crearlo primero (ver `_create_employee_in_enterprise()`). Esto
        cubre tanto el alta inicial (llamada directa desde `create()`) como un reintento manual/
        del cron sobre un alta que falló la primera vez - mismo botón/cron, mismo
        `personal_data_sync_state`, sin UI nueva."""
        for employee in self:
            company = employee.company_id
            if company.payment_order_role != 'solicitante' or not company.payment_order_sync_enabled:
                continue
            if not employee.enterprise_employee_ref:
                employee._create_employee_in_enterprise()
                continue
            fields_to_push = [f for f in (employee.personal_data_sync_pending_fields or '').split(',') if f]
            if not fields_to_push:
                continue
            try:
                push_employee_personal_data(
                    company.payment_order_sync_url, company.payment_order_sync_db,
                    company.payment_order_sync_login, company.payment_order_sync_api_key,
                    employee.enterprise_employee_ref,
                    employee._prepare_personal_data_sync_vals(fields_to_push))
            except EnterpriseSyncError as exc:
                _logger.warning(
                    'Error sincronizando datos personales del empleado %s hacia Enterprise: %s',
                    employee.id, exc)
                employee.write({'personal_data_sync_state': 'error', 'personal_data_sync_error': str(exc)})
            else:
                employee.write({
                    'personal_data_sync_state': 'enviado', 'personal_data_sync_error': False,
                    'personal_data_sync_pending_fields': False,
                })

    def action_retry_personal_data_sync(self):
        self.filtered(lambda e: e.personal_data_sync_state == 'error')._sync_personal_data_to_enterprise()

    @api.model
    def _cron_retry_personal_data_sync(self):
        self.search([
            ('personal_data_sync_state', '=', 'error'),
            ('company_id.payment_order_role', '=', 'solicitante'),
        ])._sync_personal_data_to_enterprise()

    @api.model_create_multi
    def create(self, vals_list):
        """Punto de entrada para dar de alta un colaborador desde Community (decisión explícita
        del usuario 2026-09-18) - antes de esto, los empleados solo se creaban en Enterprise;
        Community únicamente recibía espejos vía `_sync_employees_from_enterprise()`.

        La señal para distinguir un alta GENUINA (hecha por una persona con
        `group_construtec_employee_data_entry` en el formulario) de un espejo que
        `_sync_employees_from_enterprise()` acaba de traer es simple: el espejo SIEMPRE incluye
        `enterprise_employee_ref` en su propio `vals` (es justo el id del empleado que ya existe
        del otro lado) - un alta nueva nunca lo trae, porque todavía no existe en ningún lado
        más que aquí."""
        records = super().create(vals_list)
        to_create_in_enterprise = self.browse()
        for vals, record in zip(vals_list, records):
            if not vals.get('enterprise_employee_ref'):
                to_create_in_enterprise |= record
        for employee in to_create_in_enterprise:
            employee._create_employee_in_enterprise()
        records._sync_user_phone()
        return records

    def _sync_user_phone(self):
        """Garantiza que el usuario de Odoo vinculado (user_id) tenga el MISMO teléfono que el
        empleado - pedido explícito del usuario (2026-09-30): "todos los usuarios están ligados
        a un empleado... necesito que los usuarios hereden el número de teléfono del empleado en
        Community". Independiente del mecanismo nativo `work_contact_id` (frágil - ver el fix de
        `_WORK_CONTACT_FIELDS` más abajo, que además solo actúa reactivamente al momento exacto
        de vincular `user_id`) - esto escribe DIRECTO sobre `user_id.partner_id.phone`, sin pasar
        por ningún compute/inverse. Mismo orden de prioridad ya usado en
        `account_payment_order.py::_onchange_employee_id()` para "Teléfono": work_phone >
        mobile_phone > private_phone. El empleado es la fuente real - si difieren, el del
        empleado gana (nunca al revés)."""
        for employee in self:
            if not employee.user_id:
                continue
            phone = employee.work_phone or employee.mobile_phone or employee.private_phone
            if phone and employee.user_id.partner_id.phone != phone:
                employee.user_id.partner_id.phone = phone

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
        usuario nuevo a un empleado ahí (el flujo normal de alta), su `work_email` se borraba
        sin protección, y el siguiente pull periódico de Community copiaba fielmente ese vacío,
        "borrando" el correo también ahí - el síntoma reportado por el usuario ("se borran los
        correos... cuando se sincroniza"), aunque el borrado real ocurre en Enterprise al
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
        # Campos de PERSONAL_DATA_FIELDS que este write() en particular está cambiando - NUNCA
        # se manda un snapshot completo (ver el bug real documentado en
        # _prepare_personal_data_sync_vals()), solo estos. `skip_personal_data_push`: usado por
        # _sync_employees_from_enterprise() al rellenar huecos con datos que YA vienen de
        # Enterprise - no tiene sentido (ni es seguro) reenviarlos como si el usuario los
        # hubiera editado aquí.
        changed_personal_fields = (
            [] if self.env.context.get('skip_personal_data_push')
            else [f for f in PERSONAL_DATA_FIELDS if f in vals])
        to_push = self.filtered('enterprise_employee_ref') if changed_personal_fields else self.browse()

        res = super().write(vals)

        for emp_id, before in values_before.items():
            employee = self.browse(emp_id)
            employee_vals = {f: v for f, v in before.items() if v and not employee[f]}
            if employee_vals:
                employee.write(employee_vals)
        if {'user_id', 'work_phone', 'mobile_phone', 'private_phone'} & set(vals):
            self._sync_user_phone()
        if to_push:
            # Acumula sobre los campos ya pendientes (ej. un push anterior falló) - así un
            # reintento manda todo lo que de verdad cambió desde el último éxito, ni más ni
            # menos. `changed_personal_fields` es la misma lista para todos los de `to_push`
            # (todos vienen del mismo `vals`), pero cada empleado puede traer arrastrados
            # campos pendientes distintos de un fallo previo.
            for employee in to_push:
                pending = set(f for f in (employee.personal_data_sync_pending_fields or '').split(',') if f)
                pending.update(changed_personal_fields)
                employee.personal_data_sync_pending_fields = ','.join(sorted(pending))
            # Fuera del `write()` que disparó esto no hay problema en volver a llamar `write()`
            # arriba (marca sync_state) - ya no estamos dentro del `values_before`/vals original.
            to_push._sync_personal_data_to_enterprise()
        return res
