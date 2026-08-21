from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from ..tools.enterprise_sync_api import EnterpriseSyncError, create_sync_record

APPROVER_GROUP_XMLID = 'construtec_account_payment_order_19.group_payment_order_approver'
APPROVER_MEDIO_GROUP_XMLID = 'construtec_account_payment_order_19.group_payment_order_approver_medio'
APPROVER_ALTO_GROUP_XMLID = 'construtec_account_payment_order_19.group_payment_order_approver_alto'
# Ambos comparten el mismo ciclo enviado/aprobado/rechazado/aplicado (decisión explícita del
# usuario: "ambos tipos comparten el mismo flujo") - `anticipo_viaticos` es el único que se ve
# en Community (trae viaticos_line_ids/sync/etc.); `anticipo` a secas sigue existiendo para un
# anticipo que un contable arma directo en Enterprise, sin relación a viáticos.
ANTICIPO_TIPOS = ('anticipo', 'anticipo_viaticos')


def _resolve_employee_for_partner(partner, company):
    """Resuelve el hr.employee real detrás de un contacto (res.partner) elegido en
    `partner_id` - compartido entre encabezado y línea para no duplicar el criterio
    de desempate.

    Se usa `partner.sudo().employee_ids` (campo nativo de Odoo, `res.partner.employee_ids`,
    `One2many('hr.employee', 'work_contact_id')`) a propósito: el picker del formulario
    filtra por `res.partner.employee` (también nativo, Boolean guardado - ya evita chocar con
    la regla multiempresa de hr.employee porque el propio contacto NO está restringido por
    compañía), y aquí, ya elegido el contacto, sí necesitamos leer sus hr.employee reales
    (sudo(): un solicitante normal no tiene por qué tener el grupo hr.group_hr_user que exige
    `employee_ids` de forma nativa).

    Desempate si el contacto está contratado en más de una compañía (decisión confirmada con
    el usuario): se prefiere el hr.employee de la MISMA compañía que la Orden de Pago/línea; si
    no hay ninguno ahí, se cae al primer empleado activo."""
    if not partner:
        return partner.env['hr.employee']
    employees = partner.sudo().employee_ids
    if company:
        same_company = employees.filtered(lambda e: e.company_id == company)
        if same_company:
            return same_company[0]
    return employees.filtered(lambda e: e.active)[:1] or employees[:1]


