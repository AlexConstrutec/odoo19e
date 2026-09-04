# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    ticket_mirror_ids = fields.One2many(
        comodel_name='construtec.helpdesk.ticket.mirror', inverse_name='move_id',
        string='Tickets de Community',
        help='Tickets de Community ya vinculados a esta Factura - ver construtec.helpdesk.'
             'ticket.mirror.move_id.')
    ticket_mirror_count = fields.Integer(compute='_compute_ticket_mirror_count')
    available_ticket_mirror_ids = fields.Many2many(
        comodel_name='construtec.helpdesk.ticket.mirror',
        compute='_compute_available_ticket_mirror_ids',
        help='Auxiliar solo para el domain de `ticket_mirror_ids` en la vista - un Many2one/'
             'One2many no puede navegar un domain complejo (billing_state/is_closed) directo '
             'en un string de vista sin materializar un campo top-level primero (mismo '
             'patrón ya usado en construtec_account_payment_order_19 para `anticipos_'
             'disponibles_ids`/`available_payment_method_line_ids`). Incluye siempre los '
             'tickets YA vinculados a esta factura, aunque dejen de calificar después (ej. '
             'al postear, billing_state pasa a facturado) - si se pusiera el domain '
             'directo en el campo `ticket_mirror_ids`, un ticket ya vinculado desaparecería '
             'de la lista en cuanto cambiara de estado (mismo bug real ya documentado para '
             '`factura_ids`/`pago_ids` en ese otro módulo).')

    def _compute_ticket_mirror_count(self):
        for move in self:
            move.ticket_mirror_count = len(move.ticket_mirror_ids)

    def _compute_available_ticket_mirror_ids(self):
        Mirror = self.env['construtec.helpdesk.ticket.mirror']
        candidatos = Mirror.search([
            ('billing_state', '=', 'no_facturado'),
            ('is_closed', '=', True),
        ])
        for move in self:
            move.available_ticket_mirror_ids = candidatos | move.ticket_mirror_ids

    def action_view_ticket_mirrors(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'construtec_ticket_billing_19.construtec_helpdesk_ticket_mirror_action')
        action['domain'] = [('move_id', '=', self.id)]
        action['context'] = {}
        return action

    def _compute_ticket_analytic_distribution(self):
        """Reparte 100% proporcionalmente por CANTIDAD de Tickets vinculados por Cuenta
        Analítica - pedido explícito del usuario, con ejemplo numérico propio (15 tickets:
        7/3/4/1 entre 4 cuentas → 46.67% / 20% / 26.67% / 6.67%). Deliberadamente por CANTIDAD
        de tickets, no por `costo_total` ponderado - así lo describió el usuario, no se asumió
        lo contrario.

        Tickets sin `analytic_account_id` (todavía sin Ubicación en Community) quedan FUERA
        del reparto por completo - ni cuentan en el denominador ni reciben porcentaje; si
        NINGÚN ticket vinculado tiene Cuenta Analítica, no hay nada que repartir (`False`).

        Redondeo: a la precisión nativa `decimal.precision` "Percentage Analytic" (la misma
        que ya usa `analytic.mixin._sanitize_values()` para que el propio ORM no vuelva a
        redondear distinto al guardar) - el remanente de redondeo se asigna a la cuenta con
        más tickets (empate → mayor id), para que la suma cierre en exactamente 100.00, nunca
        99.99/100.01 por arrastre de decimales."""
        self.ensure_one()
        tickets = self.ticket_mirror_ids.filtered('analytic_account_id')
        total = len(tickets)
        if not total:
            return False
        conteo = {}
        for ticket in tickets:
            conteo[ticket.analytic_account_id] = conteo.get(ticket.analytic_account_id, 0) + 1
        precision = self.env['decimal.precision'].precision_get('Percentage Analytic')
        porcentajes = {cuenta: round(cantidad / total * 100, precision) for cuenta, cantidad in conteo.items()}
        remanente = round(100 - sum(porcentajes.values()), precision)
        if remanente:
            cuenta_mayor = max(conteo, key=lambda c: (conteo[c], c.id))
            porcentajes[cuenta_mayor] = round(porcentajes[cuenta_mayor] + remanente, precision)
        return {str(cuenta.id): pct for cuenta, pct in porcentajes.items()}

    def _apply_ticket_analytic_distribution(self):
        """Aplica el reparto de `_compute_ticket_analytic_distribution()` a las líneas de la
        Factura que TODAVÍA no tienen su propia distribución analítica - nunca pisa una que el
        contable ya fijó a mano (mismo criterio "solo rellena vacíos" usado en todo este
        proyecto, ej. `cuenta_contable_id` en construtec_account_19). Excluye líneas de
        sección/nota (`display_type`), que no tienen efecto contable real."""
        for move in self:
            if move.move_type != 'out_invoice':
                continue
            distribucion = move._compute_ticket_analytic_distribution()
            if not distribucion:
                continue
            lineas = move.invoice_line_ids.filtered(
                lambda l: l.display_type not in ('line_section', 'line_note')
                and not l.analytic_distribution
            )
            lineas.analytic_distribution = distribucion

    @api.onchange('ticket_mirror_ids', 'invoice_line_ids')
    def _onchange_ticket_mirror_ids_apply_analytic_distribution(self):
        self._apply_ticket_analytic_distribution()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        # _apply_ticket_analytic_distribution() ya es un no-op seguro (move_type != 'out_invoice',
        # o sin tickets con Cuenta Analítica) - no hace falta filtrar cuáles vals traían qué.
        records._apply_ticket_analytic_distribution()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'ticket_mirror_ids' in vals or 'invoice_line_ids' in vals:
            self._apply_ticket_analytic_distribution()
        return res
