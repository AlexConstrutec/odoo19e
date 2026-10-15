from odoo import api, fields, models

NOTIFY_STATES = [
    ('no_aplica', 'No aplica'),
    ('pendiente', 'Pendiente'),
    ('enviado', 'Enviado'),
    ('error', 'Error'),
    ('sin_telefono', 'Sin teléfono'),
]

# Codifica (estado, casilla) en un número: si cambia cualquiera de los dos, el pago vuelve a la
# cola. `state` es compute en Odoo 19 (una cancelación desde el asiento no pasa por write()), por
# eso la cola es un compute guardado y no un flag que se encienda al escribir.
STATE_CODES = {'draft': 1, 'in_process': 2, 'paid': 3, 'canceled': 4, 'rejected': 5}

# Lo único que Community puede escribir con construtec_community_ack().
ACK_FIELDS = (
    'community_payment_url', 'whatsapp_notify_state', 'whatsapp_notify_error',
    'whatsapp_cancel_notify_state',
)


class AccountPayment(models.Model):
    """Lado Enterprise del aviso por WhatsApp Alterno al proveedor. Enterprise no llama a nadie:
    deja el pago en cola (`community_sync_state='pendiente'`) y Community lo jala cada 20 min,
    manda el WhatsApp y confirma con `construtec_community_ack()`. Contrato completo en el
    CLAUDE.md de este módulo y en el de construtec_sat_payment_notify_19 (Community)."""

    _inherit = 'account.payment'

    notify_supplier_whatsapp = fields.Boolean(
        string='Avisar al proveedor por WhatsApp', copy=False, tracking=True,
        help='Community le manda al proveedor un WhatsApp (WhatsApp Alterno) avisando de este pago, '
             'y otro si después se cancela. Solo aplica a pagos de facturas que vienen de un '
             'Documento SAT. El aviso sale en la siguiente sincronización de Community (≤ 20 min).')
    has_sat_invoice = fields.Boolean(
        string='Paga facturas SAT', compute='_compute_has_sat_invoice')
    community_sync_seq = fields.Integer(
        string='Versión para Community', compute='_compute_community_sync_seq', store=True,
        copy=False)
    community_acked_seq = fields.Integer(
        string='Versión confirmada por Community', readonly=True, copy=False)
    community_sync_state = fields.Selection([
        ('no_aplica', 'No aplica'),
        ('pendiente', 'Pendiente'),
        ('sincronizado', 'Sincronizado'),
    ], string='Sincronización con Community', compute='_compute_community_sync_state', store=True,
        index=True, copy=False,
        help='Cola: "Pendiente" mientras Community no haya procesado la versión actual del pago '
             '(estado + casilla). Community la jala cada 20 minutos.')
    community_payment_url = fields.Char(
        string='Ver en Community', readonly=True, copy=False)
    whatsapp_notify_state = fields.Selection(
        NOTIFY_STATES, string='Aviso de Pago', readonly=True, copy=False)
    whatsapp_notify_error = fields.Text(string='Detalle del Aviso', readonly=True, copy=False)
    whatsapp_cancel_notify_state = fields.Selection(
        NOTIFY_STATES, string='Aviso de Cancelación', readonly=True, copy=False)

    @api.depends('reconciled_bill_ids.sat_document_id')
    def _compute_has_sat_invoice(self):
        for pay in self:
            pay.has_sat_invoice = bool(pay.reconciled_bill_ids.sat_document_id)

    @api.depends('state', 'notify_supplier_whatsapp')
    def _compute_community_sync_seq(self):
        for pay in self:
            pay.community_sync_seq = (
                STATE_CODES.get(pay.state, 0) * 10 + (1 if pay.notify_supplier_whatsapp else 0))

    @api.depends('partner_type', 'payment_type', 'notify_supplier_whatsapp',
                 'community_sync_seq', 'community_acked_seq')
    def _compute_community_sync_state(self):
        for pay in self:
            relevante = pay.partner_type == 'supplier' and pay.payment_type == 'outbound' and (
                pay.notify_supplier_whatsapp or pay.community_acked_seq)
            if not relevante:
                pay.community_sync_state = 'no_aplica'
            elif pay.community_acked_seq == pay.community_sync_seq:
                pay.community_sync_state = 'sincronizado'
            else:
                pay.community_sync_state = 'pendiente'

    def construtec_community_ack(self, seq, vals):
        """Llamado por Community (JSON-RPC) tras procesar el pago. Guarda la URL del espejo y el
        estado de los avisos, y marca como confirmada la versión `seq`. Si el pago cambió mientras
        Community lo procesaba, `seq` ya no coincide y el pago sigue pendiente (se vuelve a jalar),
        así no se pierde un aviso de cancelación."""
        clean = {key: vals[key] for key in ACK_FIELDS if key in vals}
        clean['community_acked_seq'] = seq
        self.write(clean)
        return True
