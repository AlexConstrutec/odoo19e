from odoo import api, fields, models
from odoo.exceptions import UserError


class AccountPaymentOrderRequestCrearAnticipoWizard(models.TransientModel):
    _name = 'account.payment.order.request.crear.anticipo.wizard'
    _description = 'Crear Anticipo desde una Solicitud de Pago'

    request_id = fields.Many2one('account.payment.order.request', string='Solicitud',
                                  required=True, readonly=True)
    partner_id = fields.Many2one(
        'res.partner', string='Contacto', required=True,
        default=lambda self: self.env['account.payment.order.request'].browse(
            self.env.context.get('default_request_id')).employee_partner_id,
        help='Contacto que recibirá el Anticipo. Se prellena con el Empleado Solicitante de la '
             'Solicitud (ya es un contacto real de ESTA base, resuelto vía employee_partner_id/'
             'employee_enterprise_ref al recibir la Solicitud) - editable por si hace falta '
             'entregarlo a otro contacto.')
    journal_id = fields.Many2one('account.journal', string='Diario', required=True,
                                  domain=[('type', '=', 'bank')])
    available_payment_method_line_ids = fields.Many2many(
        'account.payment.method.line', compute='_compute_available_payment_method_line_ids',
        help='Auxiliar para el dominio de `payment_method_line_id` - ver el mismo campo en '
             'account_payment_order.py (motivo: InvalidDomainError con una lista vacía al '
             'navegar journal_id.outbound_payment_method_line_ids directo en un domain string).')
    payment_method_line_id = fields.Many2one(
        'account.payment.method.line', string='Método de Pago',
        domain="[('id', 'in', available_payment_method_line_ids)]")

    @api.depends('journal_id')
    def _compute_available_payment_method_line_ids(self):
        for rec in self:
            rec.available_payment_method_line_ids = rec.journal_id.outbound_payment_method_line_ids
    cuenta_anticipo_id = fields.Many2one(
        'account.account', string='Cuenta de Anticipos por Liquidar', required=True,
        domain=[('account_type', 'in', ('asset_receivable', 'liability_payable'))])
    monto = fields.Float(string='Monto', required=True)

    def action_confirmar(self):
        self.ensure_one()
        if self.request_id.payment_order_id:
            raise UserError(self.env._('Esta solicitud ya tiene una Orden de Pago asociada.'))

        vals = {
            'tipo': 'anticipo',
            'partner_id': self.partner_id.id,
            'journal_id': self.journal_id.id,
            'cuenta_anticipo_id': self.cuenta_anticipo_id.id,
            'monto': self.monto,
        }
        if self.payment_method_line_id:
            vals['payment_method_line_id'] = self.payment_method_line_id.id
        payment_order = self.env['account.payment.order'].create(vals)
        self.request_id.payment_order_id = payment_order.id

        redirect = {
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment.order',
            'view_mode': 'form',
            'res_id': payment_order.id,
            'target': 'current',
        }
        pendientes = payment_order._find_anticipos_sin_liquidar(self.partner_id, exclude=payment_order)
        if not pendientes:
            return redirect
        # No bloquea la creación - puede ser intencional (viáticos de dos viajes distintos,
        # por ejemplo). 'next' es un mecanismo nativo de display_notification (ver
        # client_actions.js) para encadenar una acción después de mostrar el aviso.
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._('Anticipos pendientes de liquidar'),
                'message': self.env._(
                    '%(contacto)s ya tiene %(cantidad)s Anticipo(s) aplicado(s) sin Liquidación '
                    'registrada todavía (%(nombres)s) - revisa si corresponde liquidarlos antes '
                    'de entregar uno nuevo.',
                    contacto=self.partner_id.name, cantidad=len(pendientes),
                    nombres=', '.join(pendientes.mapped('name'))),
                'type': 'warning',
                'sticky': True,
                'next': redirect,
            },
        }
