import logging

from odoo import api, fields, models

from ..tools.enterprise_sync_api import EnterpriseSyncError, create_analytic_account_in_enterprise

_logger = logging.getLogger(__name__)


class AccountAnalyticAccount(models.Model):
    _inherit = 'account.analytic.account'

    enterprise_analytic_ref = fields.Char(
        string='Referencia de Cuenta Analítica en Enterprise', readonly=True, copy=False,
        index=True,
        help='Id de la cuenta analítica en la instalación Enterprise de origen (o, si esta '
             'cuenta se creó aquí y se empujó hacia allá, el id que Enterprise le asignó al '
             'recibirla - ver _create_analytic_account_in_enterprise()). Uso técnico interno '
             'para no duplicar el registro en cada sincronización.')
    disponible_tickets = fields.Boolean(
        string='Disponible para Tickets', default=False,
        help='Si está marcado, esta Cuenta Analítica aparece como opción de "Ubicación" al '
             'crear un Ticket en Community (construtec_helpdesk_field_service) - un filtro '
             'para que el operador solo vea las cuentas que de verdad representan una '
             'ubicación de servicio, no cualquier cuenta analítica del catálogo (proyectos '
             'internos, cuentas de otro uso, etc.). Viaja hacia Community igual que el resto '
             'de esta sincronización (ver _sync_analytic_accounts_from_enterprise() en '
             'res_company.py) - se edita aquí, nunca en Community.')

    analytic_sync_state = fields.Selection(
        [('pendiente', 'Pendiente'), ('enviado', 'Enviado'), ('error', 'Error')],
        string='Sincronización a Enterprise', copy=False,
        help='Solo aplica a cuentas analíticas creadas aquí en Community (sin '
             '`enterprise_analytic_ref` al momento de crearse) - una cuenta que llegó por el '
             'pull normal (`_sync_analytic_accounts_from_enterprise()`) ya trae su referencia '
             'desde el principio y nunca pasa por aquí.')
    analytic_sync_error = fields.Char(string='Detalle del Error de Sincronización', copy=False)

    def _create_analytic_account_in_enterprise(self):
        """Empuja hacia Enterprise una cuenta analítica creada aquí en Community - pedido
        explícito del usuario (2026-09-30): "si alguien crea una cuenta analítica en Community,
        que automáticamente se sincronice hasta Enterprise" - invierte, para este caso puntual,
        la regla histórica de que las cuentas analíticas "siempre se crean en Enterprise, nunca
        aquí". Mismo patrón que `hr.employee._create_employee_in_enterprise()`: manda un
        snapshot completo (nada que pisar del otro lado, el registro no existe todavía allá).

        `plan_name` viaja como NOMBRE (nunca id, mismo criterio de siempre en este módulo para
        `plan_id` en la dirección Enterprise→Community) - Enterprise busca-o-crea el plan por
        nombre. `partner_id` viaja como el id REAL en Enterprise
        (`partner_id.enterprise_partner_ref`) si ese contacto ya se sincronizó; si no, se manda
        vacío y la cuenta queda sin cliente asignado del lado de Enterprise (corregible a mano
        allá, o se resuelve solo en una futura edición si se construye ese camino)."""
        company = self.env.company
        if company.payment_order_role != 'solicitante' or not company.payment_order_sync_enabled:
            return
        for account in self:
            vals = {
                'name': account.name,
                'code': account.code or False,
                'plan_name': account.plan_id.name or False,
                'partner_ref': account.partner_id.enterprise_partner_ref or False,
                'disponible_tickets': account.disponible_tickets,
            }
            try:
                new_ref = create_analytic_account_in_enterprise(
                    company.payment_order_sync_url, company.payment_order_sync_db,
                    company.payment_order_sync_login, company.payment_order_sync_api_key, vals)
            except EnterpriseSyncError as exc:
                _logger.warning(
                    'Error creando la cuenta analítica %s en Enterprise: %s', account.id, exc)
                account.write({'analytic_sync_state': 'error', 'analytic_sync_error': str(exc)})
            else:
                account.write({
                    'enterprise_analytic_ref': str(new_ref),
                    'analytic_sync_state': 'enviado', 'analytic_sync_error': False,
                })

    def action_retry_analytic_sync(self):
        self.filtered(
            lambda a: a.analytic_sync_state == 'error')._create_analytic_account_in_enterprise()

    @api.model
    def _cron_retry_analytic_sync(self):
        self.search([('analytic_sync_state', '=', 'error')])._create_analytic_account_in_enterprise()

    @api.model_create_multi
    def create(self, vals_list):
        """La señal para distinguir un alta GENUINA (hecha a mano, o por cualquier otro código
        de Community) de un espejo que `_sync_analytic_accounts_from_enterprise()` acaba de
        traer es la misma que ya usa `hr.employee.create()`: el espejo SIEMPRE incluye
        `enterprise_analytic_ref` en su propio `vals` (es justo el id que ya tiene del otro
        lado) - un alta nueva nunca lo trae, porque todavía no existe en ningún lado más que
        aquí."""
        records = super().create(vals_list)
        to_push = self.browse()
        for vals, record in zip(vals_list, records):
            if not vals.get('enterprise_analytic_ref'):
                to_push |= record
        to_push._create_analytic_account_in_enterprise()
        return records

    # Campos que `create_analytic_account_from_community()` acepta - una fuga de la API Key de
    # integración nunca puede crear una cuenta analítica con más que esto.
    ANALYTIC_ACCOUNT_FROM_COMMUNITY_ALLOWED_FIELDS = (
        'name', 'code', 'plan_name', 'partner_ref', 'disponible_tickets')

    def create_analytic_account_from_community(self, vals):
        """Método whitelisted, llamado vía JSON-RPC desde una instalación Solicitante (ver
        `create_analytic_account_in_enterprise()` en `tools/enterprise_sync_api.py`) para crear
        una cuenta analítica NUEVA aquí a partir de una creada en Community.

        `plan_name` se resuelve busca-o-crea por nombre (mismo criterio que
        `_sync_analytic_accounts_from_enterprise()` usa en la dirección contraria) - si no viene,
        cae en el mismo plan genérico "Proyectos (sin plan de origen)". `partner_ref` es el id
        REAL de un `res.partner` en ESTA base (Enterprise) - se resuelve directo por `browse()`,
        sin buscar por nombre, ya que Community solo lo manda cuando el contacto ya se
        sincronizó y por lo tanto ya conoce ese id real."""
        clean_vals = {k: v for k, v in (vals or {}).items()
                      if k in self.ANALYTIC_ACCOUNT_FROM_COMMUNITY_ALLOWED_FIELDS and v}
        if not clean_vals.get('name'):
            raise ValueError('Falta el nombre de la cuenta analítica.')
        plan_name = clean_vals.pop('plan_name', None)
        partner_ref = clean_vals.pop('partner_ref', None)

        Plan = self.env['account.analytic.plan'].sudo()
        plan = Plan.search([('name', '=', plan_name)], limit=1) if plan_name else Plan.browse()
        if not plan:
            plan = Plan.search([('name', '=', 'Proyectos (sin plan de origen)')], limit=1)
        if not plan:
            plan = Plan.create({'name': plan_name or 'Proyectos (sin plan de origen)'})
        clean_vals['plan_id'] = plan.id

        if partner_ref:
            partner = self.env['res.partner'].sudo().browse(int(partner_ref)).exists()
            if partner:
                clean_vals['partner_id'] = partner.id

        account = self.sudo().create(clean_vals)
        return account.id
