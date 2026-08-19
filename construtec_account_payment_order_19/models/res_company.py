import logging

from odoo import api, fields, models

from ..tools.enterprise_sync_api import EnterpriseSyncError, fetch_analytic_accounts, fetch_employees

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
        ok = ok_emp and ok_analytic
        message = self.env._(
            'Empleados: %(message_emp)s\nCuentas Analíticas: %(message_analytic)s',
            message_emp=message_emp, message_analytic=message_analytic)
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
                'telefono_trabajo': emp.get('work_phone') or False,
                'celular_trabajo': emp.get('mobile_phone') or False,
                'telefono_personal_raw': emp.get('private_phone') or False,
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
