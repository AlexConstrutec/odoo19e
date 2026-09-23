import logging

from odoo import api, fields, models

from .account_payment_order import _resolve_employee_for_partner
from ..tools.enterprise_sync_api import EnterpriseSyncError, create_partner_in_enterprise

_logger = logging.getLogger(__name__)

CATEGORIA_EMPLEADOS = 'Empleados'
CATEGORIA_PROVEEDORES = 'Proveedores'
CATEGORIA_CLIENTES = 'Clientes'


def _construtec_tag_names_for(customer_rank, supplier_rank, is_employee):
    """Nombres de `res.partner.category` que le tocan a un contacto, derivados 100% de
    campos nativos de Odoo - nunca etiquetado manual (decisión explícita del usuario,
    2026-09-03). Un contacto puede calificar para más de uno a la vez (ej. un empleado que
    también es proveedor). Reutilizada tanto por `ResPartner._apply_construtec_tags()`
    (Enterprise, sobre sus propios contactos) como por `res.company._sync_partners_from_
    enterprise()` (Community, sobre los valores YA recibidos en el payload del pull - nunca
    se recalculan localmente ahí, `customer_rank`/`supplier_rank` locales de Community no
    significan nada real)."""
    names = []
    if is_employee:
        names.append(CATEGORIA_EMPLEADOS)
    if customer_rank and customer_rank > 0:
        names.append(CATEGORIA_CLIENTES)
    if supplier_rank and supplier_rank > 0:
        names.append(CATEGORIA_PROVEEDORES)
    return names


