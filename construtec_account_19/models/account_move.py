from datetime import date

from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    partida_numero = fields.Integer(
        string='No. Partida',
        copy=False,
        help="Numeración consecutiva de la partida contable, por compañía y "
             "reiniciada cada año según la fecha contable. Se asigna sola al "
             "contabilizar el asiento; si se escribe un número manualmente, "
             "las demás partidas del mismo año se reordenan para acomodarla "
             "en esa posición.",
    )

    @api.model
    def _partida_domain(self, company, year):
        return [
            ('company_id', '=', company.id),
            ('state', '=', 'posted'),
            ('date', '>=', date(year, 1, 1)),
            ('date', '<=', date(year, 12, 31)),
        ]

    def _recompute_partida_numeros(self, company, year):
        moves = self.env['account.move'].search(
            self._partida_domain(company, year),
            order='date asc, create_date asc, id asc',
        )
        for index, move in enumerate(moves, start=1):
            if move.partida_numero != index:
                move.with_context(skip_partida_recompute=True).partida_numero = index

    def _reorder_partida_manual(self, new_number):
        self.ensure_one()
        siblings = self.env['account.move'].search(
            self._partida_domain(self.company_id, self.date.year) + [('id', '!=', self.id)],
            order='partida_numero asc, date asc, create_date asc, id asc',
        )
        ordered = list(siblings)
        position = max(1, min(new_number, len(ordered) + 1)) - 1
        ordered.insert(position, self)
        for index, move in enumerate(ordered, start=1):
            if move.partida_numero != index:
                move.with_context(skip_partida_recompute=True).partida_numero = index

    def write(self, vals):
        skip = self.env.context.get('skip_partida_recompute')
        manual_numbers = {}
        if 'partida_numero' in vals and not skip:
            vals = dict(vals)
            manual_number = vals.pop('partida_numero')
            for move in self:
                if move.state == 'posted':
                    manual_numbers[move.id] = manual_number

        before = {move.id: (move.state, move.date) for move in self}
        res = super().write(vals)

        if not skip:
            affected = set()
            for move in self:
                old_state, old_date = before[move.id]
                new_state, new_date = move.state, move.date
                if old_state == 'posted' and new_state != 'posted':
                    move.with_context(skip_partida_recompute=True).partida_numero = False
                    affected.add((move.company_id.id, old_date.year))
                elif new_state == 'posted' and (old_state != 'posted' or old_date != new_date):
                    affected.add((move.company_id.id, new_date.year))
                    if old_state == 'posted' and old_date != new_date:
                        affected.add((move.company_id.id, old_date.year))

            for move_id, number in manual_numbers.items():
                self.browse(move_id)._reorder_partida_manual(number)

            for company_id, year in affected:
                self._recompute_partida_numeros(self.env['res.company'].browse(company_id), year)

        return res
