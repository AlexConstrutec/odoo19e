import logging

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from ..tools.enterprise_sync_api import (
    EnterpriseConnectionError, EnterpriseSyncError, create_sync_record,
    link_gasto_documents_in_enterprise)

_logger = logging.getLogger(__name__)

APPROVER_GROUP_XMLID = 'construtec_account_payment_order_19.group_payment_order_approver'
APPROVER_MEDIO_GROUP_XMLID = 'construtec_account_payment_order_19.group_payment_order_approver_medio'
APPROVER_ALTO_GROUP_XMLID = 'construtec_account_payment_order_19.group_payment_order_approver_alto'
# Los tres comparten el mismo ciclo enviado/aprobado/rechazado/aplicado (decisión explícita del
# usuario: "ambos tipos comparten el mismo flujo", extendida a Materiales por el mismo criterio)
# - `anticipo_viaticos`/`anticipo_materiales` son los que se ven en Community (traen sus propias
# líneas de detalle + sync); `anticipo` a secas sigue existiendo para un anticipo que un contable
# arma directo en Enterprise, sin relación a viáticos ni materiales.
ANTICIPO_TIPOS = ('anticipo', 'anticipo_viaticos', 'anticipo_materiales')
# Pago Directo ahora también se puede crear/enviar desde Community (una Solicitud de Pago a
# Proveedor vinculada a un Documento SAT real, ya factura o todavía pendiente - ver
# factura_mirror_ids/_check_factura_mirror_disponible más abajo), reusando el mismo ciclo
# enviado/aprobado que ya tenían los tres de ANTICIPO_TIPOS - a
# diferencia de esos tres, Pago Directo nunca pasa por `aplicado` (va directo de `aprobado` a
# `liquidado` vía action_conciliar(), igual que su camino clásico de `borrador` a `liquidado`
# cuando se crea directo en Enterprise, sin pasar por Community).
SUBMITTABLE_TIPOS = ANTICIPO_TIPOS + ('pago_directo',)
# Facturas de gastos (2026-10-17): para liquidar un anticipo de Viáticos hacen falta las facturas con
# las que el técnico gastó. Desde Community las vincula desde Borrador (viajan al enviar) y también
# DESPUÉS de enviar, hasta que la requisición se liquide (ver gasto_mirror_ids). En Borrador se
# pueden quitar libremente; ya enviada, solo se agregan (Enterprise ya las reclamó).
# Materiales (2026-10-19): misma pestaña, para las facturas del proveedor que se compró con el anticipo.
GASTOS_TIPOS = ('anticipo_viaticos', 'anticipo_materiales')
# Cuenta puente de cada tipo de anticipo (código del plan de cuentas, 2026-10-19, pedido del usuario):
# se pone sola al aprobar/aplicar y no se edita a mano para estos tipos.
CUENTA_ANTICIPO_POR_TIPO = {
    'anticipo_materiales': '110204',  # Anticipo a Proveedores y Subcontratistas
    'anticipo_viaticos': '110208',  # Anticipo Viáticos por Liquidar
}
GASTOS_STATES_EDITABLES = ('borrador', 'enviado', 'en_compras', 'aprobado', 'aplicado')
# Gestión de Compras (2026-10-21): en Enterprise, el grupo nativo de la app Compras gestiona las
# Solicitudes de Materiales entre Aprobar y Aplicar (cotizaciones, precios, Orden de Compra,
# factura) y las entrega a Contabilidad con "Fin de intervención de Compras".
COMPRAS_GROUP_XMLID = 'purchase.group_purchase_user'


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
    _description = 'Requisición de Pago (Anticipo / Pago Directo)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fecha desc'

    tipo = fields.Selection([
        ('anticipo', 'Anticipo'),
        ('anticipo_viaticos', 'Viáticos'),
        ('anticipo_materiales', 'Materiales'),
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
    factura_mirror_ids = fields.Many2many(
        'construtec.sat.invoice.mirror', string='Facturas (Catálogo SAT)',
        help='Lo que un jefe de técnicos en Community realmente elige para un Pago Directo - '
             'Documentos SAT reales de Enterprise (ya factura, o todavía pendientes de '
             'convertir), vía el mirror de solo lectura de construtec_sat_catalog_sync_19 '
             '(Community no tiene construtec.sat.document/account.move reales que vincular). Al '
             'Enviar, sus `origin_id` (siempre el id del Documento SAT, NUNCA el de la factura - '
             'decisión explícita del usuario: "de Enterprise a Community solo deben copiarse los '
             'documentos SAT") viajan como `sat_document_ids` - Enterprise decide qué hacer con '
             'cada uno según su estado real (`_resolve_sat_document_ids()`, Enterprise-only, '
             'construtec_account_19): ya `convertido_factura` se vincula directo; `pendiente` se '
             'reclama y el Contador lo convierte a factura real al Aprobar. Sin efecto en '
             'Enterprise mismo (es_procesador=True) - ahí se usa `factura_ids` directo, como '
             'siempre.')
    gasto_mirror_ids = fields.Many2many(
        'construtec.sat.invoice.mirror', relation='account_payment_order_gasto_mirror_rel',
        column1='order_id', column2='mirror_id', string='Facturas de Gastos',
        domain=[('payment_state', '!=', 'paid')],
        help='Facturas (Documentos SAT) con las que el técnico gastó el anticipo de Viáticos - '
             'sirven para liquidarlo. Solo en Community. Se pueden agregar desde Borrador (viajan '
             'junto con la requisición al enviarla: `sat_document_ids`) y también después de '
             'enviarla, hasta que se liquide: ahí, al guardar, se avisan a Enterprise '
             '(`sync_gasto_documents_from_community()`). Enterprise las reclama y el Contador las '
             'convierte a factura real y las concilia contra el pago. Solo se aceptan facturas con '
             'saldo vigente (sin pago o pagadas parcialmente) que no estén vinculadas a otra '
             'requisición. En Borrador se pueden quitar; ya enviada no (Enterprise ya las '
             'reclamó).')
    # Cola de facturas de gastos (2026-10-21): al guardar se envían al instante; si la comunicación
    # con Enterprise falla quedan aquí y `_cron_retry_gasto_sync()` las reintenta.
    gasto_pendiente_ids = fields.Many2many(
        'construtec.sat.invoice.mirror', relation='account_payment_order_gasto_pendiente_rel',
        column1='order_id', column2='mirror_id', string='Facturas pendientes de enviar',
        readonly=True, copy=False,
        help='Facturas de gastos ya guardadas en Community que todavía NO llegaron a Enterprise '
             '(falló la comunicación, o la requisición aún no está allá). Se reintentan solas.')
    gasto_sync_state = fields.Selection([
        ('sincronizado', 'Enviadas a Enterprise'),
        ('pendiente', 'Pendiente de enviar'),
        ('error', 'Error de comunicación (se reintenta)'),
        ('rechazado', 'Rechazada por Enterprise'),
    ], string='Envío de facturas de gastos', readonly=True, copy=False)
    gasto_sync_error = fields.Text(string='Detalle del envío de facturas', readonly=True, copy=False)
    gasto_sync_date = fields.Datetime(string='Último envío de facturas', readonly=True, copy=False)
    gasto_sync_attempts = fields.Integer(string='Intentos de envío de facturas', readonly=True, copy=False)
    # Gestión de Compras (Solicitud de Materiales, Enterprise) - ver COMPRAS_GROUP_XMLID.
    cotizacion_attachment_ids = fields.Many2many(
        'ir.attachment', 'account_payment_order_cotizacion_rel', 'order_id', 'attachment_id',
        string='Cotizaciones', copy=False,
        help='Las cotizaciones que Compras recibió de los proveedores (una, dos o tres).')
    aprobado_por_gerente = fields.Boolean(
        string='Aprobada por Gerente', readonly=True, copy=False,
        help='Un Aprobador Nivel Alto (Gerente) ya aprobó esta requisición (al Aprobar o al '
             'autorizar el monto final de Compras).')
    requiere_aprobacion_gerente = fields.Boolean(
        string='Pendiente de autorización del Gerente', readonly=True, copy=False,
        help='Compras terminó, pero con los precios reales el total llegó al umbral de '
             'aprobación y falta la autorización de un Gerente (Nivel Alto).')
    compras_finalizado_por_id = fields.Many2one(
        'res.users', string='Compras finalizada por', readonly=True, copy=False)
    compras_finalizado_date = fields.Datetime(
        string='Fin de intervención de Compras', readonly=True, copy=False)
    partner_es_contrata = fields.Boolean(
        string='Es Contrata', compute='_compute_partner_es_contrata',
        inverse='_inverse_partner_es_contrata',
        help='Marca al proveedor de esta requisición como "contrata" (etiqueta "Contrata" de su '
             'contacto). Se aplica al guardar y Community lo envía a Enterprise. Solo aplica a '
             'Pago Directo.')
    partner_vat_actual = fields.Char(
        compute='_compute_partner_vat_actual',
        help='Auxiliar para el dominio de `factura_mirror_ids` - navegar `partner_id.vat` '
             'directo dentro de un `domain=` en string revienta en el cliente '
             '(`InvalidDomainError: partner_vat,=,`) en cuanto `partner_id` está vacío o su '
             '`vat` no está cargado todavía - bug real de producción (2026-09-29), mismo motivo '
             'documentado arriba para `available_payment_method_line_ids` '
             '(`journal_id.outbound_payment_method_line_ids`) - cualquier navegación por punto '
             'en un domain de vista necesita este mismo patrón de campo calculado intermedio, no '
             'solo las que atraviesan un Many2many.')
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
        ('en_compras', 'Gestión de Compras'),
        ('aprobado', 'Aprobado'),
        ('rechazado', 'Rechazado'),
        ('aplicado', 'Aplicado'),
        ('liquidado', 'Liquidado'),
        ('cancelado', 'Cancelado'),
        ('dividida', 'Dividida'),
    ], string='Estado', default='borrador', copy=False, tracking=True,
        help='`enviado`/`aprobado`/`rechazado` solo aplican a Anticipo/Anticipo Viáticos (el '
             'ciclo heredado de la antigua Solicitud de Pago, fusionada aquí). Pago Directo va '
             'directo de `borrador` a `liquidado` vía `action_conciliar()`, sin pasar por '
             'enviar/aprobar. Anticipo/Anticipo Viáticos, tras `aplicado` (dinero ya '
             'desembolsado), pueden seguir agregando facturas/pagos sobre sí mismos y llamar a '
             '`action_conciliar()` para llegar también a `liquidado` - no existe un registro '
             '"Liquidación" aparte (ver "Fusión: Liquidación deja de ser un tipo aparte" en el '
             'CLAUDE.md de este módulo). `dividida` es exclusivo de Anticipo Viáticos con '
             '"Depositar Directo a Técnicos" marcado - la Orden ORIGINAL nunca se envía ella '
             'misma como dinero real, queda en este estado solo como referencia hacia las '
             'Órdenes reales que sí se generaron (ver `ordenes_hijas_ids`/`lote_origen` y '
             '`_dividir_en_ordenes_por_tecnico()`) - deliberadamente distinto de `cancelado` '
             '(que significa "esto no va a pasar"), ya que aquí el pago SÍ ocurre, solo que en '
             'otras Órdenes.')

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
    ], string='Tipo de Cuenta', readonly=True,
        help='Se autocompleta desde la cuenta bancaria del empleado solicitante en Enterprise '
             '(mismo criterio que `cuenta_acreditar`/`banco`) - no editable a mano, para reducir '
             'campos que el jefe de técnicos/solicitante tendría que digitar cada vez. Si el '
             'empleado no tiene un Tipo de Cuenta configurado en su cuenta bancaria, queda vacío '
             'y bloquea Enviar (Anticipo Viáticos) hasta que RR.HH. lo complete ahí.')
    banco = fields.Char(string='Banco', readonly=True)
    periodo_del = fields.Date(string='Del')
    periodo_al = fields.Date(string='Al')
    observaciones = fields.Text(string='Observaciones / Instrucciones')
    viaticos_line_ids = fields.One2many(
        'account.payment.order.viatico.line', 'order_id', string='Líneas de Viáticos')
    depositar_directo_tecnicos = fields.Boolean(
        string='¿Depositar Directo a Técnicos?',
        help='Solo para Anticipo Viáticos: al Enviar, en vez de mandar esta Orden con el jefe '
             'de técnicos como Contacto/beneficiario del depósito, se genera una Orden de Pago '
             'independiente POR CADA técnico de la lista de Viáticos (ver '
             '`_dividir_en_ordenes_por_tecnico()`), con ese técnico como Contacto real - el '
             'depósito llega a su propia cuenta, no a la del jefe. Esta Orden original queda '
             'entonces `cancelado`, solo como referencia (ver `ordenes_hijas_ids`). Editable '
             'libremente mientras la Orden esté en Borrador.')
    orden_padre_id = fields.Many2one(
        'account.payment.order', string='Requisición Original', readonly=True, copy=False,
        help='Si esta Orden se generó al dividir un Anticipo Viáticos con "Depositar Directo a '
             'Técnicos" marcado, aquí queda la Orden original de la que salió.')
    ordenes_hijas_ids = fields.One2many(
        'account.payment.order', 'orden_padre_id', string='Requisiciones Generadas',
        help='Si esta Orden se dividió ("Depositar Directo a Técnicos"), aquí quedan las '
             'Órdenes independientes que se generaron, una por técnico.')
    ordenes_hijas_count = fields.Integer(
        string='Cantidad de Requisiciones Generadas', compute='_compute_ordenes_hijas_count')
    lote_origen = fields.Char(
        string='Lote de Origen', copy=False, readonly=True,
        help='`name` (nunca un id) de la Orden original que se dividió en Órdenes por técnico '
             '("Depositar Directo a Técnicos") - viaja como TEXTO plano hacia Enterprise vía '
             '`_prepare_sync_vals()`, igual que `external_ref` - la Orden original nunca se '
             'sincroniza ella misma (queda `cancelado` en Community), así que sin esto no '
             'habría forma de saber, del lado Enterprise, que varias Órdenes independientes '
             'pertenecen al mismo lote de depósito masivo. Vacío para una Orden que nunca fue '
             'generada por una división.')
    material_line_ids = fields.One2many(
        'account.payment.order.material.line', 'order_id', string='Líneas de Materiales')
    pagar_a = fields.Selection([
        ('jefe_tecnicos', 'Jefe de Técnicos'),
        ('proveedor_directo', 'Proveedor Directo'),
    ], string='Pagar a',
        help='Solo para Anticipo Materiales: a quién se le entrega el dinero al Aplicar - al '
             'jefe de técnicos (`partner_id`, "Contacto", quien luego paga al proveedor) o '
             'directo al proveedor (`proveedor_materiales_id`, "Proveedor de Materiales" - ver '
             '`_resolve_beneficiario_pago()`). `partner_id` nunca se limpia por elegir aquí - '
             'siempre identifica a quien sube la Orden, sin importar a quién se le paga.')
    proveedor_materiales_catalogo_id = fields.Many2one(
        'construtec.materials.vendor.mirror', string='Proveedor Sugerido (Catálogo)',
        help='Elegido por el jefe de técnicos (o resuelto/creado automáticamente por "Cargar '
             'Cotización") contra el Catálogo de Proveedores (construtec_sat_catalog_sync_19), '
             'ya no como texto libre. Es un id local de Community - nunca viaja tal cual hacia '
             'Enterprise (otra base de datos); `proveedor_materiales_name` (ver abajo) se deriva '
             'de aquí y es lo que realmente viaja por sincronización.')
    proveedor_materiales_name = fields.Char(
        string='Proveedor Sugerido', readonly=True,
        help='Derivado de `proveedor_materiales_catalogo_id` (ver '
             '`_sync_proveedor_materiales_name()`) - viaja por sincronización igual que '
             '`vendor_name` de cada línea, nunca se trata como relación (Community/Enterprise '
             'son bases distintas). Visible también en Enterprise (de solo lectura) - pedido '
             'explícito del usuario, quiere ver el nombre tal como llegó de Community, además '
             'del contacto real ya resuelto en `proveedor_materiales_id`.')
    proveedor_materiales_id = fields.Many2one(
        'res.partner', string='Proveedor de Materiales',
        help='El proveedor real que surte los materiales de esta Orden - independiente de '
             '`pagar_a`/`partner_id` (quien recibe el pago puede ser el jefe de técnicos, '
             'mientras que el proveedor sigue siendo un contacto distinto). Requerido antes de '
             'generar la Orden de Compra, y también antes de Aplicar si `pagar_a == '
             '\'proveedor_directo\'` (ver `_resolve_beneficiario_pago()`). Se autosugiere '
             '(`_autosugerir_proveedor_materiales_id()`) buscando un contacto existente con el '
             'mismo nombre que `proveedor_materiales_name` - nunca crea uno nuevo, y nunca pisa '
             'una elección ya hecha a mano.')
    purchase_order_ids = fields.One2many(
        'purchase.order', 'payment_order_id', string='Órdenes de Compra')
    purchase_order_count = fields.Integer(
        string='Cantidad de Órdenes de Compra', compute='_compute_purchase_order_count')
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
        """El nombre real (secuencia RP/0001) se asigna en create() ANTES del insert (ver
        `create()`) - este compute solo cubre el placeholder de un registro `.new()` que
        todavía no se ha guardado."""
        for rec in self:
            if not rec.name:
                rec.name = 'Nueva Requisición de Pago'

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
        """Un Pago Directo creado directo en Enterprise (sin pasar por Community) sigue sin
        poder guardarse sin Diario, igual que siempre. Un Pago Directo que SÍ viene de una
        Solicitud sincronizada desde Community (ver factura_mirror_ids/action_submit()) no
        necesita Diario todavía al crearse/enviarse - lo llena el contable después de Aprobar,
        exactamente igual que ya funciona para un Anticipo (ver `action_conciliar()`, que sí lo
        exige antes de Conciliar). No hay forma de distinguir el origen a este nivel, así que se
        relaja para AMBOS caminos de Pago Directo - mismo criterio ya usado para Anticipo."""
        for rec in self:
            if rec.tipo not in SUBMITTABLE_TIPOS and not rec.journal_id:
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

    @api.depends('partner_id.category_id')
    def _compute_partner_es_contrata(self):
        for rec in self:
            rec.partner_es_contrata = bool(rec.partner_id) and rec.partner_id.sudo()._es_contrata_actual()

    def _inverse_partner_es_contrata(self):
        """Solo Pago Directo: aplica el check a la etiqueta "Contrata" del proveedor (el contacto
        decide si hay algo que cambiar y la envía a Enterprise - ver `res.partner.write()`)."""
        for rec in self.filtered(lambda r: r.tipo == 'pago_directo' and r.partner_id):
            rec.partner_id.sudo().es_contrata = rec.partner_es_contrata

    @api.depends('partner_id.vat')
    def _compute_partner_vat_actual(self):
        for rec in self:
            rec.partner_vat_actual = rec.partner_id.vat

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
                # Bug real (2026-09-18): estas 3 líneas leían `rec.employee_id` (SIN sudo) en vez
                # de la variable `employee` ya preparada arriba - para un solicitante sin
                # hr.group_hr_user, cualquier lectura de un campo de hr.employee sin sudo() hace
                # que Odoo intente resolverlo vía hr.employee.public (el "perfil público" que no
                # tiene ninguno de los campos custom de Datos Personales agregados 2026-09-16/17)
                # y truena con "Error de acceso" - reportado por el usuario con una captura real
                # de producción al presionar "Depositar a Mí".
                rec.cuenta_acreditar = employee.cuenta_bancaria or rec.cuenta_acreditar
                rec.banco = employee.banco_nombre or rec.banco
                rec.tipo_cuenta = employee.tipo_cuenta or rec.tipo_cuenta
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

    @api.depends('ordenes_hijas_ids')
    def _compute_ordenes_hijas_count(self):
        for rec in self:
            rec.ordenes_hijas_count = len(rec.ordenes_hijas_ids)

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
                # 'aprobado': Pago Directo pedido desde Community (bug real 2026-10-14: sin esto
                # una requisición Aprobada se quedaba sin "Liquidar"/"Crear Pago").
                or (rec.tipo == 'pago_directo' and rec.state in ('borrador', 'aprobado'))
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

    @api.onchange('proveedor_materiales_catalogo_id')
    def _onchange_proveedor_materiales_catalogo_id(self):
        self._sync_proveedor_materiales_name()

    def _sync_proveedor_materiales_name(self):
        """`proveedor_materiales_name` (el texto que viaja a Enterprise vía
        `_prepare_sync_vals()`) se deriva del proveedor elegido en Community en
        `proveedor_materiales_catalogo_id` (Many2one al Catálogo de Proveedores,
        construtec_sat_catalog_sync_19), un id local de Community sin significado en Enterprise.
        Se llama desde el onchange (formulario web) y desde create()/write() (altas/ediciones por
        API o script, donde el onchange no corre).

        Solo ESCRIBE cuando `proveedor_materiales_catalogo_id` sí tiene un valor - nunca lo
        limpia a vacío cuando no lo tiene. Bug real corregido (2026-09-02): la versión anterior
        también limpiaba `proveedor_materiales_name` a `''` cuando `proveedor_materiales_catalogo_id`
        estaba vacío, sin importar el motivo - y en Enterprise, `proveedor_materiales_catalogo_id`
        SIEMPRE está vacío (ese campo nunca viaja por sincronización, es puramente local a
        Community), así que esta misma llamada, disparada por CUALQUIER create()/write() del
        registro sincronizado en Enterprise, borraba en el acto el texto real que acababa de
        llegar por `_prepare_sync_vals()`. `proveedor_materiales_name` queda con lo que ya tenía
        cuando no hay catálogo elegido - correcto tanto en Enterprise (conserva lo sincronizado)
        como en Community (si el jefe de técnicos limpia el desplegable, el texto anterior queda
        obsoleto pero no se pierde nada real)."""
        for rec in self:
            if rec.proveedor_materiales_catalogo_id \
                    and rec.proveedor_materiales_name != rec.proveedor_materiales_catalogo_id.name:
                rec.proveedor_materiales_name = rec.proveedor_materiales_catalogo_id.name

    def _autosugerir_proveedor_materiales_id(self):
        """Enterprise, Anticipo Materiales: si `proveedor_materiales_id` (el contacto real, a
        quien se le va a pagar) está vacío y ya llegó un `proveedor_materiales_name` (texto,
        sincronizado desde Community o capturado a mano), intenta resolverlo contra un contacto
        YA EXISTENTE - primero por nombre EXACTO (`=ilike`, insensible a mayúsculas); si no hay
        ninguno exacto, intenta uno "parecido" (`ilike`, substring) pero **solo si resulta en un
        único candidato** - nunca adivina entre varios resultados ambiguos, en cuyo caso queda
        vacío para que el contable lo resuelva a mano (mismo criterio: nunca crea un contacto
        nuevo, a diferencia del Catálogo de Proveedores en Community - un `res.partner` mal
        creado en Enterprise sí tiene consecuencias reales de compras/facturación).

        Se llama automáticamente al llegar/cambiar `proveedor_materiales_name` (create()/write() -
        ver más abajo, dispara justo cuando Community envía/sincroniza la Orden) y de nuevo como
        respaldo dentro de `action_approve()`/`action_aplicar()`/`action_crear_pago()` (self-heal
        para Órdenes ya existentes antes de que este código corriera la primera vez). Solo
        rellena si está vacío - nunca pisa una elección ya hecha a mano."""
        Partner = self.env['res.partner']
        for rec in self:
            if not rec.es_procesador or rec.tipo != 'anticipo_materiales' \
                    or rec.proveedor_materiales_id or not rec.proveedor_materiales_name:
                continue
            nombre = rec.proveedor_materiales_name.strip()
            domain_empresa = [('company_id', 'in', [rec.company_id.id, False])]
            exactos = Partner.search([('name', '=ilike', nombre)] + domain_empresa, limit=2)
            if len(exactos) == 1:
                rec.proveedor_materiales_id = exactos.id
                continue
            if exactos:
                continue  # exacto ambiguo (2+ contactos con el mismo nombre) - no adivina
            parecidos = Partner.search([('name', 'ilike', nombre)] + domain_empresa, limit=2)
            if len(parecidos) == 1:
                rec.proveedor_materiales_id = parecidos.id

    def _resolve_beneficiario_pago(self):
        """A quién se le paga de verdad al Aplicar/Crear Pago - normalmente `partner_id` (el
        Contacto, que para Anticipo Materiales siempre identifica a quien sube la Orden, nunca
        al proveedor - ver `_onchange_pagar_a()`). Única excepción: Anticipo Materiales con
        `pagar_a == 'proveedor_directo'` - ahí el dinero va directo a `proveedor_materiales_id`
        (el proveedor real), no a quien subió la solicitud."""
        self.ensure_one()
        if self.tipo == 'anticipo_materiales' and self.pagar_a == 'proveedor_directo':
            return self.proveedor_materiales_id
        return self.partner_id

    @api.onchange('pagar_a')
    def _onchange_pagar_a(self):
        """Solo Anticipo Materiales: sugiere/mantiene el contacto del jefe de técnicos (mismo
        criterio ya usado por Anticipo Viáticos) sin importar el valor de `pagar_a` - `partner_id`
        (el "Contacto") siempre identifica a quien sube/solicita la Orden, nunca al proveedor.

        Antes, 'proveedor_directo' limpiaba `partner_id` para forzar a elegir ahí el contacto
        real del proveedor - decisión revertida (2026-09-02, pedido explícito del usuario): un
        técnico siempre es quien sube esta información, así que el Contacto no debía borrarse
        por elegir a quién se le paga. El proveedor real que recibe el pago cuando `pagar_a ==
        'proveedor_directo'` es `proveedor_materiales_id` - ver `_resolve_beneficiario_pago()`,
        usado en `action_aplicar()`/`action_crear_pago()`."""
        if self.tipo != 'anticipo_materiales':
            return
        if not self.partner_id or not self.partner_id.employee:
            self.partner_id = self.env['hr.employee'].search(
                [('user_id', '=', self.env.user.id)], limit=1).work_contact_id

    @api.model_create_multi
    def create(self, vals_list):
        sat_document_ids_list = [vals.pop('sat_document_ids', None) for vals in vals_list]
        for vals in vals_list:
            if vals.get('tipo', 'anticipo') in (
                    'anticipo', 'anticipo_viaticos', 'anticipo_materiales', 'pago_directo') \
                    and vals.get('name', '/') in ('/', False, None, '', 'Nueva Orden de Pago',
                                                'Nueva Requisición de Pago'):
                # Bug real (2026-09-04): `name` es store=True/readonly=False (_compute_name()),
                # así que un formulario web real (ej. "Nuevo" desde payment_order_ids dentro de
                # un Ticket) SIEMPRE manda 'Nueva Orden de Pago' ya puesto en vals - el viejo
                # `not vals.get('name')` lo trataba como "ya tiene nombre" y JAMÁS asignaba la
                # secuencia real. Un `create()` por `odoo-bin shell` sin la clave 'name' nunca
                # reproducía esto (por eso pasó inadvertido durante toda la verificación de esta
                # sesión) - solo se manifiesta guardando desde el cliente web real. Confirmado
                # leyendo el propio código del cliente (`record.js::_getChanges()`): un registro
                # nuevo manda TODOS sus valores actuales, no solo los que el usuario tocó.
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'account.payment.order.sequence') or '/'
            self._resolve_employee_enterprise_ref(vals)
            self._resolve_partner_enterprise_ref(vals)
            self._resolve_company_enterprise_ref(vals)
            self._resolve_analytic_enterprise_ref(vals)
            self._fill_derived_vals_from_employee(vals)
            self._fill_derived_vals_from_analytic_account(vals)
        records = super().create(vals_list)
        records._sync_monto_desde_total_acreditar()
        records._sync_proveedor_materiales_name()
        records._autosugerir_proveedor_materiales_id()
        for record, sat_document_ids in zip(records, sat_document_ids_list):
            # `_resolve_sat_document_ids()` solo existe si construtec_account_19 (Enterprise-
            # only) está instalado - ver account_payment_order_sat_document.py ahí. Este archivo
            # compartido nunca referencia construtec.sat.document directamente (ni account.move
            # para esto - decisión explícita del usuario, 2026-09-29: "de Enterprise a Community
            # solo deben copiarse los documentos SAT", nunca un id de factura), así que Community
            # puede seguir cargándolo sin ese modelo instalado.
            if sat_document_ids and hasattr(record, '_resolve_sat_document_ids'):
                record._resolve_sat_document_ids(sat_document_ids)
        return records

    def _check_factura_mirror_disponible(self, mirror):
        """Mismo candado que `_check_factura_disponible()`, pero contra el mirror de solo
        lectura (Community no tiene el account.move real) - un aviso temprano en
        `action_submit()`, útil pero NO autoritativo (el mirror puede estar desactualizado); la
        autoridad real corre en Enterprise, dentro de `_resolve_factura_origin_ids()`.

        También bloquea mezclar facturas de proveedores distintos en una misma Solicitud - una
        Orden de Pago Directo es para UN solo proveedor (regla de negocio explícita del usuario);
        la vista ya filtra `factura_mirror_ids` por `partner_id.vat` (ver
        account_payment_order_views.xml), esto es la defensa real (por si se elige por API/script,
        o si `partner_id` cambia después de ya haber elegido facturas)."""
        label = mirror.numero_autorizacion or mirror.partner_name or str(mirror.origin_id)
        if mirror.payment_state == 'paid':
            raise UserError(self.env._('La factura %s ya está completamente pagada.', label))
        if mirror.linked_order_name and mirror.linked_order_name != self.name:
            raise UserError(self.env._(
                'La factura %(factura)s ya está vinculada a la Orden de Pago %(orden)s.',
                factura=label, orden=mirror.linked_order_name))
        if (self.tipo == 'pago_directo' and self.partner_id and self.partner_id.vat
                and mirror.partner_vat and mirror.partner_vat != self.partner_id.vat):
            raise UserError(self.env._(
                'La factura %(factura)s es del proveedor %(otro)s, no de %(actual)s - una '
                'Requisición de Pago Directo es para un solo proveedor.',
                factura=label, otro=mirror.partner_name or mirror.partner_vat,
                actual=self.partner_id.name))

    def _check_gasto_mirror_disponible(self, mirror):
        """Una factura de gasto debe tener saldo vigente: sin pago o pagada parcialmente, nunca
        pagada (aviso temprano contra el mirror; la autoridad real corre en Enterprise). A
        diferencia de Pago Directo, aquí las facturas pueden ser de cualquier proveedor (el técnico
        gastó en varios comercios), así que no se valida el NIT."""
        self._check_factura_mirror_disponible(mirror)
        label = mirror.numero_autorizacion or mirror.partner_name or str(mirror.origin_id)
        if mirror.state == 'convertido_factura' and mirror.amount_residual <= 0:
            raise UserError(self.env._(
                'La factura %s ya no tiene saldo pendiente: solo se aceptan facturas sin pago o '
                'pagadas parcialmente.', label))

    def _check_puede_vincular_gastos(self):
        self.ensure_one()
        company = self.env.company
        if self.tipo not in GASTOS_TIPOS:
            raise UserError(self.env._(
                'Solo las requisiciones de Viáticos y Materiales llevan facturas de gastos.'))
        if self.state not in GASTOS_STATES_EDITABLES:
            raise UserError(self.env._(
                'Las facturas de gastos se vinculan desde Borrador y hasta que la requisición se '
                'liquide (estado actual: %s).', dict(self._fields['state'].selection)[self.state]))
        if self.state == 'borrador':
            # Todavía no existe la copia en Enterprise: viajan al enviar (`sat_document_ids`).
            return
        if company.payment_order_role != 'solicitante' or not company.payment_order_sync_enabled:
            raise UserError(self.env._(
                'La sincronización con Enterprise no está habilitada: no se pueden vincular '
                'facturas desde esta instalación.'))
        # Si la requisición aún no llegó a Enterprise, las facturas quedan en cola
        # (`gasto_pendiente_ids`) y se envían cuando llegue.

    @api.model
    def _gasto_labels(self, mirrors):
        return ', '.join(m.numero_documento or m.numero_autorizacion or str(m.origin_id)
                         for m in mirrors)

    def _push_gastos_to_enterprise(self, mirrors, desde_cola=False):
        """Envía a Enterprise las facturas de gastos nuevas (`mirrors`) junto con las que estuvieran
        en cola. Al guardar (`desde_cola=False`):
        - falla la COMUNICACIÓN (red, timeout, Enterprise caído) -> se guarda igual y quedan en cola
          (`gasto_pendiente_ids`); el cron las reintenta;
        - Enterprise RECHAZA (ya pagada, vinculada a otra requisición...) -> se cancela el guardado,
          porque reintentar no lo arregla.
        Desde la cola (`desde_cola=True`, cron o botón) un rechazo no lanza: queda `rechazado`.
        El método de Enterprise es idempotente (re-vincular a la misma requisición no duplica)."""
        self.ensure_one()
        company = self.env.company
        pendientes = self.gasto_pendiente_ids | mirrors
        if not pendientes:
            return
        if self.sync_state != 'synced':
            self._queue_gastos(pendientes, 'pendiente', self.env._(
                'La requisición todavía no está en Enterprise; las facturas se envían cuando llegue.'),
                avisar=bool(mirrors))
            return
        try:
            link_gasto_documents_in_enterprise(
                company.payment_order_sync_url, company.payment_order_sync_db,
                company.payment_order_sync_login, company.payment_order_sync_api_key,
                self.name, pendientes.mapped('origin_id'))
        except EnterpriseConnectionError as exc:
            self._queue_gastos(pendientes, 'error', str(exc), avisar=bool(mirrors))
            return
        except EnterpriseSyncError as exc:
            if not desde_cola:
                raise UserError(self.env._(
                    'Enterprise rechazó las facturas: %s', exc)) from exc
            self.write({'gasto_sync_state': 'rechazado', 'gasto_sync_error': str(exc),
                        'gasto_sync_attempts': self.gasto_sync_attempts + 1})
            self.message_post(body=self.env._(
                'Enterprise rechazó las facturas de gastos %(f)s: %(e)s. Quítelas de la '
                'requisición o corrija y presione "Reintentar envío".',
                f=self._gasto_labels(pendientes), e=exc))
            return
        self.write({'gasto_pendiente_ids': [(5, 0, 0)], 'gasto_sync_state': 'sincronizado',
                    'gasto_sync_error': False, 'gasto_sync_attempts': 0,
                    'gasto_sync_date': fields.Datetime.now()})
        self.message_post(body=self.env._(
            'Facturas de gastos vinculadas en Enterprise: %s.', self._gasto_labels(pendientes)))

    def _queue_gastos(self, mirrors, state, error, avisar=True):
        self.ensure_one()
        self.write({'gasto_pendiente_ids': [(4, m.id) for m in mirrors], 'gasto_sync_state': state,
                    'gasto_sync_error': error,
                    'gasto_sync_attempts': self.gasto_sync_attempts + (1 if state == 'error' else 0)})
        if avisar:
            self.message_post(body=self.env._(
                'Facturas de gastos guardadas, pendientes de enviar a Enterprise (%(f)s): %(e)s. '
                'Se reintenta automáticamente cada 15 minutos.',
                f=self._gasto_labels(mirrors), e=error))

    def action_retry_gasto_sync(self):
        for rec in self:
            rec._push_gastos_to_enterprise(self.env['construtec.sat.invoice.mirror'], desde_cola=True)

    @api.model
    def _cron_retry_gasto_sync(self):
        pendientes = self.search([
            ('gasto_pendiente_ids', '!=', False),
            ('gasto_sync_state', 'in', ('pendiente', 'error')),
            ('company_id.payment_order_role', '=', 'solicitante'),
            ('company_id.payment_order_sync_enabled', '=', True),
        ])
        for rec in pendientes:
            try:
                with self.env.cr.savepoint():
                    rec.with_company(rec.company_id)._push_gastos_to_enterprise(
                        self.env['construtec.sat.invoice.mirror'], desde_cola=True)
            except Exception:  # noqa: BLE001 - una requisición no frena a las demás
                _logger.exception('Reintento de facturas de gastos falló para %s', rec.name)

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
            # .sudo(): quien crea/sincroniza una Orden no necesariamente tiene hr.group_hr_user -
            # mismo motivo documentado en _onchange_partner_id() (bug real 2026-09-18).
            employee = self.env['hr.employee'].sudo().browse(int(ref)).exists()
            if employee:
                vals['partner_id'] = employee.work_contact_id.id
                vals.setdefault('company_id', employee.company_id.id)

    def _resolve_partner_enterprise_ref(self, vals):
        """Resuelve `partner_enterprise_ref` (solo para Pago Directo - ver `_prepare_sync_vals()`)
        hacia un `partner_id` real de esta base. A diferencia de `_resolve_employee_enterprise_ref()`
        (el contacto de un EMPLEADO, resuelto vía `hr.employee.enterprise_employee_ref`), aquí
        `partner_id` es directamente un proveedor/cliente real - se resuelve vía
        `res.partner.enterprise_partner_ref`, poblado por la sincronización de Contactos que ya
        trae a Community los proveedores conocidos (ver `res_company.py::
        _sync_partners_from_enterprise()`) - el mismo id, porque es literalmente el id de ese
        contacto tal como existe en Enterprise."""
        ref = vals.pop('partner_enterprise_ref', None)
        if ref and not vals.get('partner_id'):
            partner = self.env['res.partner'].browse(int(ref)).exists()
            if partner:
                vals['partner_id'] = partner.id

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
        vals.setdefault('tipo_cuenta', employee.tipo_cuenta or False)
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
                # Anti-suplantación, para Anticipo Viáticos y Anticipo Materiales - en ambos
                # `partner_id` siempre identifica a quien sube/solicita la Orden (nunca al
                # proveedor, ver `_onchange_pagar_a()`), así que aplica el mismo criterio en los
                # dos. partner_id de un Pago Directo/Anticipo normal debe seguir siendo
                # libremente editable (nunca tuvo esta restricción). employee_id (calculado) se
                # revisa también por defensa en profundidad.
                if rec.tipo not in ('anticipo_viaticos', 'anticipo_materiales'):
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
        gasto_antes = {}
        if 'gasto_mirror_ids' in vals:
            for rec in self:
                rec._check_puede_vincular_gastos()
            gasto_antes = {rec.id: rec.gasto_mirror_ids for rec in self}
        res = super().write(vals)
        # En Borrador se edita libremente (nada que avisar todavía); desde Enviada se empuja.
        for rec in self.filtered(lambda r: r.id in gasto_antes and r.state != 'borrador'):
            antes, ahora = gasto_antes[rec.id], rec.gasto_mirror_ids
            quitadas = antes - ahora
            if quitadas - rec.gasto_pendiente_ids:
                raise UserError(self.env._(
                    'Una factura de gasto ya vinculada no se puede quitar: Enterprise ya la '
                    'reclamó para esta requisición.'))
            if quitadas:
                # Nunca llegaron a Enterprise: se pueden quitar y salen de la cola.
                rec.gasto_pendiente_ids -= quitadas
                if not rec.gasto_pendiente_ids:
                    rec.gasto_sync_state = 'sincronizado' if rec.gasto_sync_date else False
                    rec.gasto_sync_error = False
            nuevas = ahora - antes
            if nuevas:
                for mirror in nuevas:
                    rec._check_gasto_mirror_disponible(mirror)
                rec._push_gastos_to_enterprise(nuevas)
        if any(k in vals for k in ('viaticos_line_ids', 'material_line_ids', 'anticipo_previo', 'tipo')):
            self._sync_monto_desde_total_acreditar()
        if 'proveedor_materiales_catalogo_id' in vals:
            self._sync_proveedor_materiales_name()
        if 'proveedor_materiales_name' in vals:
            self._autosugerir_proveedor_materiales_id()
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

    def _push_notify(self, partners, title, body):
        """Notificación push del navegador (Web Push / RFC 8291) - pedido explícito del usuario
        2026-09-18: que viva aquí, en `construtec_account_payment_order_19`, separada de
        `construtec_whatsapp_19` (esa integra con la API de Meta, mucho más compleja).

        **Rediseñado el mismo día**: la primera versión llamaba directo a los métodos de bajo
        nivel de `mail.thread` (`_web_push_get_partners_parameters`/`_web_push_send_notification`)
        con un payload propio, sin pasar por `message_post()` - esto SÍ mandaba el push, pero no
        dejaba ningún rastro en Odoo: ni en el chatter de la Orden, ni en el panel de
        Conversaciones (Discusión > Bandeja de entrada) del destinatario. El usuario pidió
        explícitamente que la notificación "quede en el panel de conversaciones" - si el push en
        sí no llega (navegador cerrado y el sistema operativo/fabricante mata el proceso en
        segundo plano antes de que despierte, batería, etc.), la persona no tenía NINGÚN otro
        rastro de que algo pasó.

        Ahora se usa `message_post(partner_ids=..., subtype_xmlid='mail.mt_note')` - el mismo
        mecanismo nativo que Odoo ya usa para menciones/mensajes directos
        (`_notify_thread_by_inbox`/`_notify_thread_by_web_push`, en `mail.thread`). Con esto, UNA
        sola llamada logra las tres cosas: (1) el mensaje queda en el chatter de la Orden
        (historial permanente, visible para cualquiera con acceso al registro), (2) cada
        `partner` recibe un `mail.notification` en su Bandeja de entrada de Conversaciones -
        visible ahí para siempre, sin importar si el push llegó o no -, y (3) Odoo dispara el
        mismo push (misma infraestructura VAPID/Service Worker de antes, sin nada nuevo que
        mantener) hacia los dispositivos ya registrados de esos partners.

        **Bug real corregido 2026-09-19, encontrado al construir la notificación de Tickets**:
        el default REAL de `message_post()` es `message_type='notification'`, NO `'comment'`
        (el docstring original de este método asumía, sin verificar, que 'comment' era el
        default - error de transcripción, nunca se puso explícito en el primer despliegue).
        Con `'notification'`, `_notify_get_recipients_for_extra_notifications()` (`mail_thread.py`)
        **excluye del push a cualquier partner cuya preferencia (`res.users.notification_type`)
        sea `'email'`** - el default de TODA cuenta nueva de Odoo. Resultado real: el push nunca
        llegaba a nadie que no hubiera cambiado ya esa preferencia a "En Odoo" a mano, aunque el
        mensaje sí quedara en el chatter. Confirmado con `odoo-bin shell` (mockeando
        `_web_push_get_partners_parameters`/`_web_push_send_notification`): `message_type`
        por defecto → cero intentos de push; `message_type='comment'` → sí se intenta, para
        TODOS los `partner_ids` explícitos salvo el autor. **El fix**: `message_type='comment'`
        ahora se pasa explícito en la llamada.

        Sin ningún efecto visible en el push si ningún `partner` tiene un dispositivo registrado
        (`mail.push.device`, nunca aceptó el permiso del navegador) - pero el registro en el
        chatter/Bandeja de entrada ocurre siempre, con o sin dispositivo."""
        self.ensure_one()
        partners = partners.filtered('id')
        if not partners:
            return
        self.message_post(
            body=Markup('<b>%s</b><br/>%s') % (title, body),
            partner_ids=partners.ids,
            subtype_xmlid='mail.mt_note',
            message_type='comment',
        )

    def _notify_estado_pull(self, estado_nuevo):
        """Notifica al solicitante original cuando `_pull_payment_order_status()`
        (`res_company.py`) detecta que su Orden cambió de estado en Enterprise - pedido
        explícito del usuario 2026-09-19: "el usuario que ingresa la orden de pago también debe
        ser notificado cuando la orden es aprobada y aplicada".

        Por qué esto vive aquí y no en `action_approve()`/`action_aplicar()`/`action_conciliar()`
        (que ya tenían su propio `_push_notify()` desde el 2026-09-18): esos tres métodos NUNCA
        se ejecutan de verdad sobre el registro LOCAL de Community de una Orden sincronizada -
        la aprobación ocurre en la instalación Procesadora (Enterprise), sobre una copia
        DISTINTA del registro (ver "Cambio de arquitectura" en este mismo CLAUDE.md). El único
        momento en que Community se entera de esa transición es el `write()` plano de
        `_pull_payment_order_status()` - así que la notificación tiene que dispararse ahí,
        usando el `requested_by_id` LOCAL de Community (el solicitante real), no el de la copia
        de Enterprise (que resuelve al usuario de integración API, no a la persona real - ver
        `requested_by_id.default` y la regla de "nunca ids entre bases independientes").

        Los `_push_notify()` que ya existen dentro de `action_approve()`/`action_aplicar()`/
        `action_conciliar()` no se eliminaron - siguen siendo correctos para una Orden 100%
        local (creada y aprobada dentro de la misma base, sin sincronización de por medio, ej.
        un Anticipo normal capturado directo en Enterprise)."""
        self.ensure_one()
        partner = self.requested_by_id.partner_id
        if estado_nuevo == 'en_compras':
            self._push_notify(
                partner, self.env._('Requisición de Pago aprobada'),
                self.env._('%(name)s fue aprobada y está en Gestión de Compras.', name=self.name))
        elif estado_nuevo == 'aprobado':
            self._push_notify(
                partner, self.env._('Requisición de Pago aprobada'),
                self.env._('%(name)s fue aprobada.', name=self.name))
        elif estado_nuevo == 'aplicado':
            self._push_notify(
                partner, self.env._('Requisición de Pago aplicada'),
                self.env._('%(name)s ya se desembolsó (Q%(monto).2f).',
                           name=self.name, monto=self.monto or 0.0))
        elif estado_nuevo == 'liquidado':
            self._push_notify(
                partner, self.env._('Requisición de Pago liquidada'),
                self.env._('%(name)s quedó liquidada.', name=self.name))
        elif estado_nuevo == 'rechazado':
            motivo = (' %s' % self.env._('Motivo: %(motivo)s', motivo=self.reject_reason)
                      if self.reject_reason else '')
            self._push_notify(
                partner, self.env._('Requisición de Pago rechazada'),
                self.env._('%(name)s fue rechazada.', name=self.name) + motivo)

    def _approver_partners(self):
        """Destinatarios del push de "Enviado" - pedido explícito del usuario, en dos pasadas:
        primero "avisar solo a quien de verdad puede aprobar según el monto" (2026-09-18), luego
        corregido el mismo día: "las Órdenes de Pago deben ser notificadas a TODOS los
        aprobadores Nivel Medio, sean menores o mayores [al umbral]... ya los gerentes solo
        arriba del umbral" - o sea:
        - **Nivel Medio (Jefe de Área)**: SIEMPRE, sin importar el monto - quiere ver todo, aunque
          técnicamente no le toque aprobar los montos altos.
        - **Nivel Alto (Gerente de Área)**: SOLO cuando el monto llega al umbral configurado
          (`res.company.payment_order_approval_threshold` - el que sea, no un número fijo) - no
          se le satura con cada Orden de monto bajo que no necesita su aprobación.

        Solo afecta el push de este módulo - WhatsApp (`construtec_whatsapp_19`) no se toca,
        sigue con su propio `recipient_group_id` configurable de siempre.

        `group_ids` (grupos DIRECTOS del usuario), no `all_group_ids` (directos + implícitos) -
        a propósito, al revés del criterio anterior: aquí sí importa separar "asignado
        directamente a Nivel Medio" de "asignado a Nivel Alto" (que implica Medio a nivel de
        PERMISO, pero eso no debe traducirse en notificarlo de más) - verificado con
        `odoo-bin shell` que un usuario asignado solo a Nivel Alto no aparece en `group_ids` de
        Nivel Medio (la implicación de `res.groups` no se materializa ahí, solo en
        `all_group_ids`), que es justo el comportamiento que se necesita ahora."""
        self.ensure_one()
        medio_partners = self.env['res.users'].search(
            [('group_ids', 'in', self.env.ref(APPROVER_MEDIO_GROUP_XMLID).ids)]).partner_id
        threshold = self.company_id.payment_order_approval_threshold or 0.0
        if self.total_acreditar >= threshold:
            alto_partners = self.env['res.users'].search(
                [('group_ids', 'in', self.env.ref(APPROVER_ALTO_GROUP_XMLID).ids)]).partner_id
            return medio_partners | alto_partners
        return medio_partners

    def action_submit_depositar_a_mi(self):
        """Botón "Depositar a Mí" (reemplaza el checkbox `depositar_directo_tecnicos` - pedido
        explícito del usuario: la elección debe ser un botón, no una casilla que hay que marcar
        antes de Enviar). Solo aplica a Anticipo Viáticos - fija el campo en False (el depósito
        va a la cuenta del jefe que captura, camino normal) y reutiliza `action_submit()` sin
        cambios."""
        self.write({'depositar_directo_tecnicos': False})
        self.action_submit()

    def action_submit_depositar_a_tecnicos(self):
        """Botón "Depositar a Técnicos" - mismo criterio que `action_submit_depositar_a_mi()`,
        fija el campo en True (dispara `_dividir_en_ordenes_por_tecnico()` dentro de
        `action_submit()`, sin cambios ahí)."""
        self.write({'depositar_directo_tecnicos': True})
        self.action_submit()

    def action_submit(self):
        for rec in self:
            if rec.tipo not in SUBMITTABLE_TIPOS:
                raise UserError(self.env._(
                    'Enviar solo aplica a Órdenes de Pago de tipo Anticipo o Pago Directo.'))
            if rec.tipo == 'pago_directo':
                if not rec.factura_mirror_ids:
                    raise UserError(self.env._(
                        'Agregue al menos una factura antes de enviar la Requisición de Pago.'))
                for mirror in rec.factura_mirror_ids:
                    rec._check_factura_mirror_disponible(mirror)
            if rec.tipo == 'anticipo_viaticos' and not rec.viaticos_line_ids:
                raise UserError(self.env._(
                    'Agregue al menos una línea de viáticos antes de enviar la orden.'))
            if rec.tipo in GASTOS_TIPOS:
                for mirror in rec.gasto_mirror_ids:
                    rec._check_gasto_mirror_disponible(mirror)
            if rec.viaticos_line_ids.filtered(lambda line: not line.employee_id):
                raise UserError(self.env._(
                    'Todas las líneas de viáticos deben tener un empleado seleccionado antes '
                    'de enviar la orden.'))
            if rec.tipo == 'anticipo_materiales' and not rec.material_line_ids:
                raise UserError(self.env._(
                    'Agregue al menos una línea de materiales antes de enviar la orden.'))
            if rec.tipo == 'anticipo_viaticos' and not (rec.periodo_del and rec.periodo_al):
                raise UserError(self.env._('Complete el período antes de enviar la orden.'))

            if rec.tipo == 'anticipo_viaticos' and rec.depositar_directo_tecnicos:
                # El depósito va a la cuenta de CADA técnico, no a la del jefe que captura -
                # esta Orden nunca se envía ella misma como una orden de dinero real, se divide.
                # Ver _dividir_en_ordenes_por_tecnico() para el detalle completo.
                faltantes = rec.viaticos_line_ids.filtered(
                    lambda l: not (l.cuenta_acreditar and l.tipo_cuenta and l.banco))
                if faltantes:
                    raise UserError(self.env._(
                        'Los siguientes técnicos no tienen cuenta bancaria sincronizada - '
                        'complétala a mano en su línea (pestaña Viáticos) antes de enviar: '
                        '%(nombres)s', nombres=', '.join(faltantes.mapped('tecnico_name'))))
                rec._dividir_en_ordenes_por_tecnico()
                continue

            if rec.tipo == 'anticipo_viaticos' and not (
                    rec.cuenta_acreditar and rec.tipo_cuenta and rec.banco):
                raise UserError(self.env._(
                    'Complete cuenta a acreditar, tipo de cuenta y banco antes de enviar la '
                    'orden.'))
            rec.write({'state': 'enviado', 'submit_date': fields.Datetime.now()})
            # La sincronización ocurre al enviar, no al aprobar - la aprobación (Nivel Medio/
            # Alto) ocurre en la instalación Procesadora (Enterprise), donde están los usuarios
            # administrativos reales. En una instalación Procesadora esto es un no-op
            # (_sync_to_enterprise() solo actúa si payment_order_role == 'solicitante'). Por
            # registro (no al final, en lote) porque una Orden dividida arriba nunca llega
            # aquí - sus hijas se sincronizan cada una por su cuenta, dentro de su propia
            # llamada recursiva a action_submit() (ver _dividir_en_ordenes_por_tecnico()).
            rec._sync_to_enterprise()
            rec._push_notify(
                rec._approver_partners(),
                self.env._('Nueva Requisición de Pago para aprobar'),
                self.env._('%(name)s - Q%(monto).2f, solicitada por %(solicitante)s',
                           name=rec.name, monto=rec.total_acreditar or rec.monto or 0.0,
                           solicitante=rec.requested_by_id.name or rec.requested_by_name or ''))

    def _dividir_en_ordenes_por_tecnico(self):
        """Con 'depositar_directo_tecnicos' marcado: por cada línea de viáticos, crea una Orden
        de Pago independiente (mismo tipo/fecha/período/compañía) con ESE técnico como Contacto
        real y su propia cuenta bancaria (ya resuelta en la línea, ver
        account_payment_order_viatico_line.py) - así el depósito llega a la cuenta de cada
        técnico, no a la del jefe que capturó la Orden original.

        Cada Orden hija se envía (`action_submit()`) por su cuenta, recorriendo el camino
        NORMAL (no vuelve a dividirse - trae una sola línea y `depositar_directo_tecnicos` en
        False por default), lo que reutiliza sin cambios toda la validación/sincronización que
        ya existe - ninguna lógica nueva de sincronización, solo el paso previo de dividir.

        La Orden original NUNCA se envía ella misma como una orden de dinero real - queda en
        `dividida` (2026-09-05: NO `cancelado` - decisión explícita del usuario, ya que
        "cancelado" da a entender que el pago no va a ocurrir, y aquí sí ocurre, solo que en
        otras Órdenes), con una nota en el chatter y las hijas enlazadas vía
        `orden_padre_id`/`ordenes_hijas_ids`. División en 1 sola hija incluida, incluso con un
        solo técnico en la lista - pedido explícito del usuario, por trazabilidad uniforme, sin
        un camino especial según cuántos técnicos haya.

        `ticket_id` (si esta Orden se creó desde dentro de un Ticket - campo que agrega
        `construtec_helpdesk_field_service`, un módulo aparte que NO es dependencia de este,
        por eso el chequeo `'ticket_id' in self._fields` antes de tocarlo, para no romper una
        instalación donde ese campo no existe, ej. Enterprise): se traslada a cada Orden hija
        (si no, quedarían invisibles en la pestaña "Órdenes de Pago" del Ticket, y su costo real
        nunca se sumaría a `helpdesk.ticket.costo_total`), y se QUITA de la Orden original al
        cancelarla - `_compute_costo_total()` suma el `monto` de TODAS las Órdenes vinculadas al
        Ticket sin filtrar por `state`, así que dejar esta Orden (ya obsoleta) vinculada
        duplicaría el total (el suyo + el de sus hijas). La trazabilidad hacia esta Orden sigue
        disponible por `orden_padre_id` en cada hija, sin necesidad de que el Ticket la siga
        listando. Se desvincula ANTES de crear las hijas (no después) para que el recómputo de
        `costo_total` nunca pase por un estado intermedio donde cuenta el monto de esta Orden Y
        el de sus hijas a la vez."""
        self.ensure_one()
        if len(self.viaticos_line_ids) > 1 and self.gasto_mirror_ids:
            # Con varios técnicos no hay forma de saber a cuál le tocan las facturas ya elegidas.
            raise UserError(self.env._(
                'Con varios técnicos las facturas de gastos se vinculan a la requisición de cada '
                'técnico una vez enviada. Quite las facturas de esta requisición antes de '
                'depositar a técnicos.'))
        tiene_ticket_id = 'ticket_id' in self._fields
        ticket_id = self.ticket_id.id if tiene_ticket_id and self.ticket_id else False
        dividir_vals = {'state': 'dividida'}
        if ticket_id:
            dividir_vals['ticket_id'] = False
        self.write(dividir_vals)

        nuevas = self.env['account.payment.order']
        for linea in self.viaticos_line_ids:
            vals = {
                'tipo': 'anticipo_viaticos',
                'partner_id': linea.employee_partner_id.id,
                'company_id': self.company_id.id,
                'fecha': self.fecha,
                'periodo_del': self.periodo_del,
                'periodo_al': self.periodo_al,
                'orden_padre_id': self.id,
                'lote_origen': self.name,
                'cuenta_acreditar': linea.cuenta_acreditar,
                'banco': linea.banco,
                'tipo_cuenta': linea.tipo_cuenta,
                'viaticos_line_ids': [(0, 0, {
                    'employee_partner_id': linea.employee_partner_id.id,
                    'cantidad': linea.cantidad,
                    'costo_individual': linea.costo_individual,
                    # Bug real (2026-09-04): sin esto, la línea PROPIA de la Orden hija volvía
                    # a derivar cuenta_acreditar/banco/tipo_cuenta desde el empleado sincronizado
                    # (ver account_payment_order_viatico_line.py::create()) - si el técnico no
                    # tenía esos datos sincronizados desde Enterprise (caso real, no raro) y el
                    # jefe ya los había corregido A MANO en la línea original, la corrección se
                    # perdía en la hija: el ENCABEZADO sí la heredaba bien (ver arriba), pero su
                    # propia línea de viáticos (ahora visible, ver la sección de más arriba sobre
                    # las columnas visibles) se quedaba en blanco - inconsistente con su propio
                    # encabezado. Mandar estos 3 valores explícitos hace que `vals.setdefault(...)`
                    # (en el create() de la línea) los respete tal cual, sin volver a derivarlos.
                    'cuenta_acreditar': linea.cuenta_acreditar,
                    'banco': linea.banco,
                    'tipo_cuenta': linea.tipo_cuenta,
                })],
            }
            if ticket_id:
                vals['ticket_id'] = ticket_id
            if self.gasto_mirror_ids:  # un solo técnico (ver arriba): sus facturas pasan a su orden
                vals['gasto_mirror_ids'] = [(6, 0, self.gasto_mirror_ids.ids)]
            nuevas |= self.create(vals)
        nuevas.action_submit()
        self.message_post(body=self.env._(
            'Dividida en %(cantidad)s Orden(es) de Pago (depósito directo a técnicos): '
            '%(nombres)s', cantidad=len(nuevas), nombres=', '.join(nuevas.mapped('name'))))
        return nuevas

    def action_approve(self):
        for rec in self:
            if rec.tipo not in SUBMITTABLE_TIPOS:
                raise UserError(self.env._(
                    'Aprobar solo aplica a Órdenes de Pago de tipo Anticipo o Pago Directo.'))
            rec._check_is_approver_for_amount()
            rec._aplicar_cuenta_anticipo_por_tipo()
            es_materiales = rec.tipo == 'anticipo_materiales'
            rec.write({
                # Materiales pasa primero por Compras; los demás tipos quedan listos para Aplicar.
                'state': 'en_compras' if es_materiales else 'aprobado',
                'approved_by_id': self.env.user.id,
                'approve_date': fields.Datetime.now(),
                'aprobado_por_gerente': self.env.user.has_group(APPROVER_ALTO_GROUP_XMLID),
            })
            if es_materiales:
                rec._push_notify(
                    rec._compras_partners(),
                    self.env._('Solicitud de Materiales para Compras'),
                    self.env._('%(name)s fue aprobada y está lista para gestionar (cotizar, Orden '
                               'de Compra y factura).', name=rec.name))
            # Auto-heal: registros sincronizados ANTES de que existiera
            # `_autosugerir_proveedor_materiales_id()` (2026-09-02) nunca recibieron su intento
            # de resolución (solo corre en create()/write() de `proveedor_materiales_name`) - se
            # reintenta aquí, mismo criterio ya usado para las credenciales del Catálogo de
            # Materiales (self-healing en el punto de uso, no una migración aparte).
            rec._autosugerir_proveedor_materiales_id()
            rec._push_notify(
                rec.requested_by_id.partner_id,
                self.env._('Requisición de Pago aprobada'),
                self.env._('%(name)s fue aprobada por %(aprobador)s', name=rec.name,
                           aprobador=self.env.user.name))

    def action_reject(self):
        self._check_is_approver()
        for rec in self:
            if rec.tipo not in SUBMITTABLE_TIPOS:
                raise UserError(self.env._(
                    'Rechazar solo aplica a Órdenes de Pago de tipo Anticipo o Pago Directo.'))
            rec.write({
                'state': 'rechazado',
                'rejected_by_id': self.env.user.id,
                'reject_date': fields.Datetime.now(),
            })

    def action_reset_to_draft(self):
        for rec in self:
            if rec.tipo not in SUBMITTABLE_TIPOS:
                raise UserError(self.env._(
                    'Volver a Borrador solo aplica a Órdenes de Pago de tipo Anticipo o Pago '
                    'Directo.'))
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
            if rec.tipo not in SUBMITTABLE_TIPOS:
                raise UserError(self.env._(
                    'Cancelar (antes de Aplicar/Liquidar) solo aplica a tipo Anticipo o Pago '
                    'Directo.'))
            if rec.state not in ('borrador', 'enviado', 'en_compras', 'aprobado', 'rechazado'):
                raise UserError(self.env._(
                    'No se puede cancelar así una Orden ya Aplicada/Liquidada - usa el botón '
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
        # 'draft': el pago de Materiales se genera en borrador (ver action_aplicar()).
        for pago in self.pago_ids.filtered(lambda p: p.state in ('draft', 'in_process', 'paid')):
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
            # .sudo(): mismo motivo documentado en _onchange_partner_id() más arriba - un
            # solicitante sin hr.group_hr_user no puede leer hr.employee sin esto.
            'employee_enterprise_ref': self.employee_id.sudo().enterprise_employee_ref or False,
            'company_enterprise_ref':
                self.company_id.payment_order_default_company_id.enterprise_company_ref or False,
            'analytic_enterprise_ref': self.analytic_account_id.enterprise_analytic_ref or False,
            # Solo para Pago Directo - ver _resolve_partner_enterprise_ref(). Para los demás
            # tipos, partner_id se resuelve vía employee_enterprise_ref (arriba), no aquí.
            'partner_enterprise_ref': (
                self.partner_id.enterprise_partner_ref
                if self.tipo == 'pago_directo' and self.partner_id else False),
            'puesto': self.puesto or '',
            'departamento': self.departamento or '',
            'proyecto': self.proyecto or '',
            'telefono': self.telefono or '',
            'correo': self.correo or '',
            'fecha': self.fecha and self.fecha.isoformat() or False,
            'cuenta_acreditar': self.cuenta_acreditar or '',
            'tipo_cuenta': self.tipo_cuenta,
            'banco': self.banco or '',
            'lote_origen': self.lote_origen or '',
            'periodo_del': self.periodo_del and self.periodo_del.isoformat() or False,
            'periodo_al': self.periodo_al and self.periodo_al.isoformat() or False,
            'observaciones': self.observaciones or '',
            'anticipo_previo': self.anticipo_previo,
            'proveedor_materiales_name': self.proveedor_materiales_name or '',
            # Ids REALES de construtec.sat.document en Enterprise - NUNCA un id de account.move
            # (decisión explícita del usuario, 2026-09-29: "de Enterprise a Community solo deben
            # copiarse los documentos SAT"). El jefe de técnicos los eligió del mirror de solo
            # lectura construtec.sat.invoice.mirror, cuyo `origin_id` ES el id real del Documento
            # SAT allá, sin importar su estado. Enterprise decide qué hacer con cada uno según su
            # estado REAL en ese momento (`_resolve_sat_document_ids()`, Enterprise-only,
            # construtec_account_19) - ya `convertido_factura` (vincula el `move_id` existente) o
            # todavía `pendiente` (lo reclama; el Contador lo convierte a factura real al
            # Aprobar). Vacío para cualquier tipo que no sea Pago Directo.
            # Viáticos: las facturas de gastos que el técnico ya vinculó en Borrador (2026-10-17;
            # las que vincule después de enviar viajan aparte, ver _push_gastos_to_enterprise()).
            'sat_document_ids': (
                self.factura_mirror_ids.mapped('origin_id') if self.tipo == 'pago_directo'
                else self.gasto_mirror_ids.mapped('origin_id') if self.tipo in GASTOS_TIPOS
                else []),
            # 'enviado', no 'aprobado': la aprobación ocurre en la instalación Procesadora
            # (Enterprise), donde están los usuarios Nivel Medio/Alto reales - ver
            # action_submit()/action_approve() más arriba.
            'state': 'enviado',
            'submit_date': fields.Datetime.to_string(fields.Datetime.now()),
            'viaticos_line_ids': [
                (0, 0, {
                    'tecnico_name': line.tecnico_name or '',
                    # .sudo(): mismo motivo que arriba - un solicitante sin hr.group_hr_user no
                    # puede leer hr.employee sin esto (bug real 2026-09-18, ver CLAUDE.md).
                    'employee_enterprise_ref': line.employee_id.sudo().enterprise_employee_ref or False,
                    'departamento': line.departamento or '',
                    'puesto': line.puesto or '',
                    'cantidad': line.cantidad,
                    'costo_individual': line.costo_individual,
                    # Bug real (2026-09-05): sin esto, la línea PROPIA ya en Enterprise volvía a
                    # derivar cuenta_acreditar/banco/tipo_cuenta desde el `hr.employee` allá (ver
                    # account_payment_order_viatico_line.py::create()) - si ese empleado tampoco
                    # tiene esos datos cargados en Enterprise (el mismo caso por el que el jefe
                    # tuvo que corregirlos A MANO en Community, ver `_dividir_en_ordenes_por_
                    # tecnico()`), la línea llegaba vacía aunque el ENCABEZADO de esta misma
                    # Orden sí los trajera bien (ese sí viajaba, ver `cuenta_acreditar`/`banco`/
                    # `tipo_cuenta` unas líneas arriba). Mandarlos explícitos aquí hace que el
                    # `create()` de la línea (que usa `vals.setdefault(...)`) los respete tal
                    # cual, sin intentar derivarlos de nuevo.
                    'cuenta_acreditar': line.cuenta_acreditar or '',
                    'banco': line.banco or '',
                    'tipo_cuenta': line.tipo_cuenta,
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
        for rec in self.filtered(lambda r: r.tipo in SUBMITTABLE_TIPOS):
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
            ('tipo', 'in', SUBMITTABLE_TIPOS),
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
        if self.tipo == 'pago_directo' and self.state not in ('borrador', 'aprobado'):
            # 'borrador': camino clásico, creado directo en Enterprise, sin pasar por Community.
            # 'aprobado': camino nuevo - llegó sincronizado desde Community y ya fue aprobado
            # aquí (ver action_submit()/action_approve()) - nunca 'enviado' sin aprobar primero.
            raise UserError(self.env._(
                'Solo se puede Conciliar/Liquidar un Pago Directo en Borrador, o ya Aprobado si '
                'vino de una Solicitud sincronizada desde Community.'))
        self._check_es_administrador_contable()
        if not self.journal_id:
            raise UserError(self.env._('Define el Diario antes de Conciliar/Liquidar.'))
        if self.tipo == 'pago_directo' and not self.factura_ids:
            raise UserError(self.env._(
                'Un Pago Directo debe incluir al menos una factura.'))

        # Solo las líneas de por cobrar/por pagar representan la deuda con el proveedor o
        # el contacto - las demás (caja, banco, "Pagos Pendientes"/outstanding) son solo el
        # otro lado del asiento y no deben entrar en el neteo.
        CUENTAS_A_NETEAR = ('asset_receivable', 'liability_payable')

        # `amount_residual` (no `credit - debit`, el monto ORIGINAL de la línea) - una factura de
        # Pago Directo puede llegar aquí ya parcialmente conciliada por una Orden ANTERIOR contra
        # la misma factura (pago en varios abonos - ver "Facturas pagadas en varios abonos" en el
        # CLAUDE.md de este módulo) - usar el monto original volvería a intentar netear lo que
        # otra Orden ya cubrió. Mismo signo que `balance` (debit-credit); positivo = todavía se
        # debe (factura), negativo = ya se pagó (pago) - de ahí el signo `-` en ambos casos.
        facturas_montos = []
        for factura in self.factura_ids:
            if factura.state != 'posted':
                continue
            for line in factura.line_ids:
                if line.account_id.reconcile and line.account_id.account_type in CUENTAS_A_NETEAR:
                    if line.reconciled:
                        raise UserError(self.env._('La factura %s ya está conciliada.', factura.name))
                    facturas_montos.append((line, -line.amount_residual))

        pagos_montos = []
        for pago in self.pago_ids:
            if pago.state not in ('in_process', 'paid'):
                continue
            if pago.reconciled_invoice_ids or pago.reconciled_bill_ids:
                if self.tipo == 'pago_directo' and pago.reconciled_bill_ids & self.factura_ids:
                    # Pago registrado desde la propia factura (botón Pagar) - ya está aplicado
                    # ahí, no se vuelve a netear (ver _sync_pagos_nativos()).
                    continue
                raise UserError(self.env._('El pago %s ya está conciliado.', pago.name))
            for line in pago.move_id.line_ids:
                if line.account_id.reconcile and line.account_id.account_type in CUENTAS_A_NETEAR:
                    pagos_montos.append((line, -line.amount_residual))

        factura_total = sum(monto for _, monto in facturas_montos)
        pago_total = sum(monto for _, monto in pagos_montos)
        total = factura_total + pago_total

        if self.tipo == 'pago_directo':
            if not pagos_montos:
                raise UserError(self.env._(
                    'No hay ningún pago pendiente de aplicar. Si los pagos se registraron desde la '
                    'factura (botón Pagar), la requisición se liquida sola cuando las facturas '
                    'quedan pagadas.'))
            if round(total, 2) < 0:
                raise UserError(self.env._(
                    'El monto del pago excede el saldo pendiente de la(s) factura(s) por '
                    '%(exceso).2f.', exceso=-total))
            # total >= 0: el pago cubre parte o el 100% del saldo actual - nunca más. A
            # diferencia de Anticipo/Liquidación (que admiten una Cuenta de Ajuste para CUALQUIER
            # diferencia), Pago Directo nunca inventa un ajuste - si el pago cubre menos que el
            # saldo, se recorta el neteo del lado de las facturas a exactamente lo que el pago
            # cubre (`abs(pago_total)`), dejando el resto del saldo abierto - ver
            # `_liberar_facturas_con_saldo()` más abajo, que libera esas facturas para que otra
            # Orden pueda tomarlas después.
            restante = -pago_total
            lineas, montos = [], []
            for line, monto in facturas_montos:
                if restante <= 0:
                    break
                cubierto = min(monto, restante)
                lineas.append(line)
                montos.append(cubierto)
                restante -= cubierto
            lineas += [line for line, _ in pagos_montos]
            montos += [monto for _, monto in pagos_montos]
        else:
            lineas = [line for line, _ in facturas_montos] + [line for line, _ in pagos_montos]
            montos = [monto for _, monto in facturas_montos] + [monto for _, monto in pagos_montos]
            if round(total, 2) != 0 and not self.cuenta_ajuste_id:
                raise UserError(self.env._(
                    'El total de las facturas no coincide con el total de los pagos. Define una '
                    'Cuenta de Ajuste para registrar la diferencia.'))

        nuevas_lineas = []
        for linea, monto in zip(lineas, montos):
            nuevas_lineas.append((0, 0, {
                'name': linea.name,
                'debit': monto if monto > 0 else 0,
                'credit': -monto if monto < 0 else 0,
                'account_id': linea.account_id.id,
                'partner_id': linea.partner_id.id,
                'date_maturity': self.fecha,
            }))

        if self.tipo != 'pago_directo' and round(total, 2) != 0:
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

        # Sin el contexto, account_partial_reconcile.py vería la factura pagada y liquidaría la
        # Orden antes de tiempo (sin move_id) - aquí la liquidación la escribe este mismo método.
        for linea, nueva_linea in zip(lineas, move.line_ids):
            (linea | nueva_linea).with_context(skip_pago_nativo_sync=True).reconcile()

        self.write({'move_id': move.id, 'state': 'liquidado'})
        if self.tipo == 'pago_directo':
            self._liberar_facturas_con_saldo()
        self._push_notify(
            self.requested_by_id.partner_id,
            self.env._('Requisición de Pago liquidada'),
            self.env._('%(name)s quedó liquidada', name=self.name))
        return True

    def _liberar_facturas_con_saldo(self):
        """Tras Conciliar un Pago Directo que cubrió solo PARTE del saldo de una factura, la
        deja libre (`payment_order_id = False`) para que otra Orden pueda tomarla y cubrir el
        resto - ver "Facturas pagadas en varios abonos" en el CLAUDE.md de este módulo. Una
        factura que SÍ quedó completamente pagada se deja vinculada a esta Orden (registro
        histórico de quién la cerró) - de todas formas `_check_payment_order_disponible()`
        (`account_move.py`) ya bloquea cualquier intento de tomarla, esté o no vinculada, en
        cuanto `payment_state == 'paid'`."""
        self.ensure_one()
        for factura in self.factura_ids:
            if factura.payment_state != 'paid':
                factura.payment_order_id = False

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
        if self.tipo in ANTICIPO_TIPOS:
            nuevo_estado = 'aplicado'
        else:
            # Pago Directo que ya pasó por Aprobar (pedido desde Community) regresa a Aprobado.
            nuevo_estado = 'aprobado' if self.approve_date else 'borrador'
        self.write({'move_id': False, 'state': nuevo_estado})

    def _sync_pagos_nativos(self):
        """Pago Directo: los pagos se registran desde la propia factura (botón Pagar o pago
        pendiente aplicado en la factura - pedido del usuario 2026-10-14, política "no hay pago
        sin factura"). Se llama al crear/borrar conciliaciones (account_partial_reconcile.py):
        vincula a esta Orden los pagos conciliados con sus facturas (aparecen en Pagos/Cheques),
        la deja en Aprobado mientras falte saldo, la pasa a Liquidado cuando todas sus facturas
        quedan pagadas, y la regresa a Aprobado si un pago se desconcilia."""
        if self.env.context.get('skip_pago_nativo_sync'):
            return
        for rec in self.filtered(lambda o: o.tipo == 'pago_directo'
                                 and o.state in ('aprobado', 'liquidado')):
            pagos = rec.factura_ids._get_reconciled_payments().filtered(
                lambda p: not p.payment_order_id)
            if pagos:
                pagos.write({'payment_order_id': rec.id})
            facturas = rec.factura_ids.filtered(lambda f: f.state == 'posted')
            pagadas = bool(facturas) and all(
                f.payment_state in ('paid', 'in_payment') for f in facturas)
            if rec.state == 'aprobado' and pagadas:
                rec.state = 'liquidado'
                rec.message_post(body=self.env._(
                    'Liquidada: todas sus facturas quedaron pagadas con pagos registrados desde '
                    'la factura.'))
                rec._push_notify(
                    rec.requested_by_id.partner_id,
                    self.env._('Requisición de Pago liquidada'),
                    self.env._('%(name)s quedó liquidada', name=rec.name))
            elif rec.state == 'liquidado' and not rec.move_id and not pagadas:
                rec.state = 'aprobado'
                rec.message_post(body=self.env._(
                    'Regresó a Aprobado: un pago se desaplicó de sus facturas y ya no están '
                    'pagadas por completo.'))

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
        self._autosugerir_proveedor_materiales_id()  # ver nota en action_approve()
        beneficiario = self._resolve_beneficiario_pago()
        if not beneficiario:
            if self.tipo == 'anticipo_materiales' and self.pagar_a == 'proveedor_directo':
                raise UserError(self.env._(
                    'Define el Proveedor de Materiales antes de crear un pago - con "Pagar a: '
                    'Proveedor Directo" el pago se le hace directo a él.'))
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
            'partner_id': beneficiario.id,
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

    def _get_cuenta_anticipo_por_tipo(self):
        """Cuenta puente fija del tipo (CUENTA_ANTICIPO_POR_TIPO), buscada por código en la compañía de
        la requisición. Vacío si el tipo no tiene una o la cuenta no existe en esa compañía."""
        self.ensure_one()
        codigo = CUENTA_ANTICIPO_POR_TIPO.get(self.tipo)
        if not codigo:
            return self.env['account.account']
        return self.env['account.account'].with_company(self.company_id).search(
            [('code', '=', codigo), ('company_ids', 'in', self.company_id.id)], limit=1)

    def _aplicar_cuenta_anticipo_por_tipo(self):
        for rec in self:
            cuenta = rec._get_cuenta_anticipo_por_tipo()
            if cuenta and rec.cuenta_anticipo_id != cuenta:
                rec.cuenta_anticipo_id = cuenta

    @api.onchange('tipo')
    def _onchange_tipo_cuenta_anticipo(self):
        for rec in self:
            cuenta = rec._get_cuenta_anticipo_por_tipo()
            if cuenta:
                rec.cuenta_anticipo_id = cuenta

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
        if self.tipo == 'anticipo_materiales' and not self.pagar_a:
            raise UserError(self.env._(
                'Define a quién se le paga (Jefe de Técnicos o Proveedor Directo) antes de '
                'aplicar.'))
        self._autosugerir_proveedor_materiales_id()  # ver nota en action_approve()
        beneficiario = self._resolve_beneficiario_pago()
        if not beneficiario:
            if self.tipo == 'anticipo_materiales' and self.pagar_a == 'proveedor_directo':
                raise UserError(self.env._(
                    'Define el Proveedor de Materiales antes de aplicar - con "Pagar a: '
                    'Proveedor Directo" el pago se le hace directo a él.'))
            raise UserError(self.env._('Define el Contacto que recibirá el anticipo.'))
        if not self.monto:
            raise UserError(self.env._('Define el Monto del anticipo.'))
        self._aplicar_cuenta_anticipo_por_tipo()
        if not self.cuenta_anticipo_id:
            raise UserError(self.env._('Define la Cuenta de Anticipos por Liquidar.'))

        payment_vals = {
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': beneficiario.id,
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
        if self.tipo == 'anticipo_materiales':
            # Materiales (2026-10-19, pedido del usuario): el pago queda en BORRADOR para que el
            # Contador lo revise y lo confirme desde Pagos. Liquidar solo netea pagos confirmados.
            self.message_post(body=self.env._(
                'Se generó el pago %s en borrador: confírmalo desde Pagos/Cheques antes de liquidar.',
                payment.name or payment.display_name))
        else:
            payment.action_post()
        self.write({'state': 'aplicado'})
        self._push_notify(
            self.requested_by_id.partner_id,
            self.env._('Requisición de Pago aplicada'),
            self.env._('%(name)s ya se aplicó (Q%(monto).2f)', name=self.name, monto=self.monto or 0.0))

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
        que todavía no generaron una línea de compra. Cada línea usa su `product_id` si ya lo
        tiene y, si no, el **Producto por defecto de Materiales** de la compañía
        (`payment_order_default_material_product_id`, 2026-10-17: así no hay que buscar un
        producto por material). Sin producto por defecto, las líneas sin producto se omiten (esa
        ausencia ES la señal de "ya hay existencia propia, no comprar" - ver el modelo de línea).
        Confirmar/enviar la Orden de Compra es el flujo nativo de la app Compras, no se
        reimplementa aquí. Solo con la requisición ya validada (Aprobada o Aplicada): la compra
        se hace una vez aprobada, no al recibirla (aclarado por el usuario, 2026-10-17)."""
        self.ensure_one()
        if self.tipo != 'anticipo_materiales':
            raise UserError(self.env._(
                'Generar Orden de Compra solo aplica a órdenes de tipo Solicitud de Materiales.'))
        if self.state not in ('en_compras', 'aprobado', 'aplicado'):
            raise UserError(self.env._(
                'La Orden de Compra se genera una vez validada (Aprobada) la requisición.'))
        self._check_puede_gestionar_compras()
        # Mismo auto-sanado que Aprobar/Aplicar: si el proveedor sugerido por Community ya existe
        # como contacto, queda elegido sin que el contable lo busque.
        self._autosugerir_proveedor_materiales_id()
        if not self.proveedor_materiales_id:
            raise UserError(self.env._('Define el Proveedor de Materiales antes de generar la Orden de Compra.'))
        default_product = self.company_id.payment_order_default_material_product_id
        # Compras actualiza precios/cantidades después de cotizar: se reflejan en las líneas de
        # compra que siguen en borrador (Solicitud de Cotización) y el proveedor elegido pasa a
        # la Orden de Compra todavía no confirmada.
        actualizadas = self._actualizar_lineas_compra_borrador()
        borradores = self.purchase_order_ids.filtered(lambda po: po.state in ('draft', 'sent'))
        borradores.filtered(lambda po: po.partner_id != self.proveedor_materiales_id).write(
            {'partner_id': self.proveedor_materiales_id.id})
        lineas = self.material_line_ids.filtered(
            lambda l: (l.product_id or default_product) and not l.purchase_order_line_id)
        if not lineas and borradores:
            return self._action_open_purchase_orders(borradores, actualizadas)
        if not lineas:
            raise UserError(self.env._(
                'No hay líneas de materiales pendientes de comprar con Producto - asigna un '
                'Producto a las líneas, o define el "Producto por defecto para la Orden de '
                'Compra" en Ajustes > Facturación, o revisa si ya se generó la Orden de Compra '
                'para todas.'))
        analytic_distribution = (
            {str(self.analytic_account_id.id): 100.0} if self.analytic_account_id else False)
        purchase_order = self.env['purchase.order'].create({
            'partner_id': self.proveedor_materiales_id.id,
            'company_id': self.company_id.id,
            'origin': self.name,
            'payment_order_id': self.id,
            'order_line': [
                (0, 0, {
                    'product_id': (linea.product_id or default_product).id,
                    'name': linea.description or linea.product_name,
                    'product_qty': linea.qty,
                    'product_uom_id': (linea.product_id or default_product).uom_id.id,
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

    def _check_puede_gestionar_compras(self):
        if not (self.env.user.has_group(COMPRAS_GROUP_XMLID)
                or self.env.user.has_group('account.group_account_manager')):
            raise AccessError(self.env._(
                'Se requiere el permiso de Compras (Usuario) para gestionar la compra de una '
                'Solicitud de Materiales.'))

    def _compras_partners(self):
        return self.env['res.users'].search(
            [('group_ids', 'in', self.env.ref(COMPRAS_GROUP_XMLID).ids)]).partner_id

    def _actualizar_lineas_compra_borrador(self):
        """Pasa precio/cantidad/descripción de cada material a su línea de compra si la Orden de
        Compra sigue en borrador o enviada. Devuelve cuántas líneas cambiaron."""
        self.ensure_one()
        cambiadas = 0
        for linea in self.material_line_ids.filtered('purchase_order_line_id'):
            po_line = linea.purchase_order_line_id
            if po_line.order_id.state not in ('draft', 'sent'):
                continue
            vals = {}
            if po_line.price_unit != linea.estimated_price:
                vals['price_unit'] = linea.estimated_price
            if po_line.product_qty != linea.qty:
                vals['product_qty'] = linea.qty
            nombre = linea.description or linea.product_name
            if nombre and po_line.name != nombre:
                vals['name'] = nombre
            if vals:
                po_line.write(vals)
                cambiadas += 1
        return cambiadas

    def _action_open_purchase_orders(self, ordenes, actualizadas=0):
        if actualizadas:
            self.message_post(body=self.env._(
                'Orden de Compra actualizada con los precios de Compras (%s línea(s)).', actualizadas))
        action = {'type': 'ir.actions.act_window', 'res_model': 'purchase.order',
                  'name': self.env._('Órdenes de Compra'), 'target': 'current'}
        if len(ordenes) == 1:
            action.update({'view_mode': 'form', 'res_id': ordenes.id})
        else:
            action.update({'view_mode': 'list,form', 'domain': [('id', 'in', ordenes.ids)]})
        return action

    def _compras_tiene_factura(self):
        """La factura del proveedor ya está vinculada: una factura real (`factura_ids`) o un
        Documento SAT reclamado (`sat_document_ids`, solo existe en Enterprise)."""
        self.ensure_one()
        rec = self.sudo()  # Compras no necesariamente puede leer facturas (account.move)
        return bool(rec.factura_ids) or bool(getattr(rec, 'sat_document_ids', False))

    def action_fin_compras(self):
        """Botón "Fin de intervención de Compras": Compras ya cotizó, actualizó precios, generó la
        Orden de Compra y vinculó la factura; la requisición pasa a Aprobado para que Contabilidad
        la Aplique. Si con los precios reales el total llegó al umbral y no la aprobó un Gerente,
        primero hace falta su autorización (`action_autorizar_gerente`)."""
        self.ensure_one()
        if self.tipo != 'anticipo_materiales' or self.state != 'en_compras':
            raise UserError(self.env._(
                'Fin de intervención de Compras solo aplica a Solicitudes de Materiales en '
                'Gestión de Compras.'))
        self._check_puede_gestionar_compras()
        if not self._compras_tiene_factura():
            raise UserError(self.env._(
                'Vincula la factura del proveedor (Documento SAT) antes de terminar la '
                'intervención de Compras.'))
        self._sync_monto_desde_total_acreditar()
        threshold = self.company_id.payment_order_approval_threshold or 0.0
        if self.total_acreditar >= threshold and not self.aprobado_por_gerente:
            if not self.env.user.has_group(APPROVER_ALTO_GROUP_XMLID):
                self.requiere_aprobacion_gerente = True
                gerentes = self.env['res.users'].search(
                    [('group_ids', 'in', self.env.ref(APPROVER_ALTO_GROUP_XMLID).ids)]).partner_id
                self._push_notify(
                    gerentes, self.env._('Autorización de Gerente requerida'),
                    self.env._('%(name)s: Compras terminó y el total (Q%(monto).2f) llegó al umbral '
                               'de Q%(umbral).2f. Falta tu autorización para pasarla a '
                               'Contabilidad.', name=self.name, monto=self.total_acreditar,
                               umbral=threshold))
                return {
                    'type': 'ir.actions.client', 'tag': 'display_notification',
                    'params': {
                        'title': self.env._('Falta la autorización del Gerente'),
                        'message': self.env._(
                            'El total con los precios de Compras (Q%(monto).2f) llegó al umbral. '
                            'Se avisó a los Gerentes; cuando uno autorice, pasa a Contabilidad.',
                            monto=self.total_acreditar),
                        'type': 'warning', 'sticky': True,
                        'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
                    },
                }
            self.aprobado_por_gerente = True
        return self._finalizar_compras()

    def action_autorizar_gerente(self):
        """El Gerente autoriza el monto final que dejó Compras y la requisición pasa a Contabilidad."""
        self.ensure_one()
        if not self.env.user.has_group(APPROVER_ALTO_GROUP_XMLID):
            raise AccessError(self.env._('Solo un Aprobador Nivel Alto (Gerente) puede autorizar.'))
        if self.state != 'en_compras' or not self.requiere_aprobacion_gerente:
            raise UserError(self.env._('Esta requisición no está esperando la autorización del Gerente.'))
        self._sync_monto_desde_total_acreditar()
        self.aprobado_por_gerente = True
        return self._finalizar_compras()

    def _finalizar_compras(self):
        self.ensure_one()
        self.write({
            'state': 'aprobado',
            'requiere_aprobacion_gerente': False,
            'compras_finalizado_por_id': self.env.user.id,
            'compras_finalizado_date': fields.Datetime.now(),
        })
        contables = self.env['res.users'].search(
            [('group_ids', 'in', self.env.ref('account.group_account_manager').ids)]).partner_id
        self._push_notify(
            contables, self.env._('Solicitud de Materiales lista para Contabilidad'),
            self.env._('%(name)s: Compras terminó su intervención (Q%(monto).2f). Lista para '
                       'Aplicar.', name=self.name, monto=self.monto or 0.0))
        return True

    def action_imprimir_orden_compra(self):
        """Botón "Imprimir Orden de Compra" (pedido del usuario, 2026-10-17): el Contador abre la
        Solicitud de Materiales que recibió y, de un clic, ve el PDF de la Orden de Compra para
        enviárselo al proveedor. Si todavía quedan líneas por comprar (o no hay ninguna Orden de
        Compra), primero la genera (`action_generar_orden_compra()`, con el producto por defecto
        para las líneas sin producto); después abre el PDF en una pestaña nueva (`/report/pdf/`,
        se visualiza en el navegador, no se descarga). Si hay varias Órdenes de Compra no
        canceladas, salen todas en un solo PDF. El reporte de Compras ya titula "Solicitud de
        Cotización" mientras está en borrador y "Orden de Compra" una vez confirmada."""
        self.ensure_one()
        if self.tipo != 'anticipo_materiales':
            raise UserError(self.env._(
                'Imprimir la Orden de Compra solo aplica a Solicitudes de Materiales.'))
        self._check_puede_gestionar_compras()
        default_product = self.company_id.payment_order_default_material_product_id
        pendientes = self.material_line_ids.filtered(
            lambda l: (l.product_id or default_product) and not l.purchase_order_line_id)
        ordenes = self.env['purchase.order'].search(
            [('payment_order_id', '=', self.id), ('state', '!=', 'cancel')])
        if pendientes or not ordenes or ordenes.filtered(lambda po: po.state in ('draft', 'sent')):
            self.action_generar_orden_compra()
            ordenes = self.env['purchase.order'].search(
            [('payment_order_id', '=', self.id), ('state', '!=', 'cancel')])
        report = self.env.ref('purchase.action_report_purchase_order')
        return {
            'type': 'ir.actions.act_url',
            'url': '/report/pdf/%s/%s' % (
                report.report_name, ','.join(str(i) for i in ordenes.ids)),
            'target': 'new',
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

    def action_view_ordenes_hijas(self):
        """Botón inteligente 'Órdenes Generadas' - mismo patrón que
        action_view_purchase_orders(): form directo si solo hay una, lista si hay más."""
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment.order',
            'name': self.env._('Órdenes Generadas'),
        }
        if len(self.ordenes_hijas_ids) == 1:
            action.update({'view_mode': 'form', 'res_id': self.ordenes_hijas_ids.id})
        else:
            action.update({
                'view_mode': 'list,form',
                'domain': [('id', 'in', self.ordenes_hijas_ids.ids)],
            })
        return action

    def action_generar_excel_transferencia_lote(self):
        """Botón en la Orden ORIGINAL (la que se dividió con "Depositar Directo a Técnicos")
        - genera el Excel de transferencia bancaria masiva directo de sus propias
        `ordenes_hijas_ids`, sin que el usuario tenga que ir a seleccionarlas a mano en la
        lista."""
        self.ensure_one()
        if not self.ordenes_hijas_ids:
            raise UserError(self.env._(
                'Esta Orden todavía no se ha dividido en Órdenes por técnico - no hay nada '
                'que exportar.'))
        return self.ordenes_hijas_ids.action_generar_excel_transferencia()

    def action_generar_excel_transferencia(self):
        """Genera un Excel de transferencia bancaria masiva (Nombre Completo/Banco/Número de
        Cuenta/Tipo de Cuenta/Monto) - una fila por Orden seleccionada. Pensado para el caso de
        "Depositar Directo a Técnicos" (ver `_dividir_en_ordenes_por_tecnico()`/`lote_origen`) -
        se puede llamar tanto desde el botón de la Orden original (`action_generar_excel_
        transferencia_lote()`, que ya trae sus propias `ordenes_hijas_ids`) como seleccionando
        cualquier grupo de Órdenes a mano en la lista (acción de servidor `binding_model_id`,
        Acciones ⚙) - no asume que las Órdenes seleccionadas compartan `lote_origen`, el
        contable puede armar su propia selección libremente.

        Nunca valida `state`/completitud de datos bancarios aquí a propósito - una fila con
        datos faltantes simplemente sale en blanco en el Excel, visible de inmediato para quien
        lo revise antes de subirlo al banco (ya hay un aviso visual - fila roja - en la propia
        lista de líneas de Viáticos, ver la vista, para detectarlo antes de llegar aquí)."""
        if not self:
            raise UserError(self.env._(
                'Selecciona al menos una Orden de Pago antes de generar el Excel.'))
        import base64
        import io

        import xlsxwriter

        buffer = io.BytesIO()
        workbook = xlsxwriter.Workbook(buffer, {'in_memory': True})
        sheet = workbook.add_worksheet('Transferencias')
        encabezado = workbook.add_format({'bold': True, 'bg_color': '#DCE7F1', 'border': 1})
        sheet.write_row(0, 0, [
            'Orden de Pago', 'Nombre Completo', 'Banco', 'Número de Cuenta',
            'Tipo de Cuenta', 'Monto',
        ], encabezado)
        tipo_cuenta_labels = dict(self._fields['tipo_cuenta'].selection)
        for fila, orden in enumerate(self, start=1):
            sheet.write(fila, 0, orden.name or '')
            sheet.write(fila, 1, orden.partner_id.name or '')
            sheet.write(fila, 2, orden.banco or '')
            sheet.write(fila, 3, orden.cuenta_acreditar or '')
            sheet.write(fila, 4, tipo_cuenta_labels.get(orden.tipo_cuenta, '') or '')
            sheet.write_number(fila, 5, orden.monto or 0.0)
        sheet.set_column(0, 0, 16)
        sheet.set_column(1, 1, 28)
        sheet.set_column(2, 2, 20)
        sheet.set_column(3, 3, 20)
        sheet.set_column(4, 4, 14)
        sheet.set_column(5, 5, 14)
        workbook.close()

        nombre_archivo = self.env._('Transferencia_Bancaria_%(fecha)s.xlsx', fecha=fields.Date.context_today(self))
        wizard = self.env['account.payment.order.export.transferencia.wizard'].create({
            'data': base64.b64encode(buffer.getvalue()),
            'name': nombre_archivo,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': (
                f'/web/content/account.payment.order.export.transferencia.wizard/'
                f'{wizard.id}/data/{nombre_archivo}?download=true'
            ),
            'target': 'self',
        }

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

