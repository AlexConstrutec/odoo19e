from odoo import api, fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    payment_order_id = fields.Many2one('account.payment.order', string='Orden de Pago', ondelete='restrict',
                                        store=True)
    payment_order_ids = fields.Many2many(
        'account.payment.order', string='Historial de Órdenes de Pago', copy=False,
        help='Todas las Órdenes de Pago que alguna vez reclamaron esta factura - a diferencia de '
             'payment_order_id (el candado ACTUAL, que _liberar_facturas_con_saldo() limpia al '
             'liberar una factura parcialmente pagada para que otra Orden la tome, ver "Facturas '
             'pagadas en varios abonos" en el CLAUDE.md de este módulo), este campo nunca se '
             'limpia: es un registro histórico aditivo de cada Orden que alguna vez pagó (total o '
             'parcialmente) esta factura, incluidas las que ya se liberaron.')

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        for vals, move in zip(vals_list, moves):
            if vals.get('payment_order_id'):
                move.payment_order_ids = [(4, vals['payment_order_id'])]
        return moves

    def _check_payment_order_disponible(self, new_order_id):
        """Candado central contra la brecha de seguridad de vincular una factura ya pagada, o ya
        comprometida en otra Orden de Pago viva - vive AQUÍ (en el write() de account.move, no
        solo en el código que resuelve una Solicitud sincronizada desde Community) para que
        aplique sin importar el camino: el widget many2many normal de `factura_ids` en
        Enterprise (un contador vinculando a mano), o la sincronización desde Community (ver
        `account_payment_order.py::_resolve_factura_origin_ids()`). `payment_order_id` es un
        Many2one normal, sin protección propia - escribirlo sin este chequeo le robaría el
        vínculo a la Orden anterior en silencio, sin ningún error."""
        for move in self:
            if move.payment_state == 'paid' and move.payment_order_id.id != new_order_id:
                raise UserError(move.env._(
                    'La factura %s ya está completamente pagada.', move.name))
            if move.payment_order_id and move.payment_order_id.id != new_order_id:
                otra = move.payment_order_id
                if otra.state not in ('rechazado', 'cancelado'):
                    raise UserError(move.env._(
                        'La factura %(factura)s ya está vinculada a la Orden de Pago '
                        '%(orden)s (estado: %(estado)s) - libérala ahí primero.',
                        factura=move.name, orden=otra.name, estado=otra.state))

    def write(self, vals):
        if vals.get('payment_order_id'):
            self._check_payment_order_disponible(vals['payment_order_id'])
        afectadas = self.env['account.move']
        if 'state' in vals and vals['state'] != 'posted':
            afectadas = self.filtered(
                lambda m: m.state == 'posted' and m.payment_order_id
                and m.payment_order_id.state == 'liquidado')
        res = super().write(vals)
        if vals.get('payment_order_id'):
            self.payment_order_ids = [(4, vals['payment_order_id'])]
        if afectadas:
            nuevo_state_label = dict(self._fields['state'].selection).get(vals['state'], vals['state'])
            for orden in afectadas.mapped('payment_order_id'):
                docs = afectadas.filtered(lambda m, orden=orden: m.payment_order_id == orden)
                orden._reaccionar_a_documento_desconciliado(docs, nuevo_state_label)
        return res