class AccountPaymentOrder(models.Model):
    _name = 'account.payment.order'
    _description = 'Orden de Pago (Anticipo / Liquidación / Pago Directo)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fecha desc'

    tipo = fields.Selection([
        ('anticipo', 'Anticipo'),
        ('anticipo_viaticos', 'Anticipo Viáticos'),
        ('liquidacion', 'Liquidación'),
        ('pago_directo', 'Pago Directo'),
    ], string='Tipo', required=True, default='anticipo')
    name = fields.Char(string='Nombre', compute='_compute_name', store=True, readonly=False)
    no_liquidacion = fields.Integer(string='No. Liquidación')
    fecha = fields.Date(string='Fecha', required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one(
        'account.journal', string='Diario',
        help='Para Liquidación/Pago Directo se exige siempre (ver `_check_journal_id()`). Para '
             'Anticipo, deliberadamente NO es obligatorio al crear - lo llena el contable '
             'DESPUÉS de Aprobar (fusión Solicitud+Anticipo: ya no hay un Wizard "Crear '
             'Anticipo" que lo pida en un paso aparte) - se exige en cambio dentro de '
             '`action_aplicar()`.')
    company_id = fields.Many2one('res.company', string='Compañía', required=True,
                                  default=lambda self: self.env.company.id)
    user_id = fields.Many2one('res.users', string='Usuario', default=lambda self: self.env.user.id)
    partner_id = fields.Many2one(
        'res.partner', string='Contacto',
        default=lambda self: self.env['hr.employee'].search(
            [('user_id', '=', self.env.user.id)], limit=1).work_contact_id,
        help='Para Liquidación/Pago Directo, el contacto/proveedor normal, sin restricción - '
             'sin cambios. Para Anticipo Viáticos, este es el "Empleado Solicitante" fusionado '
             'aquí (antes un campo separado) - la vista restringe el dominio a contactos '
             'marcados como empleado (`res.partner.employee`, nativo) y lo bloquea después de '
             'crear (ver write()), solo para ese tipo, para evitar suplantación. '
             'Contactos no tiene la regla multiempresa de `hr.employee`, así que el desplegable '
             'no choca con ella ni en Community ni en Enterprise. El hr.employee real se '
             'resuelve en `employee_id` (ver _compute_employee_id/_resolve_employee_for_partner).')
    currency_id = fields.Many2one('res.currency', string='Moneda',
                                   default=lambda self: self.env.company.currency_id.id)
    cuenta_ajuste_id = fields.Many2one('account.account', string='Cuenta de Ajuste')
    move_id = fields.Many2one('account.move', string='Asiento', readonly=True, copy=False)
    anticipo_id = fields.Many2one(
        'account.payment.order', string='Anticipo de Origen',
        domain="[('id', 'in', anticipos_disponibles_ids)]", copy=False,
        help='Anticipo del que se origina esta Liquidación. Se llena solo al generarla desde el '
             'botón "Registrar Liquidación" de un Anticipo aplicado - editable en borrador por '
             'si se necesita corregirlo a mano, listando únicamente Anticipos ya Aplicados que '
             'todavía no tengan otra Liquidación registrada (ver `_compute_anticipos_disponibles_ids`).')
    anticipos_disponibles_ids = fields.Many2many(
        'account.payment.order', compute='_compute_anticipos_disponibles_ids',
        help='Auxiliar para el dominio de `anticipo_id` (mismo patrón que '
             '`available_payment_method_line_ids`: un domain string no puede expresar "sin '
             'Liquidación registrada" como subquery directa, así que se materializa aquí). '
             'Anticipos con tipo Anticipo/Anticipo Viáticos, estado Aplicado, sin ninguna otra '
             'Orden tipo Liquidación que ya los referencie en `anticipo_id` - más el propio '
             'valor actual de `anticipo_id`, para que no desaparezca del desplegable si la '
             'configuración cambia después de haberlo elegido.\n\n'
             'OJO al probarlo en `odoo-bin shell` con `.new()`: Odoo envuelve los ids reales que '
             'trae un campo x2many en un registro sin guardar como `NewId(origin=<id real>)` - '
             'comparar con `in` contra el recordset real (`anticipo in registro.new().campo`) da '
             'un falso negativo aunque el id interno sea correcto. Para verificar, comparar por '
             '`origin` (`{getattr(i, "origin", i) for i in registro.campo.ids}`), no por `in` '
             'directo. Esto es un artefacto de `.new()`, no ocurre en la app real: el cliente web '
             'recibe ids planos de la respuesta de onchange, nunca el wrapper NewId.')
    monto = fields.Monetary(string='Monto', currency_field='currency_id',
                             help='Monto del Anticipo a entregar al Contacto.')
    available_payment_method_line_ids = fields.Many2many(
        'account.payment.method.line', compute='_compute_available_payment_method_line_ids',
        help='Auxiliar para el dominio de `payment_method_line_id` - navegar '
             '`journal_id.outbound_payment_method_line_ids` directo dentro de un `domain=` en '
             'string revienta en el cliente (`InvalidDomainError: id,in,`) en cuanto esa lista '
             'queda vacía (diario de banco sin métodos de pago configurados) - mismo motivo por '
             'el que el propio `account.payment` de Odoo usa un campo calculado intermedio '
             '(`available_payment_method_line_ids`) en vez de la ruta punteada directa.')
    payment_method_line_id = fields.Many2one(
        'account.payment.method.line', string='Método de Pago',
        domain="[('id', 'in', available_payment_method_line_ids)]",
        help='Método de pago para el Anticipo, según los métodos configurados en el Diario '
             '(ej. Manual, Cheque). Si se deja vacío, se usa el método por defecto del Diario.')
    cuenta_anticipo_id = fields.Many2one(
        'account.account', string='Cuenta de Anticipos por Liquidar',
        domain=[('account_type', 'in', ('asset_receivable', 'liability_payable'))],
        help='Cuenta puente donde queda registrado el Anticipo hasta que se liquide contra facturas '
             'reales (no es la cuenta por pagar normal del Contacto). Debe ser de tipo por cobrar/por '
             'pagar para que la Liquidación pueda netearla contra las facturas reales.')
    payment_id = fields.Many2one('account.payment', string='Pago del Anticipo', readonly=True, copy=False)
    factura_ids = fields.One2many('account.move', 'payment_order_id', string='Facturas', domain=[
        ('move_type', 'in', ('in_invoice', 'in_refund')),
        ('state', '=', 'posted'),
    ])
    # No se filtra por reconciled_invoice_ids/reconciled_bill_ids aquí: son campos computados
    # cuyo método _search (account_payment.py:_search_reconciled_invoice_ids) solo entiende
    # 'in'/'=' contra un id concreto, no '=False' (lo traduce a "id in ()", que excluye todo).
    # Ese chequeo se hace en Python dentro de action_conciliar().
    pago_ids = fields.One2many('account.payment', 'payment_order_id', string='Pagos/Cheques', domain=[
        # account.payment.state ya no usa 'posted' (solo account.move lo usa) - un pago
        # confirmado pasa a 'in_process' y llega a 'paid' cuando su cuenta puente
        # (Outstanding Payments) queda en cero.
        ('state', 'in', ('in_process', 'paid')),
    ])
    state = fields.Selection([
        ('borrador', 'Borrador'),
        ('enviado', 'Enviado'),
        ('aprobado', 'Aprobado'),
        ('rechazado', 'Rechazado'),
        ('aplicado', 'Aplicado'),
        ('cancelado', 'Cancelado'),
    ], default='borrador', copy=False, tracking=True,
        help='`enviado`/`aprobado`/`rechazado` solo aplican a `tipo=\'anticipo\'` (el ciclo '
             'heredado de la antigua Solicitud de Pago, fusionada aquí) - Liquidación y Pago '
             'Directo siguen yendo directo de `borrador` a `aplicado` vía `action_conciliar()`, '
             'sin pasar por enviar/aprobar, exactamente como antes de esta fusión.')

    # --- Campos absorbidos de la antigua account.payment.order.request (fusión Solicitud+Anticipo) ---
    external_ref = fields.Char(
        string='Referencia de Origen', readonly=True, copy=False,
        help='Referencia (nombre/secuencia) que tenía esta Orden de Pago en la instalación donde '
             'se creó originalmente, si llegó por sincronización.')
    origin = fields.Selection([
        ('local', 'Local'),
        ('synced', 'Sincronizada'),
    ], string='Origen', default='local', copy=False)
    es_procesador = fields.Boolean(
        compute='_compute_es_procesador',
        help='Auxiliar para mostrar/ocultar Aprobar/Rechazar según el rol de la compañía - una '
             'vista no puede navegar `company_id.payment_order_role` directo en `invisible=`, '
             'así que se resuelve aquí. Decisión explícita del usuario: la aprobación ocurre '
             'solo en la instalación Procesadora (Enterprise); una instalación Solicitante '
             '(Community) nunca debe ver estos botones.')
    requested_by_id = fields.Many2one('res.users', string='Solicitado por',
                                       default=lambda self: self.env.user, readonly=True, copy=False,
                                       help='Técnico para la regla de seguridad "ve las propias" '
                                            '(`account_payment_order_own_rule`) - no se muestra en '
                                            'el formulario, `partner_id` ya identifica a la persona '
                                            'sin duplicarla.')
    requested_by_name = fields.Char(string='Nombre', default=lambda self: self.env.user.name,
                                     help='Ya no se muestra en el formulario (duplicaba a '
                                          '`partner_id`) - se mantiene solo por compatibilidad '
                                          'con `_prepare_sync_vals()`.')
    employee_id = fields.Many2one(
        'hr.employee', string='Empleado (resuelto)', compute='_compute_employee_id',
        store=True, readonly=True,
        help='hr.employee real detrás de `partner_id` (fusionado con el antiguo '
             '"Empleado Solicitante" - un solo campo de contacto, no dos - ver '
             '_resolve_employee_for_partner()). Todo lo que ya dependía de un employee_id '
             '(departamento/puesto/banco/teléfono en el onchange y en create(), y '
             '`employee_enterprise_ref` en _prepare_sync_vals()) sigue funcionando igual.')
    puesto = fields.Char(string='Puesto')
    departamento = fields.Char(string='Departamento')
    analytic_account_id = fields.Many2one(
        'account.analytic.account', string='Cuenta Analítica',
        help='Sincronizada desde Enterprise. Solo llena el campo de texto "Proyecto" '
             'automáticamente; no se envía ningún id a la instalación Procesadora.')
    proyecto = fields.Char(string='Proyecto')
    telefono = fields.Char(string='Teléfono')
    correo = fields.Char(string='Correo', default=lambda self: self.env.user.email)
    cuenta_acreditar = fields.Char(
        string='Cuenta a Acreditar', readonly=True,
        help='Se autocompleta desde la cuenta bancaria del empleado solicitante en Enterprise - '
             'no editable, para evitar que una solicitud acredite a una cuenta distinta a la del '
             'empleado real.')
    tipo_cuenta = fields.Selection([
        ('monetaria', 'Monetaria'),
        ('ahorro', 'Ahorro'),
    ], string='Tipo de Cuenta')
    banco = fields.Char(string='Banco', readonly=True)
    periodo_del = fields.Date(string='Del')
    periodo_al = fields.Date(string='Al')
    observaciones = fields.Text(string='Observaciones / Instrucciones')
    viaticos_line_ids = fields.One2many(
        'account.payment.order.viatico.line', 'order_id', string='Líneas de Viáticos')
    anticipo_previo = fields.Float(string='Anticipo')
    subtotal = fields.Float(string='Subtotal', compute='_compute_totales', store=True)
    total_acreditar = fields.Float(string='Total a Acreditar', compute='_compute_totales', store=True)
    submit_date = fields.Datetime(string='Fecha de Envío', readonly=True, copy=False)
    approved_by_id = fields.Many2one('res.users', string='Aprobado por', readonly=True, copy=False)
    approve_date = fields.Datetime(string='Fecha de Aprobación', readonly=True, copy=False)
    rejected_by_id = fields.Many2one('res.users', string='Rechazado por', readonly=True, copy=False)
    reject_date = fields.Datetime(string='Fecha de Rechazo', readonly=True, copy=False)
    reject_reason = fields.Text(string='Motivo de Rechazo')
    sync_state = fields.Selection([
        ('not_synced', 'No Sincronizada'),
        ('synced', 'Sincronizada'),
        ('error', 'Error de Sincronización'),
    ], string='Sincronización', default='not_synced', copy=False, tracking=True)
    sync_error = fields.Text(string='Detalle del Error de Sincronización', readonly=True, copy=False)
    sync_date = fields.Datetime(string='Fecha de Sincronización', readonly=True, copy=False)

    _sql_constraints = [
        ('no_liquidacion_unique',
         'UNIQUE(no_liquidacion) WHERE no_liquidacion != 0',
         'El número de liquidación debe ser único, excepto si es cero.'),
    ]

    @api.depends('no_liquidacion', 'tipo')
    def _compute_name(self):
        for rec in self:
            if rec.tipo == 'liquidacion' and rec.no_liquidacion:
                rec.name = 'Liquidación %s' % rec.no_liquidacion
            elif not rec.name:
                rec.name = 'Nueva Orden de Pago'

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        """Filtra las opciones del desplegable de `tipo` según la configuración de la compañía
        actual (`res.company._get_payment_order_allowed_tipos()`) - Fase 1 del proyecto:
        Community solo debe ofrecer "Anticipo Viáticos" al crear, Enterprise las demás.

        Deliberadamente solo toca lo que el CLIENTE ofrece elegir en un formulario nuevo, no la
        validación de create()/write() (que sigue aceptando cualquier valor del Selection
        completo) - una Orden sincronizada o creada por `action_registrar_liquidacion()` debe
        poder existir sin importar esta configuración. Ver el `help=` de cada campo booleano en
        res_company.py."""
        res = super().fields_get(allfields=allfields, attributes=attributes)
        tipo_desc = res.get('tipo')
        if tipo_desc and tipo_desc.get('selection'):
            allowed = self.env.company._get_payment_order_allowed_tipos()
            tipo_desc['selection'] = [
                (value, label) for value, label in tipo_desc['selection'] if value in allowed
            ]
        return res

    @api.depends('anticipo_id')
    def _compute_anticipos_disponibles_ids(self):
        ya_liquidados = self.env['account.payment.order'].search([
            ('tipo', '=', 'liquidacion'), ('anticipo_id', '!=', False),
        ]).anticipo_id
        disponibles = self.env['account.payment.order'].search([
            ('tipo', 'in', ANTICIPO_TIPOS), ('state', '=', 'aplicado'),
        ]) - ya_liquidados
        for rec in self:
            rec.anticipos_disponibles_ids = disponibles | rec.anticipo_id

    @api.constrains('tipo', 'anticipo_id')
    def _check_anticipo_id(self):
        for rec in self:
            if rec.tipo == 'liquidacion' and not rec.anticipo_id:
                raise ValidationError(rec.env._(
                    'Una Liquidación debe originarse desde un Anticipo: usa el botón "Registrar '
                    'Liquidación" en el Anticipo correspondiente en vez de crearla directamente.'))

    @api.constrains('tipo', 'journal_id')
    def _check_journal_id(self):
        """Liquidación/Pago Directo siempre necesitan un Diario (antes se garantizaba con
        `required=True` a nivel de campo, cuando `journal_id` solo existía para estos dos
        tipos). Un Anticipo NO lo necesita todavía al crearse - lo llena el contable después de
        Aprobar (ver el `help=` de `journal_id` y `action_aplicar()`, que sí lo exige antes de
        aplicar)."""
        for rec in self:
            if rec.tipo not in ANTICIPO_TIPOS and not rec.journal_id:
                raise ValidationError(rec.env._(
                    'Defina el Diario antes de guardar una Orden de Pago de tipo %s.', rec.tipo))

    def _check_es_administrador_contable(self):
        if not self.env.user.has_group('account.group_account_manager'):
            raise AccessError(self.env._(
                'Se requiere el permiso de Contabilidad: Administrador para aplicar o cancelar '
                'una Orden de Pago. Cualquier usuario de Contabilidad puede crearla y dejarla en '
                'borrador, pero solo un Administrador puede avanzarla de estado.'))

    @api.depends('journal_id')
    def _compute_available_payment_method_line_ids(self):
        for rec in self:
            rec.available_payment_method_line_ids = rec.journal_id.outbound_payment_method_line_ids

    @api.onchange('journal_id')
    def _onchange_journal_id_payment_method(self):
        if self.payment_method_line_id not in self.journal_id.outbound_payment_method_line_ids:
            self.payment_method_line_id = self.journal_id.outbound_payment_method_line_ids[:1]

    @api.onchange('no_liquidacion')
    def _onchange_no_liquidacion(self):
        if self.no_liquidacion:
            existing = self.env['account.payment.order'].search([
                ('no_liquidacion', '=', self.no_liquidacion),
                ('id', '!=', self._origin.id),
            ], limit=1)
            if existing:
                raise UserError(self.env._('El número de liquidación ya existe.'))
            self.name = 'Liquidación %s' % self.no_liquidacion
            for factura in self.factura_ids:
                factura.no_liquidacion = self.no_liquidacion

    @api.depends('partner_id', 'company_id')
    def _compute_employee_id(self):
        for rec in self:
            rec.employee_id = _resolve_employee_for_partner(rec.partner_id, rec.company_id)

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        for rec in self:
            if rec.employee_id:
                # puesto/departamento se leen del CONTACTO (res_partner.py,
                # function/employee_department_id - heredados automáticamente ahí
                # desde el hr.employee vinculado), no resueltos aquí en vivo - decisión
                # explícita del usuario: un solo valor por contacto, no uno por compañía.
                rec.puesto = rec.partner_id.function or rec.puesto
                rec.departamento = rec.partner_id.employee_department_id.name or rec.departamento
                # sudo(): un solicitante normal no tiene por qué tener hr.group_hr_user, y
                # aun así debe poder ver estos datos no sensibles de SU PROPIO empleado vinculado.
                employee = rec.employee_id.sudo()
                # cuenta_bancaria/banco_nombre/telefono_personal solo resuelven a un valor real
                # cuando employee_id es el empleado vinculado al usuario actual - hr_employee.py.
                rec.cuenta_acreditar = rec.employee_id.cuenta_bancaria or rec.cuenta_acreditar
                rec.banco = rec.employee_id.banco_nombre or rec.banco
                # Teléfono: trabajo (work_phone) -> celular de trabajo (mobile_phone) ->
                # personal (private_phone), campos nativos de hr.employee. sudo() porque
                # private_phone requiere hr.group_hr_user para leerse directo.
                rec.telefono = (employee.work_phone or employee.mobile_phone
                                 or employee.private_phone or rec.telefono)
                # Correo: de trabajo -> personal, mismo criterio que teléfono.
                rec.correo = employee.work_email or employee.private_email or rec.correo

    @api.depends('company_id.payment_order_role')
    def _compute_es_procesador(self):
        for rec in self:
            rec.es_procesador = rec.company_id.payment_order_role == 'procesador'

    @api.onchange('analytic_account_id')
    def _onchange_analytic_account_id(self):
        for rec in self:
            if rec.analytic_account_id:
                rec.proyecto = rec.analytic_account_id.name

    @api.depends('viaticos_line_ids.total', 'anticipo_previo')
    def _compute_totales(self):
        for rec in self:
            subtotal = sum(rec.viaticos_line_ids.mapped('total'))
            rec.subtotal = subtotal
            rec.total_acreditar = subtotal - rec.anticipo_previo

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('tipo', 'anticipo') in ('anticipo', 'anticipo_viaticos', 'pago_directo') \
                    and not vals.get('name'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'account.payment.order.sequence') or '/'
            self._resolve_employee_enterprise_ref(vals)
            self._resolve_company_enterprise_ref(vals)
            self._resolve_analytic_enterprise_ref(vals)
            self._fill_derived_vals_from_employee(vals)
            self._fill_derived_vals_from_analytic_account(vals)
        return super().create(vals_list)

    def _resolve_employee_enterprise_ref(self, vals):
        """Resuelve `employee_enterprise_ref` (el id ORIGINAL de este empleado en Enterprise,
        enviado por _prepare_sync_vals()) hacia un `partner_id` real de ESTA base - hay un id
        genuinamente válido en ambos lados porque es literalmente el id del empleado tal como
        existe en Enterprise (mismo patrón que `_resolve_analytic_enterprise_ref()` abajo).

        Se resuelve hacia `partner_id` (el contacto), NO hacia `employee_id` directamente -
        `employee_id` es un campo calculado (ver _compute_employee_id()) que se vuelve a derivar
        solo, y lo hace exactamente hacia ESTE mismo hr.employee porque `company_id` también
        queda fijado aquí abajo a su compañía real (ver _resolve_employee_for_partner: coincidir
        compañía es el primer criterio de desempate)."""
        ref = vals.pop('employee_enterprise_ref', None)
        if ref and not vals.get('partner_id'):
            employee = self.env['hr.employee'].browse(int(ref)).exists()
            if employee:
                vals['partner_id'] = employee.work_contact_id.id
                vals.setdefault('company_id', employee.company_id.id)

    def _resolve_company_enterprise_ref(self, vals):
        """Respaldo de compañía (`res.company.payment_order_default_company_id`, configurado en
        la instalación Solicitante) para cuando el empleado no se pudo resolver arriba - ej. la
        Orden de Pago llegó de un usuario todavía no sincronizado. No-op si `company_id` ya
        quedó resuelto por el empleado."""
        ref = vals.pop('company_enterprise_ref', None)
        if ref and not vals.get('company_id'):
            company = self.env['res.company'].browse(int(ref)).exists()
            if company:
                vals['company_id'] = company.id

    def _resolve_analytic_enterprise_ref(self, vals):
        """Resuelve `analytic_enterprise_ref` (enviado por _prepare_sync_vals(), tomado del
        `enterprise_analytic_ref` del mirror local en Community - ver `_sync_analytic_accounts_
        from_enterprise()` en res_company.py) hacia un `analytic_account_id` real de ESTA base -
        mismo patrón que `_resolve_employee_enterprise_ref()`: es un id genuinamente válido aquí
        porque es literalmente el id de la cuenta analítica tal como existe en Enterprise (el
        mirror de Community solo la reflejó, nunca la creó de cero).

        Bug real corregido (2026-08): antes de esto, la cuenta analítica NUNCA viajaba como
        relación real - `_prepare_sync_vals()` solo mandaba `proyecto` (el nombre en texto plano)
        y `_fill_derived_vals_from_analytic_account()` únicamente sabe derivar `proyecto` A PARTIR
        de un `analytic_account_id` ya dado, no al revés - así que una Orden sincronizada desde
        Community, aunque mostrara el nombre correcto en "Proyecto", llegaba a Enterprise con
        `analytic_account_id` vacío."""
        ref = vals.pop('analytic_enterprise_ref', None)
        if ref and not vals.get('analytic_account_id'):
            analytic_account = self.env['account.analytic.account'].browse(int(ref)).exists()
            if analytic_account:
                vals['analytic_account_id'] = analytic_account.id

    def _fill_derived_vals_from_employee(self, vals):
        """Same autocompletado que _onchange_partner_id, pero para create() por API/script (el
        onchange solo corre en el formulario web). `employee_id` todavía no existe como tal (el
        registro no se ha insertado, así que el campo calculado no ha corrido) - se resuelve
        aquí con el mismo criterio (_resolve_employee_for_partner) para poder llenar los campos
        de texto plano (puesto/banco/teléfono/etc.) antes del insert."""
        partner_id = vals.get('partner_id')
        if not partner_id:
            partner_id = self.default_get(['partner_id']).get('partner_id')
        if not partner_id:
            return
        vals.setdefault('partner_id', partner_id)
        partner = self.env['res.partner'].browse(partner_id)
        company = self.env['res.company'].browse(vals.get('company_id')) if vals.get('company_id') \
            else self.env.company
        # puesto/departamento: del CONTACTO, no resueltos aquí en vivo - ver res_partner.py.
        vals.setdefault('puesto', partner.function or False)
        vals.setdefault('departamento', partner.employee_department_id.name or False)
        employee = _resolve_employee_for_partner(partner, company)
        if not employee:
            return
        vals.setdefault('cuenta_acreditar', employee.cuenta_bancaria or False)
        vals.setdefault('banco', employee.banco_nombre or False)
        vals.setdefault('telefono', employee.sudo().work_phone or employee.sudo().mobile_phone
                        or employee.sudo().private_phone or False)
        vals.setdefault('correo', employee.sudo().work_email or employee.sudo().private_email or False)

    def _fill_derived_vals_from_analytic_account(self, vals):
        analytic_account_id = vals.get('analytic_account_id')
        if not analytic_account_id:
            return
        analytic_account = self.env['account.analytic.account'].browse(analytic_account_id)
        vals.setdefault('proyecto', analytic_account.name)

    def write(self, vals):
        if not self.env.user.has_group(APPROVER_GROUP_XMLID):
            for rec in self:
                # Anti-suplantación, solo para Anticipo Viáticos - partner_id de una
                # Liquidación/Pago Directo/Anticipo normal debe seguir siendo libremente
                # editable (nunca tuvo esta restricción). employee_id (calculado) se revisa
                # también por defensa en profundidad.
                if rec.tipo != 'anticipo_viaticos':
                    continue
                if ('partner_id' in vals and rec.partner_id
                        and vals['partner_id'] != rec.partner_id.id):
                    raise UserError(self.env._(
                        'No se puede cambiar el empleado de una Orden de Pago ya creada '
                        '- cree una nueva en su lugar.'))
                if ('employee_id' in vals and rec.employee_id
                        and vals['employee_id'] != rec.employee_id.id):
                    raise UserError(self.env._(
                        'No se puede cambiar el empleado de una Orden de Pago ya creada '
                        '- cree una nueva en su lugar.'))
        return super().write(vals)

    def unlink(self):
        for rec in self:
            if rec.tipo in ANTICIPO_TIPOS and rec.state not in ('borrador', 'cancelado', 'rechazado'):
                raise UserError(self.env._(
                    'No puede eliminar una Orden de Pago que no esté en borrador, '
                    'cancelada o rechazada.'))
        return super().unlink()

    def _check_is_approver(self):
        if not self.env.user.has_group(APPROVER_GROUP_XMLID):
            raise AccessError(self.env._(
                'Solo un usuario autorizado puede aprobar o rechazar Órdenes de Pago.'))

    def _check_is_approver_for_amount(self):
        """Gate por monto para action_approve(): Nivel Alto (Gerente de Área) siempre puede
        aprobar (implica Nivel Medio); Nivel Medio (Jefe de Área) solo si el Total a Acreditar
        es menor al umbral configurado en la compañía. Se revisa registro por registro porque
        el monto varía por Orden de Pago."""
        self.ensure_one()
        threshold = self.company_id.payment_order_approval_threshold or 0.0
        if self.total_acreditar >= threshold:
            if not self.env.user.has_group(APPROVER_ALTO_GROUP_XMLID):
                raise AccessError(self.env._(
                    'La Orden %(name)s (Q%(monto).2f) es mayor o igual al umbral de '
                    'Q%(umbral).2f - solo un Aprobador Nivel Alto (Gerente de Área) puede '
                    'aprobarla.', name=self.name, monto=self.total_acreditar, umbral=threshold))
        elif not self.env.user.has_group(APPROVER_MEDIO_GROUP_XMLID):
            raise AccessError(self.env._(
                'Solo un Aprobador Nivel Medio (Jefe de Área) o superior puede aprobar '
                'Órdenes de Pago.'))

    def action_submit(self):
        for rec in self:
            if rec.tipo not in ANTICIPO_TIPOS:
                raise UserError(self.env._('Enviar solo aplica a Órdenes de Pago de tipo Anticipo.'))
            if rec.tipo == 'anticipo_viaticos' and not rec.viaticos_line_ids:
                raise UserError(self.env._(
                    'Agregue al menos una línea de viáticos antes de enviar la orden.'))
            if rec.viaticos_line_ids.filtered(lambda line: not line.employee_id):
                raise UserError(self.env._(
                    'Todas las líneas de viáticos deben tener un empleado seleccionado antes '
                    'de enviar la orden.'))
            if rec.tipo == 'anticipo_viaticos' and not (
                    rec.cuenta_acreditar and rec.tipo_cuenta and rec.banco
                    and rec.periodo_del and rec.periodo_al):
                raise UserError(self.env._(
                    'Complete cuenta a acreditar, tipo de cuenta, banco y el período antes de '
                    'enviar la orden.'))
            rec.write({'state': 'enviado', 'submit_date': fields.Datetime.now()})
        # La sincronización ocurre al enviar, no al aprobar - la aprobación (Nivel Medio/Alto)
        # ocurre en la instalación Procesadora (Enterprise), donde están los usuarios
        # administrativos reales. En una instalación Procesadora esto es un no-op
        # (_sync_to_enterprise() solo actúa si payment_order_role == 'solicitante').
        self._sync_to_enterprise()

    def action_approve(self):
        for rec in self:
            if rec.tipo not in ANTICIPO_TIPOS:
                raise UserError(self.env._('Aprobar solo aplica a Órdenes de Pago de tipo Anticipo.'))
            rec._check_is_approver_for_amount()
            rec.write({
                'state': 'aprobado',
                'approved_by_id': self.env.user.id,
                'approve_date': fields.Datetime.now(),
            })

    def action_reject(self):
        self._check_is_approver()
        for rec in self:
            if rec.tipo not in ANTICIPO_TIPOS:
                raise UserError(self.env._('Rechazar solo aplica a Órdenes de Pago de tipo Anticipo.'))
            rec.write({
                'state': 'rechazado',
                'rejected_by_id': self.env.user.id,
                'reject_date': fields.Datetime.now(),
            })

    def action_reset_to_draft(self):
        for rec in self:
            if rec.tipo not in ANTICIPO_TIPOS:
                raise UserError(self.env._(
                    'Volver a Borrador solo aplica a Órdenes de Pago de tipo Anticipo.'))
            rec.write({
                'state': 'borrador',
                'approved_by_id': False,
                'rejected_by_id': False,
                'reject_reason': False,
            })

    def action_cancel(self):
        for rec in self:
            if rec.tipo not in ANTICIPO_TIPOS:
                raise UserError(self.env._('Cancelar (Anticipo) solo aplica a tipo Anticipo.'))
            rec.state = 'cancelado'

    def action_cancelar_anticipo_aplicado(self):
        """Cancela/revierte un Anticipo YA Aplicado (pago real ya contabilizado) - a diferencia
        de `action_cancel()` (sin restricción de grupo, pero solo visible ANTES de aplicar, ver
        la vista), esto deshace un pago real, así que está restringido a Gerente igual que
        `action_cancelar()` (Liquidación/Pago Directo). Bloquea si ya existe una Liquidación
        registrada para este Anticipo - cancelar el pago por debajo la dejaría en un estado
        inconsistente (referenciando un pago cancelado, o rompiendo una conciliación ya hecha)."""
        self.ensure_one()
        if self.tipo not in ANTICIPO_TIPOS:
            raise UserError(self.env._(
                'Esta acción solo aplica a Anticipo/Anticipo Viáticos.'))
        if self.state != 'aplicado':
            raise UserError(self.env._(
                'Solo se puede cancelar así un Anticipo ya Aplicado - use el botón "Cancelar" '
                'normal para uno que todavía no se ha aplicado.'))
        self._check_es_administrador_contable()
        if self.search_count([('anticipo_id', '=', self.id)]):
            raise UserError(self.env._(
                'Este Anticipo ya tiene una Liquidación registrada - cancela o revierte esa '
                'Liquidación primero (botón "Cancelar" en la Liquidación).'))
        if self.payment_id:
            for line in self.payment_id.move_id.line_ids:
                if line.reconciled:
                    line.remove_move_reconcile()
            self.payment_id.action_cancel()
        self.write({'state': 'cancelado'})
        return True

    def _prepare_sync_vals(self):
        """Snapshot plano (sin ids) para crear el registro correspondiente en la instalación
        Procesadora - incluso siendo el mismo modelo en ambos lados, un id de res.company/
        res.users de esta base no significa nada en la otra.

        Excepción deliberada: `employee_enterprise_ref`/`company_enterprise_ref`/
        `analytic_enterprise_ref` SÍ son ids, pero válidos en ambos lados porque son literalmente
        los ids que Enterprise usa para ese empleado/compañía/cuenta analítica (todos se
        sincronizaron DESDE ahí - ver `enterprise_employee_ref` en hr_employee.py y
        `enterprise_analytic_ref` en account_analytic_account.py). No es lo mismo que enviar un
        id local de esta base (que no significaría nada allá)."""
        self.ensure_one()
        return {
            'tipo': 'anticipo_viaticos',
            'external_ref': self.name,
            'origin': 'synced',
            'requested_by_name': self.requested_by_name or '',
            'employee_enterprise_ref': self.employee_id.enterprise_employee_ref or False,
            'company_enterprise_ref':
                self.company_id.payment_order_default_company_id.enterprise_company_ref or False,
            'analytic_enterprise_ref': self.analytic_account_id.enterprise_analytic_ref or False,
            'puesto': self.puesto or '',
            'departamento': self.departamento or '',
            'proyecto': self.proyecto or '',
            'telefono': self.telefono or '',
            'correo': self.correo or '',
            'fecha': self.fecha and self.fecha.isoformat() or False,
            'cuenta_acreditar': self.cuenta_acreditar or '',
            'tipo_cuenta': self.tipo_cuenta,
            'banco': self.banco or '',
            'periodo_del': self.periodo_del and self.periodo_del.isoformat() or False,
            'periodo_al': self.periodo_al and self.periodo_al.isoformat() or False,
            'observaciones': self.observaciones or '',
            'anticipo_previo': self.anticipo_previo,
            # 'enviado', no 'aprobado': la aprobación ocurre en la instalación Procesadora
            # (Enterprise), donde están los usuarios Nivel Medio/Alto reales - ver
            # action_submit()/action_approve() más arriba.
            'state': 'enviado',
            'submit_date': fields.Datetime.to_string(fields.Datetime.now()),
            'viaticos_line_ids': [
                (0, 0, {
                    'tecnico_name': line.tecnico_name or '',
                    'employee_enterprise_ref': line.employee_id.enterprise_employee_ref or False,
                    'departamento': line.departamento or '',
                    'puesto': line.puesto or '',
                    'cantidad': line.cantidad,
                    'costo_individual': line.costo_individual,
                })
                for line in self.viaticos_line_ids
            ],
        }

    def _sync_to_enterprise(self):
        """Empuja esta Orden de Pago (recién enviada, `state='enviado'`) hacia la instalación
        Procesadora configurada - se llama desde action_submit(), no action_approve(): la
        aprobación ocurre en Enterprise, no aquí (decisión explícita del usuario).

        Nunca lanza: los fallos quedan registrados en el propio registro (sync_state='error')
        para el cron de reintento, sin bloquear action_submit()."""
        for rec in self.filtered(lambda r: r.tipo in ANTICIPO_TIPOS):
            company = rec.company_id
            if company.payment_order_role != 'solicitante' or not company.payment_order_sync_enabled:
                continue
            try:
                remote_id = create_sync_record(
                    company.payment_order_sync_url,
                    company.payment_order_sync_db,
                    company.payment_order_sync_login,
                    company.payment_order_sync_api_key,
                    rec._prepare_sync_vals(),
                )
            except EnterpriseSyncError as exc:
                rec.write({'sync_state': 'error', 'sync_error': str(exc)})
                company._payment_order_sync_log(
                    False, self.env._('Error al sincronizar %(name)s: %(error)s', name=rec.name, error=exc))
            else:
                rec.write({
                    'sync_state': 'synced',
                    'sync_error': False,
                    'sync_date': fields.Datetime.now(),
                })
                company._payment_order_sync_log(
                    True, self.env._(
                        'Orden de Pago %(name)s sincronizada (id remoto %(remote_id)s).',
                        name=rec.name, remote_id=remote_id))

    def action_retry_sync(self):
        self._sync_to_enterprise()

    @api.model
    def _cron_retry_sync(self):
        pending = self.search([
            ('tipo', 'in', ANTICIPO_TIPOS),
            ('sync_state', '=', 'error'),
            ('company_id.payment_order_role', '=', 'solicitante'),
            ('company_id.payment_order_sync_enabled', '=', True),
        ])
        pending._sync_to_enterprise()

    def action_conciliar(self):
        self.ensure_one()
        if self.tipo not in ('liquidacion', 'pago_directo'):
            raise UserError(self.env._(
                'Conciliar solo aplica a órdenes de tipo Liquidación o Pago Directo.'))
        self._check_es_administrador_contable()
        if self.tipo == 'pago_directo' and not self.factura_ids:
            raise UserError(self.env._(
                'Un Pago Directo debe incluir al menos una factura.'))

        # Solo las líneas de por cobrar/por pagar representan la deuda con el proveedor o
        # el contacto - las demás (caja, banco, "Pagos Pendientes"/outstanding) son solo el
        # otro lado del asiento y no deben entrar en el neteo.
        CUENTAS_A_NETEAR = ('asset_receivable', 'liability_payable')

        lineas = []
        total = 0.0

        for factura in self.factura_ids:
            if factura.state != 'posted':
                continue
            for line in factura.line_ids:
                if line.account_id.reconcile and line.account_id.account_type in CUENTAS_A_NETEAR:
                    if line.reconciled:
                        raise UserError(self.env._('La factura %s ya está conciliada.', factura.name))
                    total += (line.credit - line.debit)
                    lineas.append(line)

        for pago in self.pago_ids:
            if pago.state not in ('in_process', 'paid'):
                continue
            if pago.reconciled_invoice_ids or pago.reconciled_bill_ids:
                raise UserError(self.env._('El pago %s ya está conciliado.', pago.name))
            for line in pago.move_id.line_ids:
                if line.account_id.reconcile and line.account_id.account_type in CUENTAS_A_NETEAR:
                    total -= (line.debit - line.credit)
                    lineas.append(line)

        if round(total, 2) != 0:
            if self.tipo == 'pago_directo':
                raise UserError(self.env._(
                    'El monto del pago no coincide con el total de la(s) factura(s) - un Pago '
                    'Directo debe cubrir exactamente el 100%s de las facturas, sin diferencia '
                    '(a diferencia de una Liquidación, no admite Cuenta de Ajuste). Corrige el '
                    'monto del pago o registra esto como una Liquidación en su lugar.', '%'))
            if not self.cuenta_ajuste_id:
                raise UserError(self.env._(
                    'El total de las facturas no coincide con el total de los pagos. Define una '
                    'Cuenta de Ajuste para registrar la diferencia.'))

        nuevas_lineas = []
        for linea in lineas:
            nuevas_lineas.append((0, 0, {
                'name': linea.name,
                'debit': linea.credit,
                'credit': linea.debit,
                'account_id': linea.account_id.id,
                'partner_id': linea.partner_id.id,
                'date_maturity': self.fecha,
            }))

        if round(total, 2) != 0:
            nuevas_lineas.append((0, 0, {
                'name': 'Diferencial en %s' % self.name,
                'debit': -total if total < 0 else 0,
                'credit': total if total > 0 else 0,
                'account_id': self.cuenta_ajuste_id.id,
                'date_maturity': self.fecha,
            }))

        move = self.env['account.move'].create({
            'move_type': 'entry',
            'line_ids': nuevas_lineas,
            'ref': self.name,
            'date': self.fecha,
            'journal_id': self.journal_id.id,
        })
        move.action_post()

        for linea, nueva_linea in zip(lineas, move.line_ids):
            (linea | nueva_linea).reconcile()

        self.write({'move_id': move.id, 'state': 'aplicado'})
        return True

    def action_cancelar(self):
        self.ensure_one()
        if self.tipo not in ('liquidacion', 'pago_directo'):
            raise UserError(self.env._(
                'Cancelar solo aplica a órdenes de tipo Liquidación o Pago Directo.'))
        self._check_es_administrador_contable()
        if self.move_id:
            for line in self.move_id.line_ids:
                if line.reconciled:
                    line.remove_move_reconcile()
            self.move_id.button_cancel()
            self.move_id.unlink()
        self.write({'move_id': False, 'state': 'borrador'})
        return True

    def action_crear_pago(self):
        """Crea y contabiliza UN account.payment por el monto todavía pendiente, en vez de exigir
        que el contable lo cree a mano en Contabilidad > Pagos y lo vincule aquí antes de
        Conciliar. Caso real que motivó esto: varias facturas se pagan en un solo pago, o una
        factura se paga con varios pagos (ej. el propio pago del Anticipo cubre una parte y este
        botón cubre el resto) - `action_conciliar()` ya sabe netear cualquier combinación de
        `factura_ids`/`pago_ids`, lo único que faltaba era no depender de que el pago ya existiera
        de antemano. Si hace falta más de un pago adicional, se puede llamar este botón varias
        veces (cada uno cubre lo que quede pendiente en ese momento), o agregar pagos ya
        existentes a mano en `pago_ids` como ya se podía hacer antes."""
        self.ensure_one()
        if self.tipo not in ('liquidacion', 'pago_directo'):
            raise UserError(self.env._(
                'Crear Pago solo aplica a órdenes de tipo Liquidación o Pago Directo.'))
        self._check_es_administrador_contable()
        if not self.journal_id:
            raise UserError(self.env._('Define el Diario antes de crear un pago.'))
        if not self.partner_id:
            raise UserError(self.env._('Define el Contacto antes de crear un pago.'))

        total_facturas = sum(self.factura_ids.filtered(
            lambda f: f.state == 'posted').mapped('amount_total'))
        ya_pagado = sum(self.pago_ids.filtered(
            lambda p: p.state in ('in_process', 'paid')).mapped('amount'))
        faltante = total_facturas - ya_pagado
        if self.currency_id.is_zero(faltante):
            raise UserError(self.env._(
                'No hay ningún monto pendiente de pagar - el/los pago(s) ya registrado(s) '
                'cubren el total de las facturas.'))
        if faltante < 0:
            raise UserError(self.env._(
                'El/los pago(s) ya registrado(s) superan el total de las facturas - revisa '
                'antes de crear otro pago.'))

        payment = self.env['account.payment'].create({
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': self.partner_id.id,
            'amount': faltante,
            'currency_id': self.currency_id.id,
            'journal_id': self.journal_id.id,
            'date': self.fecha,
            'memo': self.name,
            'payment_order_id': self.id,
        })
        payment.action_post()
        return True

    def action_aplicar(self):
        self.ensure_one()
        if self.tipo not in ANTICIPO_TIPOS:
            raise UserError(self.env._('Aplicar solo se usa para órdenes de tipo Anticipo.'))
        if self.state != 'aprobado':
            raise UserError(self.env._(
                'Solo se puede Aplicar una Orden de Pago ya Aprobada - use Enviar y luego '
                'Aprobar primero (todo Anticipo debe pasar por ese camino, incluso uno '
                'creado directo en Enterprise).'))
        self._check_es_administrador_contable()
        if not self.journal_id:
            raise UserError(self.env._('Define el Diario antes de aplicar.'))
        if not self.partner_id:
            raise UserError(self.env._('Define el Contacto que recibirá el anticipo.'))
        if not self.monto:
            raise UserError(self.env._('Define el Monto del anticipo.'))
        if not self.cuenta_anticipo_id:
            raise UserError(self.env._('Define la Cuenta de Anticipos por Liquidar.'))

        payment_vals = {
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': self.partner_id.id,
            'amount': self.monto,
            'currency_id': self.currency_id.id,
            'journal_id': self.journal_id.id,
            'date': self.fecha,
            'memo': self.name,
            'destination_account_id': self.cuenta_anticipo_id.id,
            # También vinculado a pago_ids (relación inversa vía payment_order_id) - no solo a
            # payment_id - así queda visible junto a cualquier pago adicional que se agregue
            # después (ver action_crear_pago()), en vez de ser el único pago "invisible" para
            # ese mecanismo genérico. payment_id se mantiene igual, por compatibilidad con
            # action_registrar_liquidacion() y el reporte impreso.
            'payment_order_id': self.id,
        }
        if self.payment_method_line_id:
            payment_vals['payment_method_line_id'] = self.payment_method_line_id.id
        payment = self.env['account.payment'].create(payment_vals)
        payment.action_post()
        self.write({'payment_id': payment.id, 'state': 'aplicado'})

        # Dos avisos posibles, ninguno bloquea: si el contacto ya tiene otro Anticipo aplicado
        # sin Liquidación registrada (antes vivía en el Wizard "Crear Anticipo", ya retirado -
        # ver CLAUDE.md), y/o si esta Orden ya cubre el 100% de facturas adjuntas (pudo haber
        # sido un Pago Directo). Se encadenan con el mecanismo nativo `next` de
        # display_notification si ambos aplican a la vez.
        aviso_pendientes = None
        pendientes = self._find_anticipos_sin_liquidar(self.partner_id, exclude=self)
        if pendientes:
            aviso_pendientes = {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': self.env._('Anticipos pendientes de liquidar'),
                    'message': self.env._(
                        '%(contacto)s ya tiene %(cantidad)s Anticipo(s) aplicado(s) sin '
                        'Liquidación registrada todavía (%(nombres)s) - revisa si corresponde '
                        'liquidarlos antes de entregar uno nuevo.',
                        contacto=self.partner_id.name, cantidad=len(pendientes),
                        nombres=', '.join(pendientes.mapped('name'))),
                    'type': 'warning',
                    'sticky': True,
                },
            }
        aviso_pago_directo = self._aviso_posible_pago_directo()
        if aviso_pendientes and aviso_pago_directo:
            aviso_pendientes['params']['next'] = aviso_pago_directo
            return aviso_pendientes
        return aviso_pendientes or aviso_pago_directo or True

    @api.model
    def _find_anticipos_sin_liquidar(self, partner, exclude=None):
        """Anticipos ya APLICADOS de este contacto que todavía no tienen una Liquidación
        registrada (ver action_registrar_liquidacion(), que fija `anticipo_id` en la
        Liquidación resultante) - se usa para avisar antes de entregar un Anticipo nuevo a
        alguien que ya tiene uno pendiente de liquidar, sin bloquear la operación (puede ser
        intencional: viáticos de dos viajes distintos, por ejemplo)."""
        domain = [
            ('tipo', 'in', ANTICIPO_TIPOS),
            ('state', '=', 'aplicado'),
            ('partner_id', '=', partner.id),
        ]
        if exclude:
            domain.append(('id', '!=', exclude.id))
        anticipos = self.search(domain)
        return anticipos.filtered(
            lambda a: not self.search_count([('anticipo_id', '=', a.id)]))

    def _aviso_posible_pago_directo(self):
        """Si el Anticipo lleva factura(s) adjunta(s) (opcional) cuyo total coincide con el monto
        entregado y ninguna tiene ya un pago conciliado, es en realidad un Pago Directo, no un
        Anticipo pendiente de Liquidación. No se cambia nada automáticamente - solo se avisa."""
        CUENTAS_A_NETEAR = ('asset_receivable', 'liability_payable')
        facturas = self.factura_ids.filtered(lambda f: f.state == 'posted')
        if not facturas:
            return None
        ya_conciliadas = facturas.filtered(lambda f: any(
            line.reconciled for line in f.line_ids if line.account_id.account_type in CUENTAS_A_NETEAR))
        if ya_conciliadas:
            return None
        total_facturas = sum(facturas.mapped('amount_total'))
        if self.currency_id.compare_amounts(total_facturas, self.monto) != 0:
            return None
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._('Posible Pago Directo'),
                'message': self.env._(
                    'El monto entregado cubre el 100%s de la(s) factura(s) adjunta(s) y ninguna '
                    'tiene todavía un pago conciliado. Si ya se pagó por completo, considera usar '
                    'una orden de tipo "Pago Directo" en vez de un Anticipo pendiente de liquidar.',
                    '%'),
                'type': 'warning',
                'sticky': True,
            },
        }

    def action_registrar_liquidacion(self):
        self.ensure_one()
        if self.tipo not in ANTICIPO_TIPOS:
            raise UserError(self.env._('Esta acción solo aplica a órdenes de tipo Anticipo.'))
        if self.state != 'aplicado':
            raise UserError(self.env._('Aplica el Anticipo antes de registrar su Liquidación.'))

        liquidacion = self.env['account.payment.order'].create({
            'tipo': 'liquidacion',
            'anticipo_id': self.id,
            'journal_id': self.journal_id.id,
            'fecha': fields.Date.context_today(self),
            'partner_id': self.partner_id.id,
            'pago_ids': [(4, self.payment_id.id)] if self.payment_id else False,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment.order',
            'view_mode': 'form',
            'res_id': liquidacion.id,
            'target': 'current',
        }
