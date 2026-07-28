from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    partida_contable = fields.Integer(
        string='No. Partida', readonly=True, copy=False, index=True,
        help='Número de partida contable, asignado secuencialmente al contabilizar el asiento. '
             'Usado por el Libro Diario y el Libro Mayor.')

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        for move in posted.filtered(lambda m: not m.partida_contable):
            move.partida_contable = self.env['ir.sequence'].next_by_code('account.move.partida_contable') or 0
        return posted
