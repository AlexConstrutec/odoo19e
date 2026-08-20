from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class AccountPaymentOrder(models.Model):
    _name = 'account.payment.order'
    _description = 'Orden de Pago (Anticipo / Liquidación / Pago Directo)'
    _order = 'fecha desc'

    tipo = fields.Selection([
        ('anticipo', 'Anticipo'),
        ('liquidacion', 'Liquidación'),
        ('pago_directo', 'Pago Directo'),
    ], string='Tipo', required=True, default='anticipo')
    name = fields.Char(string='Nombre', compute='_compute_name', store=True, readonly=False)
    no_liquidacion = fields.Integer(string='No. Liquidación')
    fecha = fields.Date(string='Fecha', required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one('account.journal', string='Diario', required=True)
    company_id = fields.Many2one('res.company', string='Compañía', required=True,
                                  default=lambda self: self.env.company.id)
    user_id = fields.Many2one('res.users', string='Usuario', default=lambda self: self.env.user.id)
    partner_id = fields.Many2one('res.partner', string='Contacto')
    currency_id = fields.Many2one('res.currency', string='Moneda',
                                   default=lambda self: self.env.company.currency_id.id)
    cuenta_ajuste_id = fields.Many2one('account.account', string='Cuenta de Ajuste')
    move_id = fields.Many2one('account.move', string='Asiento', readonly=True, copy=False)
    anticipo_id = fields.Many2one('account.payment.order', string='Anticipo de Origen',
                                   domain=[('tipo', '=', 'anticipo')], copy=False,
                                   help='Anticipo del que se origina esta Liquidación. Una Liquidación no se '
                                        'puede crear directamente - debe generarse desde el botón "Registrar '
                                        'Liquidación" de un Anticipo ya aplicado.')
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
        ('aplicado', 'Aplicado'),
        ('cancelado', 'Cancelado'),
    ], string='Estado', default='borrador', copy=False)

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

    @api.constrains('tipo', 'anticipo_id')
    def _check_anticipo_id(self):
        for rec in self:
            if rec.tipo == 'liquidacion' and not rec.anticipo_id:
                raise ValidationError(rec.env._(
                    'Una Liquidación debe originarse desde un Anticipo: usa el botón "Registrar '
                    'Liquidación" en el Anticipo correspondiente en vez de crearla directamente.'))

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

    def action_conciliar(self):
        self.ensure_one()
        if self.tipo not in ('liquidacion', 'pago_directo'):
            raise UserError(self.env._(
                'Conciliar solo aplica a órdenes de tipo Liquidación o Pago Directo.'))
        self._check_es_administrador_contable()

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

        if round(total, 2) != 0 and not self.cuenta_ajuste_id:
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

    def action_aplicar(self):
        self.ensure_one()
        if self.tipo != 'anticipo':
            raise UserError(self.env._('Aplicar solo se usa para órdenes de tipo Anticipo.'))
        self._check_es_administrador_contable()
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
        }
        if self.payment_method_line_id:
            payment_vals['payment_method_line_id'] = self.payment_method_line_id.id
        payment = self.env['account.payment'].create(payment_vals)
        payment.action_post()
        self.write({'payment_id': payment.id, 'state': 'aplicado'})

        aviso = self._aviso_posible_pago_directo()
        if aviso:
            return aviso
        return True

    @api.model
    def _find_anticipos_sin_liquidar(self, partner, exclude=None):
        """Anticipos ya APLICADOS de este contacto que todavía no tienen una Liquidación
        registrada (ver action_registrar_liquidacion(), que fija `anticipo_id` en la
        Liquidación resultante) - se usa para avisar antes de entregar un Anticipo nuevo a
        alguien que ya tiene uno pendiente de liquidar, sin bloquear la operación (puede ser
        intencional: viáticos de dos viajes distintos, por ejemplo)."""
        domain = [
            ('tipo', '=', 'anticipo'),
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
        if self.tipo != 'anticipo':
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
