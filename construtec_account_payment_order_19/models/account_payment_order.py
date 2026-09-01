from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from ..tools.enterprise_sync_api import EnterpriseSyncError, create_sync_record

APPROVER_GROUP_XMLID = 'construtec_account_payment_order_19.group_payment_order_approver'
APPROVER_MEDIO_GROUP_XMLID = 'construtec_account_payment_order_19.group_payment_order_approver_medio'
APPROVER_ALTO_GROUP_XMLID = 'construtec_account_payment_order_19.group_payment_order_approver_alto'
# Los tres comparten el mismo ciclo enviado/aprobado/rechazado/aplicado (decisión explícita del
# usuario: "ambos tipos comparten el mismo flujo", extendida a Materiales por el mismo criterio)
# - `anticipo_viaticos`/`anticipo_materiales` son los que se ven en Community (traen sus propias
# líneas de detalle + sync); `anticipo` a secas sigue existiendo para un anticipo que un contable
# arma directo en Enterprise, sin relación a viáticos ni materiales.
ANTICIPO_TIPOS = ('anticipo', 'anticipo_viaticos', 'anticipo_materiales')


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
    _description = 'Orden de Pago (Anticipo / Pago Directo)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fecha desc'

    tipo = fields.Selection([
        ('anticipo', 'Anticipo'),
        ('anticipo_viaticos', 'Anticipo Viáticos'),
        ('anticipo_materiales', 'Anticipo Materiales'),
        ('pago_directo', 'Pago Directo'),
    ], string='Tipo', required=True,
        default=lambda self: (self.env.company._get_payment_order_allowed_tipos() or ['anticipo'])[0],
        help='El valor por defecto es el primer tipo habilitado para esta compañía (ver '
             '`res.company._get_payment_order_allowed_tipos()`) - antes era siempre "Anticipo" '
             'fijo, lo que en Community (solo "Anticipo Viáticos" habilitado) dejaba un registro '
             'nuevo con un valor que ni siquiera aparece en su propio desplegable filtrado '
             '(`fields_get()`), viéndose "vacío" y ocultando Viáticos/Pagos/Facturas por completo.')
    name = fields.Char(string='Nombre', compute='_compute_name', store=True, readonly=False)
    fecha = fields.Date(string='Fecha', required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one(
        'account.journal', string='Diario',
        help='Para Pago Directo se exige siempre (ver `_check_journal_id()`). Para Anticipo, '
             'deliberadamente NO es obligatorio al crear - lo llena el contable DESPUÉS de '
             'Aprobar (fusión Solicitud+Anticipo: ya no hay un Wizard "Crear Anticipo" que lo '
             'pida en un paso aparte) - se exige en cambio dentro de `action_aplicar()`.')
    company_id = fields.Many2one('res.company', string='Compañía', required=True,
                                  default=lambda self: self.env.company.id)
    user_id = fields.Many2one('res.users', string='Usuario', default=lambda self: self.env.user.id)
    partner_id = fields.Many2one(
        'res.partner', string='Contacto',
        default=lambda self: self.env['hr.employee'].search(
            [('user_id', '=', self.env.user.id)], limit=1).work_contact_id,
        help='Para Pago Directo, el contacto/proveedor normal, sin restricción - sin cambios. '
             'Para Anticipo Viáticos, este es el "Empleado Solicitante" fusionado '
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
    monto = fields.Monetary(
        string='Monto', currency_field='currency_id',
        help='Monto del Anticipo a entregar al Contacto. Para Anticipo Viáticos, se llena solo '
             'con la suma de `total_acreditar` (hoy solo la pestaña Viáticos; si en el futuro se '
             'agregan más pestañas de detalle - ej. Materiales - `total_acreditar` las sumaría a '
             'todas ahí, y este campo las heredaría igual, sin cambios aquí) - no es editable a '
             'mano para ese tipo (ver `_sync_monto_desde_total_acreditar()`, disparado por '
             'onchange y en create()/write()). Para un Anticipo normal (sin pestañas de detalle) '
             'sigue siendo un monto capturado a mano, como siempre.')
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
    factura_ids = fields.One2many('account.move', 'payment_order_id', string='Facturas', domain=[
        ('move_type', 'in', ('in_invoice', 'in_refund')),
    ])
    # Deliberadamente SIN filtro de state=posted en el domain (bug real, ver "Bug real: una
    # factura/pago conciliado que se resetea a Borrador desaparecía de la Orden" en el CLAUDE.md
    # de este módulo) - un domain en un One2many se aplica también AL LEER, no solo al buscar
    # candidatas para adjuntar, así que filtrar por estado aquí hacía que una factura ya
    # adjuntada "desapareciera" de la Orden en cuanto alguien la reseteaba a Borrador por fuera
    # de aquí (Contabilidad > Facturas), aunque `payment_order_id` siguiera apuntando aquí. Todo
    # el código que SÍ necesita solo las posted/conciliables ya filtra explícitamente por state
    # en Python (`_compute_diferencia_conciliacion`, `action_conciliar`, `action_crear_pago`) -
    # el domain del campo nunca era necesario para eso, solo causaba esta desaparición.
    # No se filtra por reconciled_invoice_ids/reconciled_bill_ids aquí: son campos computados
    # cuyo método _search (account_payment.py:_search_reconciled_invoice_ids) solo entiende
    # 'in'/'=' contra un id concreto, no '=False' (lo traduce a "id in ()", que excluye todo).
    # Ese chequeo se hace en Python dentro de action_conciliar().
    pago_ids = fields.One2many('account.payment', 'payment_order_id', string='Pagos/Cheques')
    diferencia_conciliacion = fields.Monetary(
        string='Diferencia (a conciliar)', compute='_compute_diferencia_conciliacion',
        currency_field='currency_id',
        help='Facturas cargadas (posted) menos Pagos cargados (in_process/paid) - lo más '
             'cercano a la conciliación nativa de Odoo que se puede mostrar aquí en vivo, antes '
             'de intentar Conciliar: positivo significa que faltan pagos por cubrir (o usar '
             '"Crear Pago"), negativo que faltan facturas (o hay pagos de más). En cero, '
             'Conciliar debería funcionar sin pedir Cuenta de Ajuste. Aproximación con los '
             'totales de cada documento (`amount_total`/`amount`), no con las líneas contables '
             'reales que usa `action_conciliar()` - coinciden en el caso normal, pero la cifra '
             'final la decide siempre `action_conciliar()`, no este campo.')
    puede_conciliar = fields.Boolean(
        compute='_compute_puede_conciliar',
        help='Auxiliar de vista: True cuando esta Orden puede pasar por `action_conciliar()` '
             'ahora mismo - Anticipo/Anticipo Viáticos ya Aplicados, o Pago Directo todavía en '
             'Borrador. Centraliza en un solo campo la condición que antes se repetía en varios '
             'botones/secciones de la vista (Conciliar, Crear Pago, Diferencia a conciliar).')
    state = fields.Selection([
        ('borrador', 'Borrador'),
        ('enviado', 'Enviado'),
        ('aprobado', 'Aprobado'),
        ('rechazado', 'Rechazado'),
        ('aplicado', 'Aplicado'),
        ('liquidado', 'Liquidado'),
        ('cancelado', 'Cancelado'),
    ], default='borrador', copy=False, tracking=True,
        help='`enviado`/`aprobado`/`rechazado` solo aplican a Anticipo/Anticipo Viáticos (el '
             'ciclo heredado de la antigua Solicitud de Pago, fusionada aquí). Pago Directo va '
             'directo de `borrador` a `liquidado` vía `action_conciliar()`, sin pasar por '
             'enviar/aprobar. Anticipo/Anticipo Viáticos, tras `aplicado` (dinero ya '
             'desembolsado), pueden seguir agregando facturas/pagos sobre sí mismos y llamar a '
             '`action_conciliar()` para llegar también a `liquidado` - no existe un registro '
             '"Liquidación" aparte (ver "Fusión: Liquidación deja de ser un tipo aparte" en el '
             'CLAUDE.md de este módulo).')

    # --- Campos absorbidos de la antigua account.payment.order.request (fusión Solicitud+Anticipo) ---
    external_ref = fields.Char(
        string='Referencia de Origen', readonly=True, copy=False,
        help='Referencia (nombre/secuencia) que tenía esta Orden de Pago en la instalación donde '
             'se creó originalmente, si llegó por sincronización.')
    origin = fields.Selection([
        ('local', 'Local'),
        ('synced', 'Sincronizada'),
    ], string='Origen', default='local', copy=False)
    origin_record_id = fields.Integer(
        string='ID en la instalación de origen', readonly=True, copy=False,
        help='Solo en el lado Procesador (`origin=\'synced\'`): el id real de este registro en '
             'la instalación Solicitante (Community) - junto con `origin_base_url`, arma '
             '`community_url`. No confundir con el id de este registro en ESTA base - son '
             'ids de dos bases de datos distintas.')
    origin_base_url = fields.Char(
        string='URL de la instalación de origen', readonly=True, copy=False,
        help='Solo en el lado Procesador: la URL base (`web.base.url`) de la instalación '
             'Solicitante que envió esta Orden, capturada al sincronizar.')
    enterprise_record_id = fields.Integer(
        string='ID en la instalación Procesadora', readonly=True, copy=False,
        help='Solo en el lado Solicitante (`tipo` sincronizable, `origin=\'local\'`): el id que '
             'la instalación Procesadora (Enterprise) le asignó a la copia de esta Orden, '
             'devuelto por `create_sync_record()` al sincronizar - junto con '
             '`company_id.payment_order_sync_url`, arma `enterprise_url`.')
    community_url = fields.Char(
        string='Ver en Community', compute='_compute_community_url',
        help='Link directo al registro de origen en Community - solo se puede armar del lado '
             'Procesador, con lo que la propia Orden llegó guardando al sincronizarse '
             '(`origin_record_id`/`origin_base_url`).')
    enterprise_url = fields.Char(
        string='Ver en Enterprise', compute='_compute_enterprise_url',
        help='Link directo a la copia de esta Orden en la instalación Procesadora - solo se '
             'puede armar del lado Solicitante, una vez que `_sync_to_enterprise()` haya '
             'guardado `enterprise_record_id` y la compañía tenga configurada '
             '`payment_order_sync_url`.')
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
    material_line_ids = fields.One2many(
        'account.payment.order.material.line', 'order_id', string='Líneas de Materiales')
    pagar_a = fields.Selection([
        ('jefe_tecnicos', 'Jefe de Técnicos'),
        ('proveedor_directo', 'Proveedor Directo'),
    ], string='Pagar a',
        help='Solo para Anticipo Materiales: a quién se le entrega el dinero al Aplicar - al '
             'jefe de técnicos (quien luego paga al proveedor) o directo al proveedor. No '
             'confundir con `proveedor_materiales_id`, que es siempre el proveedor real de los '
             'materiales sin importar a quién se le paga.')
    proveedor_materiales_id = fields.Many2one(
        'res.partner', string='Proveedor de Materiales',
        help='El proveedor real que surte los materiales de esta Orden - independiente de '
             '`pagar_a`/`partner_id` (quien recibe el pago puede ser el jefe de técnicos, '
             'mientras que el proveedor sigue siendo un contacto distinto). Requerido antes de '
             'generar la Orden de Compra.')
    purchase_order_ids = fields.One2many(
        'purchase.order', 'payment_order_id', string='Órdenes de Compra')
    purchase_order_count = fields.Integer(
        string='Órdenes de Compra', compute='_compute_purchase_order_count')
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

    @api.depends('tipo')
    def _compute_name(self):
        """El nombre real (secuencia OP/0001) se asigna en create() ANTES del insert (ver
        `create()`) - este compute solo cubre el placeholder de un registro `.new()` que
        todavía no se ha guardado."""
        for rec in self:
            if not rec.name:
                rec.name = 'Nueva Orden de Pago'

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        """Filtra las opciones del desplegable de `tipo` según la configuración de la compañía
        actual (`res.company._get_payment_order_allowed_tipos()`) - Fase 1 del proyecto:
        Community solo debe ofrecer "Anticipo Viáticos" al crear, Enterprise las demás.

        Deliberadamente solo toca lo que el CLIENTE ofrece elegir en un formulario nuevo, no la
        validación de create()/write() (que sigue aceptando cualquier valor del Selection
        completo) - una Orden sincronizada debe poder existir sin importar esta configuración.
        Ver el `help=` de cada campo booleano en res_company.py."""
        res = super().fields_get(allfields=allfields, attributes=attributes)
        tipo_desc = res.get('tipo')
        if tipo_desc and tipo_desc.get('selection'):
            allowed = self.env.company._get_payment_order_allowed_tipos()
            tipo_desc['selection'] = [
                (value, label) for value, label in tipo_desc['selection'] if value in allowed
            ]
        return res

    @api.constrains('tipo', 'journal_id')
    def _check_journal_id(self):
        """Pago Directo siempre necesita un Diario (antes se garantizaba con `required=True` a
        nivel de campo, cuando `journal_id` solo existía para ese tipo). Un Anticipo NO lo
        necesita todavía al crearse - lo llena el contable después de Aprobar (ver el `help=`
        de `journal_id` y `action_aplicar()`, que sí lo exige antes de aplicar)."""
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

    @api.depends('origin_record_id', 'origin_base_url')
    def _compute_community_url(self):
        for rec in self:
            if rec.origin_record_id and rec.origin_base_url:
                rec.community_url = (
                    f'{rec.origin_base_url}/web#id={rec.origin_record_id}'
                    f'&model=account.payment.order&view_type=form')
            else:
                rec.community_url = False

    @api.depends('enterprise_record_id', 'company_id.payment_order_sync_url')
    def _compute_enterprise_url(self):
        for rec in self:
            base_url = rec.company_id.payment_order_sync_url
            if rec.enterprise_record_id and base_url:
                rec.enterprise_url = (
                    f'{base_url.rstrip("/")}/web#id={rec.enterprise_record_id}'
                    f'&model=account.payment.order&view_type=form')
            else:
                rec.enterprise_url = False

    @api.onchange('analytic_account_id')
    def _onchange_analytic_account_id(self):
        for rec in self:
            if rec.analytic_account_id:
                rec.proyecto = rec.analytic_account_id.name

    @api.depends('viaticos_line_ids.total', 'material_line_ids.subtotal', 'anticipo_previo')
    def _compute_totales(self):
        for rec in self:
            subtotal = (sum(rec.viaticos_line_ids.mapped('total'))
                        + sum(rec.material_line_ids.mapped('subtotal')))
            rec.subtotal = subtotal
            rec.total_acreditar = subtotal - rec.anticipo_previo

    @api.depends('purchase_order_ids')
    def _compute_purchase_order_count(self):
        for rec in self:
            rec.purchase_order_count = len(rec.purchase_order_ids)

    @api.depends('factura_ids.amount_total', 'factura_ids.state', 'pago_ids.amount', 'pago_ids.state')
    def _compute_diferencia_conciliacion(self):
        for rec in self:
            total_facturas = sum(rec.factura_ids.filtered(
                lambda f: f.state == 'posted').mapped('amount_total'))
            total_pagos = sum(rec.pago_ids.filtered(
                lambda p: p.state in ('in_process', 'paid')).mapped('amount'))
            rec.diferencia_conciliacion = total_facturas - total_pagos

    @api.depends('tipo', 'state')
    def _compute_puede_conciliar(self):
        for rec in self:
            rec.puede_conciliar = (
                (rec.tipo in ANTICIPO_TIPOS and rec.state == 'aplicado')
                or (rec.tipo == 'pago_directo' and rec.state == 'borrador')
            )

    @api.onchange('viaticos_line_ids.total', 'material_line_ids.subtotal', 'anticipo_previo')
    def _onchange_sync_monto(self):
        self._sync_monto_desde_total_acreditar()

    def _sync_monto_desde_total_acreditar(self):
        """Para Anticipo Viáticos/Anticipo Materiales, `monto` no se captura a mano - hereda la
        suma de las pestañas de detalle (`total_acreditar`, vía `_compute_totales()`, que ya
        suma Viáticos + Materiales). Se llama desde el onchange (formulario web) y desde
        create()/write() (altas/ediciones por API o script, donde el onchange no corre)."""
        for rec in self:
            if rec.tipo in ('anticipo_viaticos', 'anticipo_materiales') \
                    and rec.monto != rec.total_acreditar:
                rec.monto = rec.total_acreditar

    @api.onchange('pagar_a')
    def _onchange_pagar_a(self):
        """Solo Anticipo Materiales: 'jefe_tecnicos' sugiere/mantiene el contacto del jefe (mismo
        criterio ya usado por Anticipo Viáticos); 'proveedor_directo' limpia `partner_id` para
        que el contable elija a mano el contacto real del proveedor, sin domain de empleado."""
        if self.tipo != 'anticipo_materiales':
            return
        if self.pagar_a == 'jefe_tecnicos':
            if not self.partner_id or not self.partner_id.employee:
                self.partner_id = self.env['hr.employee'].search(
                    [('user_id', '=', self.env.user.id)], limit=1).work_contact_id
        elif self.pagar_a == 'proveedor_directo' and self.partner_id and self.partner_id.employee:
            self.partner_id = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('tipo', 'anticipo') in (
                    'anticipo', 'anticipo_viaticos', 'anticipo_materiales', 'pago_directo') \
                    and not vals.get('name'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'account.payment.order.sequence') or '/'
            self._resolve_employee_enterprise_ref(vals)
            self._resolve_company_enterprise_ref(vals)
            self._resolve_analytic_enterprise_ref(vals)
            self._fill_derived_vals_from_employee(vals)
            self._fill_derived_vals_from_analytic_account(vals)
        records = super().create(vals_list)
        records._sync_monto_desde_total_acreditar()
        return records

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
                # Anti-suplantación, solo para Anticipo Viáticos - partner_id de un Pago
                # Directo/Anticipo normal debe seguir siendo libremente editable (nunca tuvo
                # esta restricción). employee_id (calculado) se revisa también por defensa en
                # profundidad.
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
        res = super().write(vals)
        if any(k in vals for k in ('viaticos_line_ids', 'material_line_ids', 'anticipo_previo', 'tipo')):
            self._sync_monto_desde_total_acreditar()
        return res

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
            if rec.tipo == 'anticipo_materiales' and not rec.material_line_ids:
                raise UserError(self.env._(
                    'Agregue al menos una línea de materiales antes de enviar la orden.'))
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
            # Enviada -> Borrador requiere el mismo permiso que aprobar/rechazar (el
            # solicitante -ej. Jefe de técnicos- no debe poder retirar en silencio una Orden
            # que ya está en revisión). Rechazada -> Borrador se deja SIN este gate a propósito:
            # es el camino normal para que el propio solicitante corrija y reenvíe algo que ya
            # fue rechazado, no una acción que necesite permiso especial.
            if rec.state == 'enviado':
                rec._check_is_approver()
            rec.write({
                'state': 'borrador',
                'approved_by_id': False,
                'rejected_by_id': False,
                'reject_reason': False,
            })

    def action_cancel(self):
        """Cancela un Anticipo que TODAVÍA no tiene ningún efecto contable real (antes de
        Aplicar) - solo cambia el estado, no revierte nada. Bloqueado a propósito desde
        `aplicado`/`liquidado` en adelante (ya existe un pago y/o un asiento reales) - usa
        `action_cancelar_anticipo_aplicado()`/`action_cancelar()` para esos casos, que sí
        revierten el efecto contable correspondiente. Antes de este chequeo, el único freno
        contra llamar esto sobre un Anticipo ya Aplicado/Liquidado era que el botón estaba
        oculto en la vista - no una validación real en Python."""
        for rec in self:
            if rec.tipo not in ANTICIPO_TIPOS:
                raise UserError(self.env._('Cancelar (Anticipo) solo aplica a tipo Anticipo.'))
            if rec.state not in ('borrador', 'enviado', 'aprobado', 'rechazado'):
                raise UserError(self.env._(
                    'No se puede cancelar así un Anticipo ya Aplicado/Liquidado - usa el botón '
                    '"Cancelar" correspondiente a ese estado, que sí revierte el pago/asiento.'))
            rec.state = 'cancelado'

    def action_cancelar_anticipo_aplicado(self):
        """Cancela/revierte un Anticipo YA Aplicado (pago real ya contabilizado) - a diferencia
        de `action_cancel()` (sin restricción de grupo, pero solo visible ANTES de aplicar, ver
        la vista), esto deshace un pago real, así que está restringido a Gerente igual que
        `action_cancelar()` (que deshace la conciliación de un Anticipo/Pago Directo ya
        Liquidado). Exige `state == 'aplicado'` específicamente - si el Anticipo ya está
        Liquidado, primero hay que usar `action_cancelar()` para regresarlo a `aplicado`."""
        self.ensure_one()
        if self.tipo not in ANTICIPO_TIPOS:
            raise UserError(self.env._(
                'Esta acción solo aplica a Anticipo/Anticipo Viáticos.'))
        if self.state != 'aplicado':
            raise UserError(self.env._(
                'Solo se puede cancelar así un Anticipo ya Aplicado - use el botón "Cancelar" '
                'normal para uno que todavía no se ha aplicado, o revierte primero su '
                'Liquidación si ya está Liquidado.'))
        self._check_es_administrador_contable()
        for pago in self.pago_ids.filtered(lambda p: p.state in ('in_process', 'paid')):
            for line in pago.move_id.line_ids:
                if line.reconciled:
                    line.remove_move_reconcile()
            pago.action_cancel()
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
            'tipo': self.tipo,
            'external_ref': self.name,
            'origin': 'synced',
            # Ids "de vuelta" hacia esta base - deliberadamente SÍ son ids (a diferencia de
            # employee_enterprise_ref/etc., que se resuelven como FK reales del otro lado, este
            # nunca se usa para buscar/vincular nada - solo arma un link de texto
            # (`community_url`) que un usuario puede clickear, así que no hay riesgo de
            # "id que no significa nada allá" siendo tratado como una relación real.
            'origin_record_id': self.id,
            'origin_base_url': self.get_base_url(),
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
            'material_line_ids': [
                (0, 0, {
                    'product_name': line.product_name or '',
                    'description': line.description or '',
                    'uom_name': line.uom_name or '',
                    'qty': line.qty,
                    'estimated_price': line.estimated_price,
                    'vendor_name': line.vendor_name or '',
                })
                for line in self.material_line_ids
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
                    'enterprise_record_id': int(remote_id),
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
        """Neteo de facturas contra pagos, terminando en `state='liquidado'`. Aplica a Pago
        Directo (desde `borrador`, sin `action_aplicar()` de por medio) y a Anticipo/Anticipo
        Viáticos (desde `aplicado` - el mismo registro que ya recibió el desembolso original
        vía `action_aplicar()` ahora agrega sus propias facturas y se concilia sobre sí mismo,
        sin crear una Liquidación aparte - ver "Fusión: Liquidación deja de ser un tipo aparte"
        en el CLAUDE.md de este módulo)."""
        self.ensure_one()
        if self.tipo not in ANTICIPO_TIPOS + ('pago_directo',):
            raise UserError(self.env._(
                'Conciliar solo aplica a órdenes de tipo Anticipo o Pago Directo.'))
        if self.tipo in ANTICIPO_TIPOS and self.state != 'aplicado':
            raise UserError(self.env._(
                'Solo se puede Conciliar/Liquidar un Anticipo ya Aplicado.'))
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
                    '(a diferencia de un Anticipo, no admite Cuenta de Ajuste). Corrige el '
                    'monto del pago o registra esto como un Anticipo en su lugar.', '%'))
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
                # Contacto = el solicitante de la Orden de Pago (`partner_id`) - a diferencia de
                # las demás líneas (que traen su propio `partner_id` real de cada factura/pago),
                # esta línea de ajuste no viene de ningún documento, así que sin esto quedaba sin
                # contacto.
                'partner_id': self.partner_id.id,
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

        self.write({'move_id': move.id, 'state': 'liquidado'})
        return True

    def _deshacer_conciliacion(self):
        """Unreconcilia y cancela `move_id` (el asiento regularizador de `action_conciliar()`),
        y regresa `state` según el tipo - Pago Directo a `borrador`, Anticipo/Anticipo Viáticos
        a `aplicado` (el desembolso original ya ocurrió y sigue siendo válido, solo se deshace
        la parte de la liquidación). Compartido entre `action_cancelar()` (manual, exige permiso
        de Administrador) y `_reaccionar_a_documento_desconciliado()` (automático, sin ese
        permiso - ver ahí el porqué)."""
        self.ensure_one()
        if self.move_id:
            for line in self.move_id.line_ids:
                if line.reconciled:
                    line.remove_move_reconcile()
            self.move_id.button_cancel()
            self.move_id.unlink()
        nuevo_estado = 'aplicado' if self.tipo in ANTICIPO_TIPOS else 'borrador'
        self.write({'move_id': False, 'state': nuevo_estado})

    def action_cancelar(self):
        """Deshace la conciliación (`action_conciliar()`) a pedido manual del Administrador
        Contable - ver `_deshacer_conciliacion()` para el detalle de qué hace."""
        self.ensure_one()
        if self.tipo not in ANTICIPO_TIPOS + ('pago_directo',):
            raise UserError(self.env._(
                'Cancelar solo aplica a órdenes de tipo Anticipo o Pago Directo.'))
        self._check_es_administrador_contable()
        self._deshacer_conciliacion()
        return True

    def _reaccionar_a_documento_desconciliado(self, documentos, nuevo_state_label):
        """Se llama desde account_move.py/account_payment.py cuando una factura o pago YA
        conciliado (parte de `factura_ids`/`pago_ids` de una Orden en `state='liquidado'`)
        cambia de estado por fuera de esta Orden - típicamente "Restablecer a Borrador" desde
        Contabilidad > Facturas/Pagos. Esa conciliación ya no es válida (una de sus líneas ya no
        está posteada), así que se deshace automáticamente (`_deshacer_conciliacion()` - mismo
        efecto que el botón "Cancelar", incluyendo el regreso de `state` a `aplicado`/`borrador`
        según el tipo) y se deja constancia en el chatter - pedido explícito del usuario:
        "considero prudente que... cambie el estado de la orden de pago de liquidado a
        aplicado... y que todo quede plasmado en el chatter".

        Deliberadamente SIN `_check_es_administrador_contable()` - quien reseteó la factura/pago
        ya tenía el permiso de Contabilidad correspondiente para hacer ESO; esto es solo una
        consecuencia automática de esa acción sobre la Orden, no una acción nueva que alguien
        esté ejecutando directamente sobre la Orden."""
        self.ensure_one()
        if self.state != 'liquidado':
            return
        nombres = ', '.join(str(nombre) for nombre in documentos.mapped('name') if nombre)
        self._deshacer_conciliacion()
        self.message_post(body=Markup(
            '⚠️ <b>Conciliación deshecha automáticamente</b>: %(docs)s pasó a "%(nuevo)s" fuera '
            'de esta Orden - la Liquidación ya no era válida, se deshizo y la Orden regresó a '
            '"%(estado)s".') % {
                'docs': nombres, 'nuevo': nuevo_state_label, 'estado': dict(
                    self._fields['state'].selection).get(self.state, self.state),
            })

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
        if self.tipo not in ANTICIPO_TIPOS + ('pago_directo',):
            raise UserError(self.env._(
                'Crear Pago solo aplica a órdenes de tipo Anticipo o Pago Directo.'))
        if self.tipo in ANTICIPO_TIPOS and self.state != 'aplicado':
            raise UserError(self.env._(
                'Solo se puede crear un pago adicional para un Anticipo ya Aplicado.'))
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

        payment_vals = {
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': self.partner_id.id,
            'amount': faltante,
            'currency_id': self.currency_id.id,
            'journal_id': self.journal_id.id,
            'date': self.fecha,
            'memo': self.name,
            'payment_order_id': self.id,
        }
        if self.payment_method_line_id:
            payment_vals['payment_method_line_id'] = self.payment_method_line_id.id
        payment = self.env['account.payment'].create(payment_vals)
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
        if self.tipo == 'anticipo_materiales' and not self.pagar_a:
            raise UserError(self.env._(
                'Define a quién se le paga (Jefe de Técnicos o Proveedor Directo) antes de '
                'aplicar.'))

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
            # Vinculado a pago_ids (relación inversa vía payment_order_id) - no hay un campo
            # dedicado tipo "Pago del Anticipo" (existió, se retiró: `pago_ids` ya cubre el
            # mismo caso genéricamente, incluyendo un eventual pago adicional - ver
            # action_crear_pago()/CLAUDE.md).
            'payment_order_id': self.id,
        }
        if self.payment_method_line_id:
            payment_vals['payment_method_line_id'] = self.payment_method_line_id.id
        payment = self.env['account.payment'].create(payment_vals)
        payment.action_post()
        self.write({'state': 'aplicado'})

        # Dos avisos posibles, ninguno bloquea: si el contacto ya tiene otro Anticipo aplicado
        # sin liquidar todavía, y/o si esta Orden ya cubre el 100% de facturas adjuntas (pudo
        # haber sido un Pago Directo). Se encadenan con el mecanismo nativo `next` de
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

    def action_generar_orden_compra(self):
        """Genera UNA Orden de Compra (RFQ, en `draft`) con las líneas de `material_line_ids`
        que ya tienen un `product_id` resuelto en Enterprise y todavía no generaron una línea de
        compra - las que no tienen producto se omiten en silencio (esa ausencia ES la señal de
        "ya hay existencia propia, no comprar" - ver el modelo de línea), nunca se bloquea por
        ellas. Confirmar/enviar la Orden de Compra es el flujo nativo de la app Compras, no se
        reimplementa aquí."""
        self.ensure_one()
        if self.tipo != 'anticipo_materiales':
            raise UserError(self.env._(
                'Generar Orden de Compra solo aplica a órdenes de tipo Anticipo Materiales.'))
        if self.state != 'aplicado':
            raise UserError(self.env._(
                'Solo se puede generar la Orden de Compra de una Orden ya Aplicada.'))
        self._check_es_administrador_contable()
        if not self.proveedor_materiales_id:
            raise UserError(self.env._('Define el Proveedor de Materiales antes de generar la Orden de Compra.'))
        lineas = self.material_line_ids.filtered(
            lambda l: l.product_id and not l.purchase_order_line_id)
        if not lineas:
            raise UserError(self.env._(
                'No hay líneas de materiales con Producto asignado pendientes de comprar - '
                'asigna un Producto (Enterprise) a las líneas que hay que comprar, o revisa si '
                'ya se generó la Orden de Compra para todas.'))
        analytic_distribution = (
            {str(self.analytic_account_id.id): 100.0} if self.analytic_account_id else False)
        purchase_order = self.env['purchase.order'].create({
            'partner_id': self.proveedor_materiales_id.id,
            'company_id': self.company_id.id,
            'origin': self.name,
            'payment_order_id': self.id,
            'order_line': [
                (0, 0, {
                    'product_id': linea.product_id.id,
                    'name': linea.description or linea.product_name,
                    'product_qty': linea.qty,
                    'product_uom_id': linea.product_id.uom_id.id,
                    'price_unit': linea.estimated_price,
                    'analytic_distribution': analytic_distribution,
                })
                for linea in lineas
            ],
        })
        for linea, po_line in zip(lineas, purchase_order.order_line):
            linea.purchase_order_line_id = po_line.id
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'res_id': purchase_order.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_purchase_orders(self):
        """Botón inteligente 'Órdenes de Compra' - abre el form directo si solo hay una (caso
        normal, ya que `action_generar_orden_compra()` agrupa todo en una sola OC por Orden de
        Pago), o una lista si por algún motivo hay más de una (ej. se generó en más de una
        pasada porque algunas líneas no tenían Producto todavía la primera vez)."""
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'name': self.env._('Órdenes de Compra'),
        }
        if len(self.purchase_order_ids) == 1:
            action.update({'view_mode': 'form', 'res_id': self.purchase_order_ids.id})
        else:
            action.update({
                'view_mode': 'list,form',
                'domain': [('id', 'in', self.purchase_order_ids.ids)],
            })
        return action

    @api.model
    def _find_anticipos_sin_liquidar(self, partner, exclude=None):
        """Anticipos de este contacto que ya están Aplicados (dinero entregado) pero todavía no
        han llegado a `state='liquidado'` - se usa para avisar antes de entregar un Anticipo
        nuevo a alguien que ya tiene uno pendiente de liquidar, sin bloquear la operación (puede
        ser intencional: viáticos de dos viajes distintos, por ejemplo). Desde que Liquidación
        dejó de ser un tipo/registro aparte, `state='aplicado'` YA significa "sin liquidar" por
        sí solo - no hace falta ningún filtro adicional."""
        domain = [
            ('tipo', 'in', ANTICIPO_TIPOS),
            ('state', '=', 'aplicado'),
            ('partner_id', '=', partner.id),
        ]
        if exclude:
            domain.append(('id', '!=', exclude.id))
        return self.search(domain)

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

