import logging

from odoo import api, fields, models

from ..tools.enterprise_sync_api import (
    EnterpriseSyncError, fetch_analytic_accounts, fetch_companies, fetch_employees,
    fetch_order_status, fetch_partners,
)
from .res_partner import _construtec_tag_names_for

_logger = logging.getLogger(__name__)

EMPLOYEE_SYNC_CRON_XMLID = 'construtec_account_payment_order_19.ir_cron_employee_sync'
PAYMENT_ORDER_STATUS_SYNC_CRON_XMLID = (
    'construtec_account_payment_order_19.ir_cron_payment_order_status_sync')


class ResCompany(models.Model):
    _inherit = 'res.company'

    payment_order_role = fields.Selection([
        ('solicitante', 'Solicitante'),
        ('procesador', 'Procesador'),
    ], string='Rol de Solicitudes de Pago', default='procesador', required=True,
        help='Solicitante: esta instalación captura y aprueba Solicitudes de Pago (ej. Odoo '
             'Community, donde un jefe de técnicos pide viáticos) y las sincroniza hacia la '
             'instalación Procesadora. Procesador: esta instalación recibe Solicitudes ya '
             'aprobadas y las convierte en Órdenes de Pago reales (ej. Odoo Enterprise, donde '
             'Contabilidad revisa y aplica el Anticipo). El valor por defecto (Procesador) deja '
             'el comportamiento actual sin cambios.')

    payment_order_approval_threshold = fields.Monetary(
        string='Umbral de Aprobación Nivel Alto', currency_field='currency_id', default=2500.0,
        help='Solicitudes de Pago con Total a Acreditar mayor o igual a este monto requieren '
             'aprobación de Nivel Alto (Gerente de Área) - ver '
             'group_payment_order_approver_alto/_medio. Montos menores solo requieren Nivel '
             'Medio (Jefe de Área). Nivel Alto siempre puede aprobar cualquier monto. Q2,500.00 '
             'por defecto, según el formulario original en papel.')

    payment_order_habilitar_anticipo = fields.Boolean(
        string='Permitir crear: Anticipo', default=True,
        help='Controla si "Anticipo" aparece como opción al crear una Orden de Pago nueva en '
             'esta compañía. Es un filtro de la lista desplegable del campo Tipo (ver '
             'fields_get() en account_payment_order.py) - NO bloquea la creación programática '
             '(sincronización), solo lo que un usuario ve como opción al llenar el formulario a '
             'mano. Fase 1 del proyecto: deshabilitado en Community, '
             'habilitado en Enterprise.')
    payment_order_habilitar_anticipo_viaticos = fields.Boolean(
        string='Permitir crear: Anticipo Viáticos', default=True,
        help='Igual que Anticipo, para "Anticipo Viáticos". Fase 1: es el único tipo habilitado '
             'en Community. Se deja habilitado por defecto también en Enterprise para que un '
             'Anticipo Viáticos ya sincronizado desde Community se siga mostrando con su '
             'etiqueta normal en el desplegable - deshabilitarlo aquí solo evita que Enterprise '
             'lo ofrezca como opción al crear uno nuevo a mano.')
    payment_order_habilitar_pago_directo = fields.Boolean(
        string='Permitir crear: Pago Directo', default=True,
        help='Igual que Anticipo, para "Pago Directo". Fase 1: deshabilitado en Community, '
             'habilitado en Enterprise.')
    payment_order_habilitar_anticipo_materiales = fields.Boolean(
        string='Permitir crear: Solicitud de Materiales', default=True,
        help='Igual que Anticipo Viáticos, para "Solicitud de Materiales" (tipo técnico '
             '`anticipo_materiales`, sin cambios) - el otro tipo que Community sí debe ver '
             'habilitado (junto con Anticipo Viáticos).')

    payment_order_sync_enabled = fields.Boolean(string='Sincronización de Solicitudes de Pago Habilitada')
    payment_order_sync_url = fields.Char(
        string='URL de la instalación Procesadora',
        help='URL base de la instalación Odoo que procesa las Solicitudes de Pago, '
             'p. ej. https://enterprise.miempresa.com. Use HTTPS en producción.')
    payment_order_sync_db = fields.Char(string='Base de Datos de la instalación Procesadora')
    payment_order_sync_login = fields.Char(
        string='Usuario de Integración en la instalación Procesadora',
        help='Use un usuario de servicio dedicado con permisos mínimos (solo crear Solicitudes '
             'de Pago) en la instalación Procesadora, no un administrador.')
    payment_order_sync_api_key = fields.Char(
        string='API Key de la instalación Procesadora',
        help='API Key generada en la instalación Procesadora para el usuario de integración '
             '(Ajustes > Mi Perfil > Seguridad de la cuenta > Nueva clave API). '
             'No usar la contraseña del usuario.')
    payment_order_sync_log_ids = fields.One2many(
        comodel_name='account.payment.order.sync.log',
        inverse_name='company_id',
        string='Registro de Sincronización de Solicitudes de Pago')

    anthropic_api_key = fields.Char(
        string='Anthropic API Key',
        help='Se usa para extraer datos de cotizaciones de proveedor subidas en la pestaña '
             'Materiales ("Cargar Cotización") - cada extracción tiene un costo real por '
             'llamada. Genere una clave en console.anthropic.com. Solo se usa desde Community '
             '(el botón no aparece en Enterprise).')

    payment_order_default_company_id = fields.Many2one(
        'account.payment.order.enterprise.company', string='Compañía por defecto en Enterprise',
        help='Compañía de la instalación Procesadora a la que caen las Solicitudes de Pago '
             'cuando el empleado solicitante/de la línea no se pudo resolver a un id real de '
             'Enterprise (ej. no está sincronizado todavía) - Enterprise puede tener varias '
             'compañías con empleados contratados en cada una. Cuando el empleado SÍ se '
             'resuelve, se usa la compañía real de ese empleado en vez de este respaldo.')

    employee_sync_interval_number = fields.Integer(
        string='Sincronizar directorio (empleados/cuentas analíticas) cada', default=6,
        help='Cada cuánto se jala desde la instalación Procesadora el directorio de empleados '
             '(nombre/departamento/puesto/cuenta bancaria) y el catálogo de cuentas analíticas '
             '(Proyectos). Solo aplica cuando el rol es Solicitante.')
    employee_sync_interval_type = fields.Selection([
        ('minutes', 'Minutos'),
        ('hours', 'Horas'),
        ('days', 'Días'),
    ], string='Unidad del intervalo', default='hours')

    payment_order_status_sync_interval_number = fields.Integer(
        string='Sincronizar estado de Órdenes de Pago cada', default=1,
        help='Cada cuánto se consulta a la instalación Procesadora el estado real '
             '(Enviado/Aprobado/Rechazado/Aplicado) de las propias Órdenes de Pago ya enviadas '
             '- `_sync_to_enterprise()` solo empuja en un sentido (crea un registro nuevo allá '
             'al Enviar); sin este pull periódico, el registro original se quedaría congelado '
             'en "Enviado" para siempre. Solo aplica cuando el rol es Solicitante. Por defecto '
             'cada 1 hora.')
    payment_order_status_sync_interval_type = fields.Selection([
        ('minutes', 'Minutos'),
        ('hours', 'Horas'),
        ('days', 'Días'),
    ], string='Unidad del intervalo de estado', default='hours')

    def _get_payment_order_allowed_tipos(self):
        """Subconjunto de `tipo` que esta compañía ofrece al crear una Orden de Pago nueva a
        mano (ver AccountPaymentOrder.fields_get()). Deliberadamente NO se usa para validar
        create()/write() - un registro sincronizado debe poder existir siempre, sin importar
        esta configuración."""
        self.ensure_one()
        allowed = []
        if self.payment_order_habilitar_anticipo:
            allowed.append('anticipo')
        if self.payment_order_habilitar_anticipo_viaticos:
            allowed.append('anticipo_viaticos')
        if self.payment_order_habilitar_pago_directo:
            allowed.append('pago_directo')
        if self.payment_order_habilitar_anticipo_materiales:
            allowed.append('anticipo_materiales')
        return allowed

    def _payment_order_sync_log(self, success, message):
        self.ensure_one()
        self.env['account.payment.order.sync.log'].sudo().create(
            {'company_id': self.id, 'success': success, 'message': message})

    def _apply_employee_sync_interval_to_cron(self):
        """Push this company's interval onto the single global sync cron.

        The cron is one record shared by the whole database, not per-company - if more than
        one company here is ever configured as Solicitante with different intervals, the last
        one saved wins. Acceptable for the single-company Community instance this targets
        today; documented in the module's CLAUDE.md as a known limitation.
        """
        self.ensure_one()
        cron = self.env.ref(EMPLOYEE_SYNC_CRON_XMLID, raise_if_not_found=False)
        if cron:
            cron.sudo().write({
                'interval_number': self.employee_sync_interval_number or 6,
                'interval_type': self.employee_sync_interval_type or 'hours',
            })

    def _apply_payment_order_status_sync_interval_to_cron(self):
        """Mismo patrón/limitación que `_apply_employee_sync_interval_to_cron()` (un solo cron
        global, no por compañía) - ver ese docstring."""
        self.ensure_one()
        cron = self.env.ref(PAYMENT_ORDER_STATUS_SYNC_CRON_XMLID, raise_if_not_found=False)
        if cron:
            cron.sudo().write({
                'interval_number': self.payment_order_status_sync_interval_number or 1,
                'interval_type': self.payment_order_status_sync_interval_type or 'hours',
            })

    def _pull_payment_order_status(self):
        """Trae de vuelta el estado real (Enviado/Aprobado/Rechazado/Aplicado/Liquidado) de las
        propias Órdenes de Pago ya enviadas a la instalación Procesadora - `_sync_to_enterprise()`
        es de un solo sentido (crea un registro NUEVO allá al Enviar), así que sin este pull el
        registro original se queda congelado en 'enviado' para siempre, sin enterarse de nada
        de lo que pasó después en Enterprise (aprobación, rechazo, aplicación, liquidación).

        Ni `'aplicado'` NI `'liquidado'` son terminales de verdad - un Anticipo Aplicado en
        Enterprise puede seguir avanzando a `'liquidado'` sobre el mismo registro, Y una
        Liquidación ya hecha puede deshacerse automáticamente si alguien resetea a Borrador una
        factura/pago ya conciliado por fuera de la Orden (ver
        `account.payment.order._reaccionar_a_documento_desconciliado()` - el estado puede
        REGRESAR de `liquidado` a `aplicado`, no solo avanzar). Solo `'rechazado'`/`'cancelado'`
        son terminales de verdad - una Orden en cualquier otro estado sigue consultándose en
        cada corrida, para siempre, precisamente porque ya no se puede asumir que el estado solo
        avanza.

        Empareja por `external_ref` = el propio `name` de esta Orden (guardado del lado de
        Enterprise por `_prepare_sync_vals()`) - nunca por id, son bases de datos distintas.
        Actualiza `state`/`monto`/`reject_reason`/`approve_date`/`reject_date` - un `write()`
        plano, NO se llaman `action_approve()`/`action_reject()`/`action_aplicar()`/
        `action_conciliar()` (esos son para ejecutar la transición AQUÍ; esto solo refleja una
        transición que ya ocurrió allá, sin repetir ningún efecto secundario - crear un pago
        local, disparar sync, etc. - de nuevo).

        `monto` se pull igual que el resto: un Anticipo Aplicado en Enterprise puede tener un
        `monto` distinto al que Community tenía al Enviar (ej. el contable lo ajustó antes de
        Aplicar) - sin esto, `helpdesk.ticket.costo_total` (que suma `payment_order_ids.monto`
        LOCAL, ver `construtec_helpdesk_field_service`) queda con el valor viejo para siempre."""
        self.ensure_one()
        if self.payment_order_role != 'solicitante' or not self.payment_order_sync_enabled:
            return True, self.env._(
                'Sincronización de estado no aplica (rol o sincronización no configurados).')

        pendientes = self.env['account.payment.order'].search([
            ('company_id', '=', self.id),
            ('tipo', 'in', ('anticipo', 'anticipo_viaticos', 'anticipo_materiales', 'pago_directo')),
            ('origin', '=', 'local'),
            ('sync_state', '=', 'synced'),
            ('state', 'not in', ('rechazado', 'cancelado')),
        ])
        if not pendientes:
            return True, self.env._('No hay Órdenes de Pago pendientes de actualizar.')

        try:
            remotos = fetch_order_status(
                self.payment_order_sync_url, self.payment_order_sync_db,
                self.payment_order_sync_login, self.payment_order_sync_api_key,
                pendientes.mapped('name'))
        except EnterpriseSyncError as exc:
            _logger.warning(
                'Sincronización de estado de Órdenes de Pago falló para %s: %s', self.name, exc)
            return False, str(exc)

        por_ref = {r['external_ref']: r for r in remotos if r.get('external_ref')}
        actualizadas = 0
        for orden in pendientes:
            remoto = por_ref.get(orden.name)
            if not remoto:
                continue
            monto_remoto = remoto.get('monto', orden.monto)
            estado_remoto = remoto['state']
            estado_anterior = orden.state
            if estado_remoto == estado_anterior and monto_remoto == orden.monto:
                continue
            orden.write({
                'state': estado_remoto,
                'monto': monto_remoto,
                'reject_reason': remoto.get('reject_reason') or orden.reject_reason,
                'approve_date': remoto.get('approve_date') or orden.approve_date,
                'reject_date': remoto.get('reject_date') or orden.reject_date,
            })
            actualizadas += 1
            # Notifica al solicitante original solo si el ESTADO en sí cambió (no si solo
            # cambió `monto`) - ver AccountPaymentOrder._notify_estado_pull().
            if estado_remoto != estado_anterior:
                orden._notify_estado_pull(estado_remoto)
        message = self.env._(
            '%(actualizadas)s de %(total)s Órdenes de Pago actualizadas.',
            actualizadas=actualizadas, total=len(pendientes))
        return True, message

    def action_pull_payment_order_status_now(self):
        self.ensure_one()
        ok, message = self._pull_payment_order_status()
        self._payment_order_sync_log(ok, message)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._('Sincronización de Estado de Órdenes de Pago'),
                'message': message,
                'type': 'success' if ok else 'danger',
                'sticky': not ok,
            },
        }

    @api.model
    def _cron_pull_payment_order_status(self):
        companies = self.search([
            ('payment_order_role', '=', 'solicitante'),
            ('payment_order_sync_enabled', '=', True),
        ])
        for company in companies:
            ok, message = company._pull_payment_order_status()
            company._payment_order_sync_log(ok, message)

    def action_sync_employees_now(self):
        self.ensure_one()
        ok_emp, message_emp = self._sync_employees_from_enterprise()
        # Contactos ANTES de Cuentas Analíticas: analytic_account.partner_id se resuelve por
        # enterprise_partner_ref, así que la primera pasada ya lo deja correcto en vez de
        # tener que esperar a la siguiente sincronización.
        ok_partners, message_partners = self._sync_partners_from_enterprise()
        ok_analytic, message_analytic = self._sync_analytic_accounts_from_enterprise()
        ok_company, message_company = self._sync_enterprise_companies()
        ok = ok_emp and ok_analytic and ok_company and ok_partners
        message = self.env._(
            'Empleados: %(message_emp)s\nCuentas Analíticas: %(message_analytic)s\n'
            'Compañías: %(message_company)s\nContactos: %(message_partners)s',
            message_emp=message_emp, message_analytic=message_analytic,
            message_company=message_company, message_partners=message_partners)
        self._payment_order_sync_log(ok, message)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._('Sincronización de Directorio'),
                'message': message,
                'type': 'success' if ok else 'danger',
                'sticky': not ok,
            },
        }

    def _sync_employees_from_enterprise(self):
        """Pull name/department/job position/job title for active employees and upsert them
        into hr.employee. `job_id` (hr.job, catálogo formal) se resuelve find-or-create por
        nombre+compañía, mismo criterio que `department_id` - Community termina con los mismos
        Puestos de Trabajo que Enterprise, no solo el texto libre de `job_title`.

        Only meaningful when this company is Solicitante - Procesador companies simply have
        nothing to pull from (they're the source, per explicit product decision: employees
        are only ever created in Enterprise, never in Community).
        """
        self.ensure_one()
        if self.payment_order_role != 'solicitante' or not self.payment_order_sync_enabled:
            return True, self.env._('Sincronización de Empleados no aplica (rol o sincronización '
                                     'no configurados).')
        try:
            employees = fetch_employees(
                self.payment_order_sync_url, self.payment_order_sync_db,
                self.payment_order_sync_login, self.payment_order_sync_api_key)
        except EnterpriseSyncError as exc:
            _logger.warning('Sincronización de Empleados falló para %s: %s', self.name, exc)
            return False, str(exc)

        Employee = self.env['hr.employee'].sudo()
        Department = self.env['hr.department'].sudo()
        Job = self.env['hr.job'].sudo()
        Country = self.env['res.country'].sudo()
        created = updated = 0
        # Mismos nombres que PERSONAL_DATA_FIELDS en hr_employee.py, sin country_id/
        # country_of_birth/municipio_nombre (esos 3 llegan como nacionalidad_code/
        # pais_origen_code/municipio_nombre - ver fetch_employees() - y se resuelven abajo).
        personal_data_direct_fields = (
            'primer_nombre', 'segundo_nombre', 'tercer_nombre', 'primer_apellido', 'segundo_apellido',
            'apellido_casada', 'discapacidad', 'nit', 'igss', 'pueblo_pertenencia', 'comunidad_linguistica',
            'marital', 'sex', 'birthday', 'children', 'identification_id', 'permit_no', 'certificate',
            'study_field',
        )
        for emp in employees:
            enterprise_ref = str(emp['id'])
            department = False
            if emp.get('department_id'):
                dept_name = emp['department_id'][1]
                department = Department.search(
                    [('name', '=', dept_name), ('company_id', '=', self.id)], limit=1)
                if not department:
                    department = Department.create({'name': dept_name, 'company_id': self.id})
            # Puesto de trabajo (hr.job, catálogo formal - no confundir con job_title, el texto
            # libre que ya se sincroniza abajo) - pedido explícito del usuario 2026-09-18: mismo
            # criterio find-or-create por nombre+compañía que ya usa department_id arriba, para
            # que Community tenga los mismos Puestos de Trabajo que Enterprise, no solo el texto.
            job = False
            if emp.get('job_id'):
                job_name = emp['job_id'][1]
                job = Job.search([('name', '=', job_name), ('company_id', '=', self.id)], limit=1)
                if not job:
                    job = Job.create({
                        'name': job_name, 'company_id': self.id,
                        'department_id': department.id if department else False,
                    })
            vals = {
                'name': emp['name'],
                'job_title': emp.get('job_title') or False,
                'job_id': job.id if job else False,
                'department_id': department.id if department else False,
                'cuenta_bancaria_raw': emp.get('acc_number') or False,
                'banco_nombre_raw': emp.get('bank_name') or False,
                'tipo_cuenta_raw': emp.get('tipo_cuenta') or False,
                'work_phone': emp.get('work_phone') or False,
                'mobile_phone': emp.get('mobile_phone') or False,
                'private_phone': emp.get('private_phone') or False,
                'work_email': emp.get('work_email') or False,
                'private_email': emp.get('private_email') or False,
                'enterprise_employee_ref': enterprise_ref,
                'company_id': self.id,
            }
            # `active_test=False`: si este empleado ya se había archivado aquí en una
            # sincronización anterior (ver más abajo), un `search()` normal ya no lo
            # encontraría (por default excluye archivados) - se crearía un DUPLICADO en vez de
            # reconocer al que ya existe.
            existing = Employee.with_context(active_test=False).search(
                [('enterprise_employee_ref', '=', enterprise_ref)], limit=1)

            # Relleno de huecos de "Datos Personales" (2026-09-17) - ver el bug real
            # documentado en hr_employee.py: estos campos, para un empleado que ya existía
            # antes de esta funcionalidad, llegaban en blanco a Community (nunca se hizo un
            # backfill desde Enterprise, que sí tiene los valores reales). Para un empleado
            # NUEVO se cargan todos tal cual (nada que pisar). Para uno EXISTENTE, solo se
            # completa lo que hoy está en blanco en Community - si el usuario ya cargó/editó
            # un valor aquí, esta sincronización nunca lo toca ni lo pisa.
            personal_data_vals = {}
            for f in personal_data_direct_fields:
                value = emp.get(f)
                # Solo se agrega si Enterprise SÍ tiene un valor real - forzar `False` explícito
                # en un `create()` nuevo pisaría el default del propio campo en Odoo (ej.
                # `marital` es NOT NULL a nivel de base de datos en `hr.version` con default
                # 'single' - mandar `False` ahí truena con NotNullViolation en vez de dejar
                # que el propio modelo ponga su default).
                if value and (not existing or not existing[f]):
                    personal_data_vals[f] = value
            if emp.get('nacionalidad_code') and (not existing or not existing.country_id):
                country = Country.search([('code', '=', emp['nacionalidad_code'])], limit=1)
                if country:
                    personal_data_vals['country_id'] = country.id
            if emp.get('pais_origen_code') and (not existing or not existing.country_of_birth):
                country = Country.search([('code', '=', emp['pais_origen_code'])], limit=1)
                if country:
                    personal_data_vals['country_of_birth'] = country.id
            if emp.get('municipio_nombre') and (not existing or not existing.municipio_nombre):
                personal_data_vals['municipio_nombre'] = emp['municipio_nombre']

            # Baja en Enterprise → baja en Community + en el usuario vinculado (2026-09-18,
            # pedido explícito del usuario). `fetch_employees()` ya trae `active` (con
            # `context: active_test=False`, para que un empleado archivado en Enterprise no
            # desaparezca del todo del resultado). Estado laboral sigue siendo dueño Enterprise
            # - esto es solo reflejar esa baja aquí, nunca al revés.
            enterprise_active = emp.get('active', True)
            was_active = existing.active if existing else True

            if existing:
                # `skip_personal_data_push`: este relleno lee de Enterprise, no debe
                # reenviarse a Enterprise como si el usuario lo hubiera editado aquí (ver
                # write() en hr_employee.py). `active_test=False`: necesario para poder
                # reactivar un registro que hoy está archivado - un write() normal sobre un
                # registro archivado igual funciona, pero mantiene el mismo contexto ya usado
                # arriba para encontrarlo.
                employee_record = existing
                employee_record.with_context(skip_personal_data_push=True, active_test=False).write(
                    {**vals, **personal_data_vals})
                updated += 1
            else:
                employee_record = Employee.create({**vals, **personal_data_vals})
                created += 1

            if was_active and not enterprise_active:
                employee_record.action_archive()
                if employee_record.user_id:
                    employee_record.user_id.sudo().action_archive()
            elif not was_active and enterprise_active:
                employee_record.action_unarchive()
                if employee_record.user_id:
                    employee_record.user_id.sudo().action_unarchive()
        message = self.env._(
            '%(created)s empleados nuevos, %(updated)s actualizados.',
            created=created, updated=updated)
        return True, message

    def _sync_analytic_accounts_from_enterprise(self):
        """Pull the analytic account catalog (used as "Proyecto" in Solicitudes de Pago) and
        upsert it into account.analytic.account. Same shape as _sync_employees_from_enterprise -
        no-op unless Solicitante + sync enabled, find-or-create the plan by name (never by id)."""
        self.ensure_one()
        if self.payment_order_role != 'solicitante' or not self.payment_order_sync_enabled:
            return True, self.env._('Sincronización de Cuentas Analíticas no aplica (rol o '
                                     'sincronización no configurados).')
        try:
            accounts = fetch_analytic_accounts(
                self.payment_order_sync_url, self.payment_order_sync_db,
                self.payment_order_sync_login, self.payment_order_sync_api_key)
        except EnterpriseSyncError as exc:
            _logger.warning('Sincronización de Cuentas Analíticas falló para %s: %s', self.name, exc)
            return False, str(exc)

        AnalyticAccount = self.env['account.analytic.account'].sudo()
        AnalyticPlan = self.env['account.analytic.plan'].sudo()
        created = updated = 0
        for acc in accounts:
            enterprise_ref = str(acc['id'])
            plan = False
            if acc.get('plan_id'):
                plan_name = acc['plan_id'][1]
                plan = AnalyticPlan.search([('name', '=', plan_name)], limit=1)
                if not plan:
                    plan = AnalyticPlan.create({'name': plan_name})
            if not plan:
                # plan_id es obligatorio en account.analytic.account - sin plan de origen,
                # se agrupa en un plan generico en vez de fallar la sincronizacion completa.
                plan = AnalyticPlan.search([('name', '=', 'Proyectos (sin plan de origen)')], limit=1)
                if not plan:
                    plan = AnalyticPlan.create({'name': 'Proyectos (sin plan de origen)'})
            partner = self.env['res.partner']
            if acc.get('partner_id'):
                partner = self.env['res.partner'].sudo().search(
                    [('enterprise_partner_ref', '=', acc['partner_id'][0])], limit=1)
            vals = {
                'name': acc['name'],
                'code': acc.get('code') or False,
                'plan_id': plan.id,
                'partner_id': partner.id or False,
                'company_id': self.id,
                'enterprise_analytic_ref': enterprise_ref,
                'disponible_tickets': bool(acc.get('disponible_tickets')),
            }
            existing = AnalyticAccount.search(
                [('enterprise_analytic_ref', '=', enterprise_ref)], limit=1)
            if existing:
                existing.write(vals)
                updated += 1
            else:
                AnalyticAccount.create(vals)
                created += 1
        message = self.env._(
            '%(created)s cuentas analíticas nuevas, %(updated)s actualizadas.',
            created=created, updated=updated)
        return True, message

    def _sync_enterprise_companies(self):
        """Pull la lista de compañías de la instalación Procesadora, para el desplegable
        "Compañía por defecto" (respaldo cuando una Solicitud no trae un empleado resoluble).
        Igual patrón que empleados/cuentas analíticas."""
        self.ensure_one()
        if self.payment_order_role != 'solicitante' or not self.payment_order_sync_enabled:
            return True, self.env._('Sincronización de Compañías no aplica (rol o '
                                     'sincronización no configurados).')
        try:
            companies = fetch_companies(
                self.payment_order_sync_url, self.payment_order_sync_db,
                self.payment_order_sync_login, self.payment_order_sync_api_key)
        except EnterpriseSyncError as exc:
            _logger.warning('Sincronización de Compañías falló para %s: %s', self.name, exc)
            return False, str(exc)

        EnterpriseCompany = self.env['account.payment.order.enterprise.company'].sudo()
        created = updated = 0
        for comp in companies:
            enterprise_ref = str(comp['id'])
            vals = {'name': comp['name'], 'enterprise_company_ref': enterprise_ref}
            existing = EnterpriseCompany.search(
                [('enterprise_company_ref', '=', enterprise_ref)], limit=1)
            if existing:
                existing.write(vals)
                updated += 1
            else:
                EnterpriseCompany.create(vals)
                created += 1
        message = self.env._(
            '%(created)s compañías nuevas, %(updated)s actualizadas.',
            created=created, updated=updated)
        return True, message

    def _sync_partners_from_enterprise(self):
        """Pull de los contactos que ya son Clientes/Proveedores reales en Enterprise - upsert
        por `enterprise_partner_ref`, igual patrón que empleados/cuentas analíticas. Las
        etiquetas (`category_id`) se derivan de `customer_rank`/`es_proveedor_sat` YA recibidos
        en el payload - nunca se recalculan localmente.

        **Proveedor se resuelve por NIT ya conocido AQUÍ, en Community** (vía el propio mirror de
        Documentos SAT, `construtec.sat.invoice.mirror` - `construtec_sat_catalog_sync_19`), no
        preguntándole a Enterprise "quién es proveedor" contra una tabla que Community no
        controla - corrección explícita del usuario (2026-09-29): "los contactos de proveedores
        en Community se filtran porque tienen una factura de proveedor en Community... estas
        facturas de proveedor de Community son los documentos SAT de Enterprise". Se manda la
        lista de NITs ya sincronizados (`partner_vat`, distintos, no vacíos) a `fetch_partners()`
        para que Enterprise resuelva los contactos reales por NIT.

        **Orden real, no garantizado por diseño**: esta sincronización de Contactos corre bajo
        `payment_order_sync_enabled` (este módulo), mientras que el mirror de Documentos SAT
        corre bajo `materials_catalog_sync_enabled` (`construtec_sat_catalog_sync_19`) - dos
        toggles/crons independientes. Si el mirror de Documentos SAT todavía no se ha poblado la
        primera vez, esta corrida simplemente no encuentra ningún NIT de proveedor (mismo
        criterio de auto-sanación ya usado en el resto de este módulo - la siguiente corrida, una
        vez que el mirror ya tenga datos, lo resuelve solo)."""
        self.ensure_one()
        if self.payment_order_role != 'solicitante' or not self.payment_order_sync_enabled:
            return True, self.env._('Sincronización de Contactos no aplica (rol o '
                                     'sincronización no configurados).')
        proveedor_vats = self.env['construtec.sat.invoice.mirror'].sudo().search(
            [('partner_vat', '!=', False)]).mapped('partner_vat')
        try:
            partners = fetch_partners(
                self.payment_order_sync_url, self.payment_order_sync_db,
                self.payment_order_sync_login, self.payment_order_sync_api_key, proveedor_vats)
        except EnterpriseSyncError as exc:
            _logger.warning('Sincronización de Contactos falló para %s: %s', self.name, exc)
            return False, str(exc)

        Partner = self.env['res.partner'].sudo()
        Category = self.env['res.partner.category'].sudo()
        created = updated = 0
        for p in partners:
            enterprise_ref = p['id']
            category_names = _construtec_tag_names_for(
                p.get('customer_rank'), p.get('es_proveedor_sat'), False)
            categories = Category.browse()
            for name in category_names:
                category = Category.search([('name', '=', name)], limit=1)
                if not category:
                    category = Category.create({'name': name})
                categories |= category
            vals = {
                'name': p['name'],
                'email': p.get('email') or False,
                'phone': p.get('phone') or False,
                'vat': p.get('vat') or False,
                'street': p.get('street') or False,
                'city': p.get('city') or False,
                'is_company': bool(p.get('is_company')),
                'category_id': [(4, cat_id) for cat_id in categories.ids],
                'enterprise_partner_ref': enterprise_ref,
                'company_id': self.id,
            }
            existing = Partner.search([('enterprise_partner_ref', '=', enterprise_ref)], limit=1)
            if existing:
                existing.write(vals)
                updated += 1
            else:
                Partner.create(vals)
                created += 1
        message = self.env._(
            '%(created)s contactos nuevos, %(updated)s actualizados.',
            created=created, updated=updated)
        return True, message

    _MATERIALS_CATALOG_SYNC_CREDENTIAL_FIELDS = (
        'payment_order_sync_url', 'payment_order_sync_db',
        'payment_order_sync_login', 'payment_order_sync_api_key')

    def _sync_materials_catalog_credentials(self):
        """Reutiliza tal cual las credenciales de Enterprise ya configuradas para Solicitudes
        de Pago (`payment_order_sync_*`) como las de `construtec_sat_catalog_sync_19`
        (`materials_catalog_sync_*`) - pedido explícito del usuario: "utiliza las mismas
        credenciales que ya están para sincronizar solicitudes de pago, es al mismo Odoo".
        Ambos pulls (empleados/cuentas analíticas/estado de Órdenes de Pago, y el Catálogo de
        Materiales) hablan con la MISMA instalación Enterprise - no hay ninguna razón real para
        pedirle al usuario la misma URL/base de datos/usuario/API Key dos veces. `write()` en
        `super()` para no volver a disparar este mismo método en cascada."""
        for company in self:
            super(ResCompany, company).write({
                'materials_catalog_sync_url': company.payment_order_sync_url,
                'materials_catalog_sync_db': company.payment_order_sync_db,
                'materials_catalog_sync_login': company.payment_order_sync_login,
                'materials_catalog_sync_api_key': company.payment_order_sync_api_key,
            })

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        companies._apply_employee_sync_interval_to_cron()
        companies._apply_payment_order_status_sync_interval_to_cron()
        if any(f in vals for vals in vals_list for f in self._MATERIALS_CATALOG_SYNC_CREDENTIAL_FIELDS):
            companies._sync_materials_catalog_credentials()
        return companies

    def write(self, vals):
        res = super().write(vals)
        if 'employee_sync_interval_number' in vals or 'employee_sync_interval_type' in vals:
            self._apply_employee_sync_interval_to_cron()
        if ('payment_order_status_sync_interval_number' in vals
                or 'payment_order_status_sync_interval_type' in vals):
            self._apply_payment_order_status_sync_interval_to_cron()
        if any(f in vals for f in self._MATERIALS_CATALOG_SYNC_CREDENTIAL_FIELDS):
            self._sync_materials_catalog_credentials()
        return res

    def action_sync_materials_catalog_now(self):
        """Antes de sincronizar, refresca `materials_catalog_sync_*` desde `payment_order_sync_*`
        - necesario para una compañía cuyas credenciales de Solicitudes de Pago ya estaban
        guardadas ANTES de que existiera este espejo (`write()` solo lo dispara cuando esos 4
        campos cambian de valor, así que una compañía ya configurada nunca lo disparó por sí
        sola). Bug real reportado en producción: el botón fallaba con "falta URL, base de
        datos, usuario o API Key" pese a que Solicitudes de Pago ya tenía las 4 credenciales
        correctas - este refresco explícito lo resuelve sin depender de un script de
        migración."""
        self.ensure_one()
        self._sync_materials_catalog_credentials()
        return super().action_sync_materials_catalog_now()

    @api.model
    def _cron_sync_employees_from_enterprise(self):
        companies = self.search([
            ('payment_order_role', '=', 'solicitante'),
            ('payment_order_sync_enabled', '=', True),
        ])
        for company in companies:
            company._sync_materials_catalog_credentials()
            ok, message = company._sync_employees_from_enterprise()
            company._payment_order_sync_log(ok, message)
            # Contactos antes de Cuentas Analíticas - ver nota en action_sync_employees_now().
            ok, message = company._sync_partners_from_enterprise()
            company._payment_order_sync_log(ok, message)
            ok, message = company._sync_analytic_accounts_from_enterprise()
            company._payment_order_sync_log(ok, message)
            ok, message = company._sync_enterprise_companies()
            company._payment_order_sync_log(ok, message)
