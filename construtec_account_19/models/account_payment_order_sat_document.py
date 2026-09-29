from odoo import models


class AccountPaymentOrder(models.Model):
    """Extensión Enterprise-only de account.payment.order (construtec_account_payment_order_19)
    - vive AQUÍ, no en el archivo compartido de ese módulo, porque necesita conocer
    construtec.sat.document, un modelo que solo existe en esta edición. El archivo compartido
    nunca importa/referencia ese modelo directamente (ver create()/_resolve_sat_document_
    pendiente_ids más abajo, invocado solo via hasattr) - así Community puede seguir cargando
    ese mismo archivo sin este modelo instalado."""
    _inherit = 'account.payment.order'

    def _resolve_sat_document_pendiente_ids(self, sat_document_ids):
        """Reclama, para esta Orden (tipo pago_directo, recién creada/recibida por
        sincronización desde Community), los Documentos SAT todavía Pendientes que el jefe de
        técnicos eligió en el mirror - `sat_document_ids` son ids reales de
        construtec.sat.document en esta base (Community los tomó de
        construtec.sat.invoice.mirror.origin_id, que para un documento pendiente ES el id real
        del propio Documento SAT aquí).

        La validación real (¿ya lo reclamó otra Solicitud viva?) vive en
        construtec.sat.document.write() (_check_payment_order_disponible_pendiente()) - se
        dispara automáticamente al escribir payment_order_id, sin repetir el chequeo aquí."""
        self.ensure_one()
        documentos = self.env['construtec.sat.document'].browse(sat_document_ids).exists()
        documentos.write({'payment_order_id': self.id})

    def action_approve(self):
        """Al Aprobar una Solicitud de Pago Directo, el Contador convierte a factura real
        cualquier Documento SAT todavía pendiente que esta Orden haya reclamado (ver
        _resolve_sat_document_pendiente_ids()) - decisión explícita del usuario ("El Contador
        la convierte al Aprobar"), nunca automático al sincronizar. action_convertir_a_factura()
        (sat_document.py) ya existe, ya está verificado, y crea el account.move en borrador -
        aquí solo se enlaza ese move resultante a la Orden, pasando por el candado normal de
        account_move.py (_check_payment_order_disponible()) como defensa adicional, aunque ya
        debería estar libre por construcción (nadie más pudo reclamar el Documento SAT
        mientras seguía pendiente)."""
        res = super().action_approve()
        for rec in self.filtered(lambda r: r.tipo == 'pago_directo'):
            pendientes = self.env['construtec.sat.document'].search([
                ('payment_order_id', '=', rec.id), ('state', '=', 'pendiente')])
            for documento in pendientes:
                documento.action_convertir_a_factura()
                documento.move_id.write({'payment_order_id': rec.id})
        return res