class ResPartner(models.Model):
    _inherit = 'res.partner'

    enterprise_partner_ref = fields.Integer(
        string='ID en Enterprise', index=True,
        help='El id real de este contacto en Enterprise - clave de upsert usada por '
             '_sync_partners_from_enterprise() (res.company). NUNCA un id local de este '
             'registro en Community - no confundir con el id propio de este registro. Vacío '
             'en cualquier contacto que no llegó por esa sincronización (la inmensa mayoría '
             'en Enterprise, donde este campo nunca se usa).')

    partner_sync_state = fields.Selection(
        [('pendiente', 'Pendiente'), ('enviado', 'Enviado'), ('error', 'Error')],
        string='Sincronización a Enterprise', copy=False,
        help='Solo aplica a contactos creados aquí explícitamente para sincronizarse hacia '
             'Enterprise (ej. desde "Crear Contacto" en la interfaz de chat del Contact '
             'Center, ver construtec_contact_center_base_19::action_create_contact()) - un '
             'contacto normal creado a mano en Contactos se queda sin valor aquí, nunca se '
             'empuja solo (a diferencia de hr.employee, que si sincroniza cualquier alta).')
    partner_sync_error = fields.Char(string='Detalle del Error de Sincronización', copy=False)

    def _push_new_partner_to_enterprise(self):
        """Crea este contacto (que todavía NO existe en Enterprise - sin `enterprise_partner_ref`)
        allá. A diferencia de `hr.employee._create_employee_in_enterprise()` (que sincroniza
        CUALQUIER alta de empleado), esto nunca se llama automáticamente desde `create()` - un
        contacto se crea por muchísimos motivos normales en Odoo (proveedores, direcciones de
        entrega, contactos de prueba) y no todos deben viajar a Enterprise. Los llamadores
        explícitos (ej. `contact.conversation.action_create_contact()`) deciden cuándo
        corresponde.

        Manda solo `name`/`phone` - un contacto que llega por este camino (ej. desde una
        conversación de WhatsApp) no tiene más datos que esos todavía; el resto se completa a
        mano en Enterprise después, igual que cualquier otro contacto nuevo. NUNCA `mobile` -
        `res.partner` en este Odoo 19 no tiene ese campo (solo `phone`), mismo gotcha ya
        documentado en este módulo para `hr.employee`/`res.partner.mobile`."""
        self.ensure_one()
        company = self.env.company
        if company.payment_order_role != 'solicitante' or not company.payment_order_sync_enabled:
            return
        vals = {'name': self.name, 'phone': self.phone or False}
        try:
            new_ref = create_partner_in_enterprise(
                company.payment_order_sync_url, company.payment_order_sync_db,
                company.payment_order_sync_login, company.payment_order_sync_api_key, vals)
        except EnterpriseSyncError as exc:
            _logger.warning('Error creando el contacto %s en Enterprise: %s', self.id, exc)
            self.write({'partner_sync_state': 'error', 'partner_sync_error': str(exc)})
        else:
            self.write({
                'enterprise_partner_ref': new_ref,
                'partner_sync_state': 'enviado', 'partner_sync_error': False,
            })

    def action_retry_partner_sync(self):
        self.filtered(lambda p: p.partner_sync_state == 'error')._push_new_partner_to_enterprise()

    @api.model
    def _cron_retry_partner_sync(self):
        self.search([
            ('partner_sync_state', '=', 'error'),
            ('company_id.payment_order_role', '=', 'solicitante'),
        ])._push_new_partner_to_enterprise()

    # Campos que `create_partner_from_community()` acepta - una fuga de la API Key de
    # integración nunca puede crear un contacto con más que esto (ej. asignarle rangos de
    # cliente/proveedor "reales" con permisos de facturación, o vincularlo a otra compañía).
    PARTNER_FROM_COMMUNITY_ALLOWED_FIELDS = ('name', 'phone')

    def create_partner_from_community(self, vals):
        """Método whitelisted, llamado vía XML-RPC desde una instalación Solicitante (ver
        `create_partner_in_enterprise()` en `tools/enterprise_sync_api.py`) para crear un
        contacto NUEVO aquí a partir de uno creado en Community (ej. "Crear Contacto" desde
        una conversación de WhatsApp del Contact Center, sin equivalente todavía en ese
        contacto del lado de Enterprise).

        Solo acepta los campos de `PARTNER_FROM_COMMUNITY_ALLOWED_FIELDS` - cualquier otra
        clave en `vals` se ignora en silencio, mismo criterio que `create_employee_from_community`
        (Enterprise, `construtec_hr_employee_19`) para su propia lista blanca. Fuerza
        `customer_rank=1` del lado del servidor (nunca confía en lo que mande el llamador) -
        un contacto que escribe por WhatsApp es, por definición de este flujo, un prospecto/
        cliente, así que se etiqueta "Clientes" de inmediato vía `_apply_construtec_tags()`."""
        clean_vals = {k: v for k, v in (vals or {}).items()
                      if k in self.PARTNER_FROM_COMMUNITY_ALLOWED_FIELDS and v}
        if not clean_vals.get('name'):
            raise ValueError('Falta el nombre del contacto.')
        clean_vals['customer_rank'] = 1
        partner = self.sudo().create(clean_vals)
        partner._apply_construtec_tags()
        return partner.id

    def _apply_construtec_tags(self):
        """Autoetiquetado local (Empleados/Proveedores/Clientes) desde campos nativos -
        idempotente y ADITIVO ÚNICAMENTE: nunca quita una etiqueta ya puesta, ni siquiera si
        el contacto deja de calificar después (ej. customer_rank vuelve a 0) - simplificación
        aceptada explícitamente, ver el plan de esta feature. Corre en ambas ediciones sin
        distinción de rol (mismo criterio ya documentado en este módulo para Solicitante/
        Procesador) - en Community, los contactos locales normalmente tienen customer_rank=0,
        así que esto es esencialmente no-op salvo para contactos creados a mano ahí."""
        Category = self.env['res.partner.category'].sudo()
        for partner in self:
            names = _construtec_tag_names_for(
                partner.customer_rank, partner.supplier_rank, partner.employee)
            if not names:
                continue
            existing_names = set(partner.category_id.mapped('name'))
            missing = [name for name in names if name not in existing_names]
            if not missing:
                continue
            categories = Category.browse()
            for name in missing:
                category = Category.search([('name', '=', name)], limit=1)
                if not category:
                    category = Category.create({'name': name})
                categories |= category
            partner.write({'category_id': [(4, cat.id) for cat in categories]})

    @api.model
    def _cron_apply_construtec_tags(self):
        self.sudo().search([])._apply_construtec_tags()

    # No se crea un campo nuevo para el puesto - `function` ("Job Position") ya existe de serie
    # en res.partner (base) y está disponible tanto en Community como en Enterprise. Se
    # redeclara aquí con compute+store para que se autocomplete desde el hr.employee vinculado;
    # `readonly=False` (mismo patrón que `crm.lead.function`, ver `..\odoo\addons\crm\models\
    # crm_lead.py`) para que un usuario todavía pueda corregirlo a mano si hiciera falta - solo
    # se recalcula cuando cambia una dependencia real (el hr.employee vinculado), nunca pisa un
    # valor manual de un contacto que NO es empleado (employee_ids vacío nunca dispara el compute).
    function = fields.Char(compute='_compute_employee_job_info', compute_sudo=True, store=True,
                            readonly=False)
    employee_department_id = fields.Many2one(
        'hr.department', string='Departamento (Empleado)', compute='_compute_employee_job_info',
        compute_sudo=True, store=True,
        help='Heredado automáticamente del hr.employee vinculado (ver '
             '_resolve_employee_for_partner en account_payment_order.py) - se guarda '
             'aquí, en el Contacto, para que exista incluso donde no se pueda resolver un '
             'hr.employee en vivo (ej. Community, que solo tiene un espejo limitado). Si este '
             'contacto es empleado en más de una compañía, se usa el mismo criterio de '
             'desempate: el hr.employee de la compañía ACTUAL (self.env.company), o si no hay '
             'match, el primero activo - un solo valor por contacto, no uno por compañía '
             '(decisión explícita del usuario: la mayoría de contactos solo tiene un empleo). '
             'No hay un campo nativo de "departamento" en res.partner para reusar - a '
             'diferencia de `function`, este sí es un campo nuevo de este módulo.')

    @api.depends('employee_ids.department_id', 'employee_ids.job_title', 'employee_ids.company_id')
    def _compute_employee_job_info(self):
        """Mismo patrón que `crm.lead._compute_function()` (Odoo core, `..\\odoo\\addons\\crm\\
        models\\crm_lead.py`) para un compute+store+readonly=False: solo pisa `function` si el
        contacto todavía no tenía nada, o si el empleado sí trae un puesto - nunca borra un
        valor puesto a mano en un contacto que dejó de tener empleado. Un contacto que nunca
        tuvo hr.employee vinculado (`employee_ids` vacío, la inmensa mayoría) nunca entra por
        aquí con un `employee` real, así que su `function` jamás se toca."""
        for partner in self:
            employee = _resolve_employee_for_partner(partner, self.env.company)
            partner.employee_department_id = employee.department_id
            if not partner.function or employee.job_title:
                partner.function = employee.job_title or partner.function
