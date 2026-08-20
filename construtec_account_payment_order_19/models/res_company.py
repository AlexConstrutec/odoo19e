import logging

from odoo import api, fields, models

from ..tools.enterprise_sync_api import (
    EnterpriseSyncError, fetch_accounts, fetch_analytic_accounts, fetch_companies,
    fetch_employees, fetch_journals,
)

_logger = logging.getLogger(__name__)

EMPLOYEE_SYNC_CRON_XMLID = 'construtec_account_payment_order_19.ir_cron_employee_sync'


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

    def action_sync_employees_now(self):
        self.ensure_one()
        ok_emp, message_emp = self._sync_employees_from_enterprise()
        ok_analytic, message_analytic = self._sync_analytic_accounts_from_enterprise()
        ok_company, message_company = self._sync_enterprise_companies()
        ok = ok_emp and ok_analytic and ok_company
        message = self.env._(
            'Empleados: %(message_emp)s\nCuentas Analíticas: %(message_analytic)s\n'
            'Compañías: %(message_company)s',
            message_emp=message_emp, message_analytic=message_analytic,
            message_company=message_company)
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
        """Pull name/department/job for active employees and upsert them into hr.employee.

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
        created = updated = 0
        for emp in employees:
            enterprise_ref = str(emp['id'])
            department = False
            if emp.get('department_id'):
                dept_name = emp['department_id'][1]
                department = Department.search(
                    [('name', '=', dept_name), ('company_id', '=', self.id)], limit=1)
                if not department:
                    department = Department.create({'name': dept_name, 'company_id': self.id})
            vals = {
                'name': emp['name'],
                'job_title': emp.get('job_title') or False,
                'department_id': department.id if department else False,
                'cuenta_bancaria_raw': emp.get('acc_number') or False,
                'banco_nombre_raw': emp.get('bank_name') or False,
                'work_phone': emp.get('work_phone') or False,
                'mobile_phone': emp.get('mobile_phone') or False,
                'private_phone': emp.get('private_phone') or False,
                'work_email': emp.get('work_email') or False,
                'private_email': emp.get('private_email') or False,
                'enterprise_employee_ref': enterprise_ref,
                'company_id': self.id,
            }
            existing = Employee.search([('enterprise_employee_ref', '=', enterprise_ref)], limit=1)
            if existing:
                existing.write(vals)
                updated += 1
            else:
                Employee.create(vals)
                created += 1
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
            vals = {
                'name': acc['name'],
                'code': acc.get('code') or False,
                'plan_id': plan.id,
                'company_id': self.id,
                'enterprise_analytic_ref': enterprise_ref,
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

    def action_sync_accounts_journals_now(self):
        self.ensure_one()
        ok_acc, message_acc = self._sync_enterprise_accounts()
        ok_journal, message_journal = self._sync_enterprise_journals()
        ok = ok_acc and ok_journal
        message = self.env._(
            'Cuentas Contables: %(message_acc)s\nDiarios Contables: %(message_journal)s',
            message_acc=message_acc, message_journal=message_journal)
        self._payment_order_sync_log(ok, message)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._('Sincronización de Cuentas/Diarios Contables'),
                'message': message,
                'type': 'success' if ok else 'danger',
                'sticky': not ok,
            },
        }

    def _sync_enterprise_accounts(self):
        """Puebla `account.payment.order.enterprise.account` (usado por `cuenta_contable_id`
        en el catálogo de Tipo de Gasto) - **consciente del rol**, a diferencia de
        empleados/analíticas/compañías (que solo aplican para Solicitante):

        - Procesador (Enterprise): se refleja LOCAL, directo de las cuentas de gasto reales de
          ESTA misma compañía (`self.env.company` - sin RPC, Enterprise ya es la fuente real).
          Necesario porque `cuenta_contable_id` es un solo campo/modelo compartido entre
          ambas ediciones - si solo se poblara en Solicitante, quedaría vacío para siempre en
          Procesador.
        - Solicitante (Community): pull por RPC, acotado a la ÚNICA compañía ya elegida en
          "Compañía por defecto" (`payment_order_default_company_id`) - no tiene sentido traer
          el plan de cuentas de TODAS las compañías de Enterprise para esto."""
        self.ensure_one()
        if self.payment_order_role == 'procesador':
            accounts = self.env['account.account'].sudo().search([
                ('company_ids', 'in', self.id), ('internal_group', '=', 'expense'),
            ])
            return self._upsert_enterprise_accounts(
                [{'id': a.id, 'name': a.name, 'code': a.code} for a in accounts])
        if not self.payment_order_sync_enabled:
            return True, self.env._(
                'Sincronización de Cuentas Contables no aplica (sincronización no configurada).')
        if not self.payment_order_default_company_id:
            return True, self.env._(
                'Sincronización de Cuentas Contables no aplica (defina primero la Compañía '
                'por Defecto en Enterprise).')
        try:
            accounts = fetch_accounts(
                self.payment_order_sync_url, self.payment_order_sync_db,
                self.payment_order_sync_login, self.payment_order_sync_api_key,
                self.payment_order_default_company_id.enterprise_company_ref)
        except EnterpriseSyncError as exc:
            _logger.warning('Sincronización de Cuentas Contables falló para %s: %s', self.name, exc)
            return False, str(exc)
        return self._upsert_enterprise_accounts(accounts)

    def _upsert_enterprise_accounts(self, accounts):
        EnterpriseAccount = self.env['account.payment.order.enterprise.account'].sudo()
        created = updated = 0
        for acc in accounts:
            enterprise_ref = str(acc['id'])
            vals = {'name': acc['name'], 'code': acc.get('code') or False,
                    'enterprise_account_ref': enterprise_ref}
            existing = EnterpriseAccount.search(
                [('enterprise_account_ref', '=', enterprise_ref)], limit=1)
            if existing:
                existing.write(vals)
                updated += 1
            else:
                EnterpriseAccount.create(vals)
                created += 1
        message = self.env._(
            '%(created)s cuentas nuevas, %(updated)s actualizadas.',
            created=created, updated=updated)
        return True, message

    def _sync_enterprise_journals(self):
        """Puebla `account.payment.order.enterprise.journal` - mismo criterio consciente del
        rol que _sync_enterprise_accounts(), solo diarios de banco."""
        self.ensure_one()
        if self.payment_order_role == 'procesador':
            journals = self.env['account.journal'].sudo().search([
                ('company_id', '=', self.id), ('type', '=', 'bank'),
            ])
            return self._upsert_enterprise_journals(
                [{'id': j.id, 'name': j.name, 'code': j.code} for j in journals])
        if not self.payment_order_sync_enabled:
            return True, self.env._(
                'Sincronización de Diarios Contables no aplica (sincronización no configurada).')
        if not self.payment_order_default_company_id:
            return True, self.env._(
                'Sincronización de Diarios Contables no aplica (defina primero la Compañía '
                'por Defecto en Enterprise).')
        try:
            journals = fetch_journals(
                self.payment_order_sync_url, self.payment_order_sync_db,
                self.payment_order_sync_login, self.payment_order_sync_api_key,
                self.payment_order_default_company_id.enterprise_company_ref)
        except EnterpriseSyncError as exc:
            _logger.warning('Sincronización de Diarios Contables falló para %s: %s', self.name, exc)
            return False, str(exc)
        return self._upsert_enterprise_journals(journals)

    def _upsert_enterprise_journals(self, journals):
        EnterpriseJournal = self.env['account.payment.order.enterprise.journal'].sudo()
        created = updated = 0
        for journal in journals:
            enterprise_ref = str(journal['id'])
            vals = {'name': journal['name'], 'code': journal.get('code') or False,
                    'enterprise_journal_ref': enterprise_ref}
            existing = EnterpriseJournal.search(
                [('enterprise_journal_ref', '=', enterprise_ref)], limit=1)
            if existing:
                existing.write(vals)
                updated += 1
            else:
                EnterpriseJournal.create(vals)
                created += 1
        message = self.env._(
            '%(created)s diarios nuevos, %(updated)s actualizados.',
            created=created, updated=updated)
        return True, message

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        companies._apply_employee_sync_interval_to_cron()
        return companies

    def write(self, vals):
        res = super().write(vals)
        if 'employee_sync_interval_number' in vals or 'employee_sync_interval_type' in vals:
            self._apply_employee_sync_interval_to_cron()
        return res

    @api.model
    def _cron_sync_employees_from_enterprise(self):
        companies = self.search([
            ('payment_order_role', '=', 'solicitante'),
            ('payment_order_sync_enabled', '=', True),
        ])
        for company in companies:
            ok, message = company._sync_employees_from_enterprise()
            company._payment_order_sync_log(ok, message)
            ok, message = company._sync_analytic_accounts_from_enterprise()
            company._payment_order_sync_log(ok, message)
            ok, message = company._sync_enterprise_companies()
            company._payment_order_sync_log(ok, message)
