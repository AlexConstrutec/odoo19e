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
    name = fields.Char(string='Ticket')
    costo_total = fields.Monetary(
        string='Costo Total', currency_field='currency_id',
        help='Suma de las Órdenes de Pago vinculadas al Ticket en Community (payment_order_ids), '
             'tal como llegó en el último empuje - un espejo, no algo calculado aquí.')
    currency_id = fields.Many2one(
        'res.currency', string='Moneda', default=lambda self: self.env.company.currency_id)
    stage_name = fields.Char(string='Etapa (Community)')
    partner_name = fields.Char(string='Cliente (Community)')
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
        'account.payment', string='Pagos Conciliados', compute='_compute_billing_state')
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

    _number_uniq = models.Constraint(
        'unique(number)',
        'Ya existe un Ticket con ese número - sync_from_community() debió actualizarlo, no '
        'crear uno nuevo.',
    )

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
            rec.reconciled_payment_ids = move.reconciled_payment_ids

    @api.depends('origin_record_id', 'origin_base_url')
    def _compute_community_url(self):
        for rec in self:
            if rec.origin_record_id and rec.origin_base_url:
                rec.community_url = (
                    f'{rec.origin_base_url}/web#id={rec.origin_record_id}'
                    f'&model=helpdesk.ticket&view_type=form')
            else:
                rec.community_url = False

    @api.model
    def sync_from_community(self, vals):
        """Punto de entrada único, llamado vía XML-RPC estándar de Odoo (`/jsonrpc`) desde
        `construtec_helpdesk_field_service::_sync_ticket_to_enterprise()` (Community) cada vez
        que `costo_total`/`stage_id` del Ticket cambia. Upsert por `number` - Community reenvía
        el Ticket completo en cada cambio, nunca solo un delta.

        Deliberadamente SIN `sudo()` - la seguridad de este endpoint depende por completo de que
        el usuario de integración (`group_ticket_billing_sync_integration`, create+write+read
        SOLO sobre este modelo) sea el único con permiso real de escribir aquí vía RPC - mismo
        criterio ya documentado en `construtec.materials.catalog.mirror::sync_from_enterprise()`
        (construtec_sat_catalog_sync_19)."""
        number = vals.get('number')
        if not number:
            raise ValueError('Falta number - no se puede actualizar sin la clave de upsert.')
        vals = dict(vals, received_date=fields.Datetime.now())
        if not vals.get('company_id'):
            vals['company_id'] = self.env.company.id
        entry = self.search([('number', '=', number)], limit=1)
        if entry:
            entry.write(vals)
        else:
            entry = self.create(vals)
        return entry.id
