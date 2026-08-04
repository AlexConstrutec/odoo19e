from odoo import api, fields, models
from odoo.exceptions import UserError


class AccountPaymentOrder(models.Model):
    _name = 'account.payment.order'
    _description = 'Orden de Pago (Anticipo / Liquidación / Pago Directo)'
    _order = 'fecha desc'

    tipo = fields.Selection([
        ('anticipo', 'Anticipo'),
        ('liquidacion', 'Liquidación'),
        ('pago_directo', 'Pago Directo'),
    ], string='Tipo', required=True, default='liquidacion')
    name = fields.Char(string='Nombre', compute='_compute_name', store=True, readonly=False)
    no_liquidacion = fields.Integer(string='No. Liquidación')
    fecha = fields.Date(string='Fecha', required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one('account.journal', string='Diario', required=True)
    company_id = fields.Many2one('res.company', string='Compañía', required=True,
                                  default=lambda self: self.env.company.id)
    user_id = fields.Many2one('res.users', string='Usuario', default=lambda self: self.env.user.id)
    partner_id = fields.Many2one('res.partner', string='Contacto')
    cuenta_ajuste_id = fields.Many2one('account.account', string='Cuenta de Ajuste')
    move_id = fields.Many2one('account.move', string='Asiento', readonly=True, copy=False)
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
        if self.tipo != 'liquidacion':
            raise UserError(self.env._(
                'Conciliar solo aplica a órdenes de tipo Liquidación (Anticipo y Pago Directo '
                'aún no están implementados).'))

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
        if self.tipo != 'liquidacion':
            raise UserError(self.env._(
                'Cancelar solo aplica a órdenes de tipo Liquidación (Anticipo y Pago Directo '
                'aún no están implementados).'))
        if self.move_id:
            for line in self.move_id.line_ids:
                if line.reconciled:
                    line.remove_move_reconcile()
            self.move_id.button_cancel()
            self.move_id.unlink()
        self.write({'move_id': False, 'state': 'borrador'})
        return True
