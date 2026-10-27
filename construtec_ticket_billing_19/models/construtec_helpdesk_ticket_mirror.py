# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import api, fields, models


class ConstructecHelpdeskTicketMirror(models.Model):
    _name = 'construtec.helpdesk.ticket.mirror'
    _description = (
        'Espejo de un Ticket de Helpdesk enviado desde Odoo Community (construtec_helpdesk_'
        'field_service), vía API, cuando su costo_total/etapa cambia. Deliberadamente NO un '
        'documento de negocio real - Community y Enterprise son bases de datos separadas, así '
        'que este modelo solo guarda referencia plana (número/nombre/costo/etapa/cliente en '
        'texto) más un vínculo real a la Factura (`move_id`, un Many2one normal a account.move, '
        'este SÍ un modelo local de esta misma base) que el contable elige a mano. `billing_'
        'state` nunca se escribe manualmente - se deriva 100% del estado real de esa Factura, '
        'para que nunca se desincronice de ella.'
    )
    _order = 'received_date desc'

    number = fields.Char(
        string='No. Ticket', required=True, index=True,
        help='El propio `number` del Ticket en Community - clave de upsert usada por '
             'sync_from_community(). NUNCA un id local de este registro en Enterprise.')
    name = fields.Char(string='Título (Community)')
    ticket_label = fields.Char(
        string='Ticket', compute='_compute_ticket_label', store=True,
        help='"`number`" a secas si el ticket nunca tuvo un título propio distinto (el caso '
             'normal - `name` llega igual a `number` desde Community), o "`number` - `name`" '
             'si sí difieren - mismo criterio que `helpdesk.ticket._compute_display_name()` '
             '(Community). Evita mostrar dos columnas casi siempre idénticas en las listas.')
    costo_plan = fields.Monetary(
        string='Costo por Plan', currency_field='currency_id',
        help='Lo que vale el servicio según el Plan de Servicio del Ticket en Community (tickets '
             'consumidos con recargos × precio por ticket del cliente), tal como llegó en el último '
             'empuje - un espejo, no algo calculado aquí.')
    costo_total = fields.Monetary(
        string='Costo por Requisiciones de Pago', currency_field='currency_id',
        help='Suma de las Requisiciones de Pago vinculadas al Ticket en Community (payment_order_ids) '
             'ya Aprobadas, Aplicadas o Liquidadas, tal como llegó en el último empuje - un espejo, '
             'no algo calculado aquí. (El nombre del campo se conserva por compatibilidad: antes era '
             'el único costo; el total de los dos es `costo_general`.)')
    costo_general = fields.Monetary(
        string='Costo Total', currency_field='currency_id',
        help='Suma de Costo por Plan + Costo por Requisiciones de Pago, tal como llegó en el último '
             'empuje de Community (2026-10-19: ahora el Ticket manda los tres costos).')
    # Costeo real (2026-10-27): calculado AQUÍ desde las requisiciones vinculadas (que ya traen su
    # costo por facturas y traslados), no empujado desde Community - así quien factura ve siempre
    # el costo real actual. Solo cuentan requisiciones Aprobadas/Aplicadas/Liquidadas.
    costo_viaticos = fields.Monetary(
        string='Viáticos', currency_field='currency_id', compute='_compute_costeo_real', store=True,
        help='`monto` de las requisiciones de Viáticos vigentes.')
    costo_materiales = fields.Monetary(
        string='Materiales', currency_field='currency_id', compute='_compute_costeo_real', store=True,
        help='`monto` de las requisiciones de Materiales vigentes.')
    costo_pago_directo = fields.Monetary(
        string='Pagos Directos', currency_field='currency_id', compute='_compute_costeo_real',
        store=True, help='`monto` de las requisiciones de Pago Directo vigentes.')
    costo_facturas = fields.Monetary(
        string='Facturas Vinculadas', currency_field='currency_id', compute='_compute_costeo_real',
        store=True,
        help='Subtotal sin IVA de las facturas de proveedor realmente vinculadas a las requisiciones.')
    costo_traslados = fields.Monetary(
        string='Traslados de Bodega', currency_field='currency_id', compute='_compute_costeo_real',
        store=True,
        help='Costo de inventario del material que salió de bodega hacia el cliente.')
    costo_real = fields.Monetary(
        string='Costo Real', currency_field='currency_id', compute='_compute_costeo_real', store=True,
        help='Facturas vinculadas + Traslados de bodega: lo que el ticket realmente costó según sus '
             'requisiciones (a diferencia de Viáticos/Materiales/Pagos Directos, que son lo pedido).')
    currency_id = fields.Many2one(
        'res.currency', string='Moneda', default=lambda self: self.env.company.currency_id)
    stage_name = fields.Char(string='Etapa (Community)')
    is_closed = fields.Boolean(
        string='Hecho (Community)',
        help='Refleja `helpdesk.ticket.closed` (Community) al momento del último empuje - '
             'un ticket que todavía no está en una etapa Cerrada no debe poder facturarse '
             '(ver el domain de `account.move.ticket_mirror_ids`).')
    partner_name = fields.Char(string='Cliente (Community)')
    analytic_account_id = fields.Many2one(
        'account.analytic.account', string='Cuenta Analítica',
        help='Ubicación del Ticket en Community - relación REAL (no texto): resuelta al '
             'sincronizar vía `analytic_enterprise_ref`, el mismo `account.analytic.account` '
             'de esta base que Community solo espejea - mismo patrón que `account.payment.'
             'order._resolve_analytic_enterprise_ref()` (construtec_account_payment_order_19). '
             'Alimenta la distribución analítica automática de la Factura, ver `account.move.'
             '_compute_ticket_analytic_distribution()`.')
    company_id = fields.Many2one(
        'res.company', string='Compañía', default=lambda self: self.env.company)
    origin_record_id = fields.Integer(
        string='ID en Community', readonly=True, copy=False,
        help='El id real de este Ticket en Community - junto con `origin_base_url`, arma '
             '`community_url`. Nunca se usa para buscar/vincular nada, solo arma un link de '
             'texto clickeable - mismo criterio ya usado por `account.payment.order.'
             'origin_record_id` (construtec_account_payment_order_19).')
    origin_base_url = fields.Char(string='URL de Community', readonly=True, copy=False)
    community_url = fields.Char(
        string='Ver Ticket en Community', compute='_compute_community_url')

    move_id = fields.Many2one(
        'account.move', string='Factura', domain=[('move_type', '=', 'out_invoice')],
        help='La Factura real de este Ticket (uno o varios Tickets pueden compartir la misma '
             'Factura) - la elige el contable a mano mientras arma la factura, para ver el '
             'costo acumulado de los Tickets ya vinculados antes de confirmarla.')
    reconciled_payment_ids = fields.Many2many(
        'account.payment', string='Pagos Conciliados', compute='_compute_reconciled_payment_ids')
    payment_id = fields.Many2one(
        'account.payment', string='Pago', compute='_compute_billing_state', store=True,
        help='El primer pago conciliado contra la Factura, una vez que `billing_state` llega '
             'a "cobrado" - MVP: si hay varios pagos parciales, solo se expone el primero.')
    billing_state = fields.Selection(
        selection=[
            ('no_facturado', 'Sin Facturar'),
            ('facturado', 'Facturado'),
            ('cobrado', 'Cobrado'),
        ],
        string='Estado de Facturación', compute='_compute_billing_state', store=True,
        help='Derivado 100% de `move_id.state`/`move_id.payment_state` - nunca editable a '
             'mano, así nunca se desincroniza de la Factura real.')
    received_date = fields.Datetime(
        string='Última Recepción', default=fields.Datetime.now, readonly=True)
    payment_order_ids = fields.One2many(
        'account.payment.order', 'ticket_mirror_id', string='Requisiciones de Pago', readonly=True,
        help='Las Requisiciones de Pago recibidas de Community que pertenecen a este Ticket.')

    _number_uniq = models.Constraint(
        'unique(number)',
        'Ya existe un Ticket con ese número - sync_from_community() debió actualizarlo, no '
        'crear uno nuevo.',
    )

    @api.depends('payment_order_ids.state', 'payment_order_ids.tipo', 'payment_order_ids.monto',
                 'payment_order_ids.costo_facturas', 'payment_order_ids.costo_traslados')
    def _compute_costeo_real(self):
        for rec in self:
            vigentes = rec.payment_order_ids.filtered(
                lambda o: o.state in ('en_compras', 'aprobado', 'aplicado', 'liquidado'))
            rec.costo_viaticos = sum(vigentes.filtered(
                lambda o: o.tipo == 'anticipo_viaticos').mapped('monto'))
            rec.costo_materiales = sum(vigentes.filtered(
                lambda o: o.tipo == 'anticipo_materiales').mapped('monto'))
            rec.costo_pago_directo = sum(vigentes.filtered(
                lambda o: o.tipo == 'pago_directo').mapped('monto'))
            rec.costo_facturas = sum(vigentes.mapped('costo_facturas'))
            rec.costo_traslados = sum(vigentes.mapped('costo_traslados'))
            rec.costo_real = rec.costo_facturas + rec.costo_traslados

    @api.depends('move_id.state', 'move_id.payment_state', 'move_id.reconciled_payment_ids')
    def _compute_billing_state(self):
        for rec in self:
            move = rec.move_id
            if not move or move.state != 'posted':
                rec.billing_state = 'no_facturado'
                rec.payment_id = False
            elif move.payment_state in ('paid', 'in_payment'):
                rec.billing_state = 'cobrado'
                rec.payment_id = move.reconciled_payment_ids[:1]
            else:
                rec.billing_state = 'facturado'
                rec.payment_id = False

    # Compute aparte: reconciled_payment_ids no se guarda y los otros dos sí; compartir el
    # método daba el warning de 'store'/'compute_sudo' inconsistentes en Odoo 19.
    @api.depends('move_id.reconciled_payment_ids')
    def _compute_reconciled_payment_ids(self):
        for rec in self:
            rec.reconciled_payment_ids = rec.move_id.reconciled_payment_ids

    @api.depends('number', 'name')
    def _compute_ticket_label(self):
        for rec in self:
            if rec.name and rec.name != rec.number:
                rec.ticket_label = f'{rec.number} - {rec.name}'
            else:
                rec.ticket_label = rec.number

    @api.depends('origin_record_id', 'origin_base_url')
    def _compute_community_url(self):
        for rec in self:
            if rec.origin_record_id and rec.origin_base_url:
                rec.community_url = (
                    f'{rec.origin_base_url}/web#id={rec.origin_record_id}'
                    f'&model=helpdesk.ticket&view_type=form')
            else:
                rec.community_url = False

    def _resolve_analytic_enterprise_ref(self, vals):
        """Resuelve `analytic_enterprise_ref` (enviado por `_prepare_ticket_sync_vals()`,
        Community) hacia un `analytic_account_id` REAL de esta base - mismo patrón que
        `account.payment.order._resolve_analytic_enterprise_ref()` (construtec_account_
        payment_order_19): el ref YA es el id real en Enterprise (Community solo espejea esa
        cuenta analítica, nunca la crea de cero), así que un `browse()` directo alcanza.

        A diferencia de ese otro método (que solo AGREGA, nunca limpia), aquí Community manda
        `analytic_enterprise_ref` en CADA push, incluso vacío (`False`) si el ticket todavía no
        tiene Ubicación - así que la clave, cuando está presente en el payload, es la fuente de
        verdad completa: se sobreescribe `analytic_account_id` con lo que traiga, resuelto o
        vacío, para que la Ubicación se pueda corregir/quitar en Community sin quedar pegada
        aquí para siempre."""
        if 'analytic_enterprise_ref' not in vals:
            return
        ref = vals.pop('analytic_enterprise_ref')
        analytic_account = self.env['account.analytic.account'].browse(int(ref)).exists() if ref else False
        vals['analytic_account_id'] = analytic_account.id if analytic_account else False

    @api.model
    def sync_from_community(self, vals):
        """Punto de entrada único, llamado vía XML-RPC estándar de Odoo (`/jsonrpc`) desde
        `construtec_helpdesk_field_service::_sync_ticket_to_enterprise()` (Community) cada vez
        que `costo_total`/`stage_id` del Ticket cambia. Upsert por `number` - Community reenvía
        el Ticket completo en cada cambio, nunca solo un delta.

        Deliberadamente SIN `sudo()` - el usuario de integración necesita permiso real (no
        prestado) sobre este modelo para que el upsert funcione vía RPC. A diferencia de otros
        mirrors de este proyecto (que usan un grupo dedicado de mínimo privilegio), este
        reutiliza `account.group_account_manager` ("Facturación: Administrador", ya existente,
        decisión explícita del usuario 2026-09-04: "reutiliza los grupos, no crea grupos
        nuevos") - el usuario de integración debe agregarse a ESE grupo. Esto es más amplio que
        un grupo dedicado (cualquier miembro de ese grupo, no solo la integración, ya tenía
        create+write+unlink aquí desde antes) - el trade-off aceptado es simplicidad de
        Ajustes/seguridad sobre superficie de ataque mínima."""
        number = vals.get('number')
        if not number:
            raise ValueError('Falta number - no se puede actualizar sin la clave de upsert.')
        vals = dict(vals, received_date=fields.Datetime.now())
        if not vals.get('company_id'):
            vals['company_id'] = self.env.company.id
        self._resolve_analytic_enterprise_ref(vals)
        payment_order_refs = vals.pop('payment_order_refs', None)
        entry = self.search([('number', '=', number)], limit=1)
        if entry:
            entry.write(vals)
        else:
            entry = self.create(vals)
        if payment_order_refs is not None:
            entry._link_payment_orders(payment_order_refs)
        return entry.id

    @api.model
    def _get_or_create_by_number(self, number):
        entry = self.search([('number', '=', number)], limit=1)
        return entry or self.create({'number': number, 'name': number})

    def _link_payment_orders(self, refs):
        """Vincula a este ticket las requisiciones recibidas cuyo `external_ref` (el nombre en
        Community) viene en `refs`, y suelta las que ya no le pertenecen. Las requisiciones que
        todavía no llegaron a Enterprise se vinculan solas al llegar (`ticket_number`).
        `sudo()`: el usuario de integración no necesita permiso de escritura sobre requisiciones."""
        self.ensure_one()
        Order = self.env['account.payment.order'].sudo()
        nuevas = Order.search([('external_ref', 'in', refs or []), ('origin', '=', 'synced'),
                               ('ticket_mirror_id', '!=', self.id)]) if refs else Order
        if nuevas:
            nuevas.write({'ticket_mirror_id': self.id})
        sobrantes = Order.search([('ticket_mirror_id', '=', self.id),
                                  ('external_ref', 'not in', refs or [])])
        if sobrantes:
            sobrantes.write({'ticket_mirror_id': False})
