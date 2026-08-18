from datetime import date

from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    sat_document_id = fields.Many2one(
        'construtec.sat.document', string='Documento SAT', readonly=True, copy=False,
        help='Documento SAT (DTE) desde el que se generó esta factura, si vino importado vía '
             'la bandeja de documentos SAT en vez de crearse manualmente.')

    def action_view_sat_document(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'construtec.sat.document',
            'view_mode': 'form',
            'res_id': self.sat_document_id.id,
            'target': 'current',
        }

    def unlink(self):
        documentos_sat = self.sat_document_id
        res = super().unlink()
        documentos_sat._sat_revertir_a_pendiente()
        return res

    def action_post(self):
        res = super().action_post()
        # Si esta factura ya tenía una constancia de retención vinculada
        # ANTES de contabilizarse (ej. la retención se importó primero y
        # construtec.sat.retention.line._sat_buscar_documento ya había
        # resuelto sat_document_id, pero move_id todavía no existía o no
        # estaba posted) - ahora que ya quedó posted, se intenta aplicar el
        # asiento de la retención. El caso inverso (retención importada
        # DESPUÉS de que la factura ya está posted) lo cubre
        # _sat_intentar_aplicar_retencion_automatica desde el otro lado, al
        # vincular. Solo aplica a direction='emitida' (una recibida nunca
        # tiene una retención que Construtec haya recibido).
        moves_emitidas = self.filtered(
            lambda m: m.sat_document_id and m.sat_document_id.direction == 'emitida')
        if moves_emitidas:
            lineas_pendientes = self.env['construtec.sat.retention.line'].search([
                ('sat_document_id', 'in', moves_emitidas.sat_document_id.ids),
                ('payment_id', '=', False),
            ])
            for linea in lineas_pendientes:
                linea._sat_intentar_aplicar_retencion_automatica()
        return res

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
