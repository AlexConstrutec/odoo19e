from odoo import api, fields, models


class AccountPaymentOrder(models.Model):
    """Extensión Enterprise-only de account.payment.order (construtec_account_payment_order_19)
    - vive AQUÍ, no en el archivo compartido de ese módulo, porque necesita conocer
    construtec.sat.document, un modelo que solo existe en esta edición. El archivo compartido
    nunca importa/referencia ese modelo directamente (ver create()/_resolve_sat_document_ids más
    abajo, invocado solo via hasattr) - así Community puede seguir cargando ese mismo archivo sin
    este modelo instalado, y nunca necesita conocer ningún id de account.move tampoco (decisión
    explícita del usuario, 2026-09-29: "de Enterprise a Community solo deben copiarse los
    documentos SAT")."""
    _inherit = 'account.payment.order'

    sat_document_ids = fields.Many2many(
        'construtec.sat.document', compute='_compute_sat_document_ids',
        string='Documentos SAT Incluidos',
        help='Todos los Documentos SAT que el jefe de técnicos eligió para esta Solicitud en '
             'Community (Pago Directo) - tanto los que ya son factura real (resueltos vía '
             'factura_ids.sat_document_id) como los que siguen Pendientes de conversión '
             '(reclamados vía construtec.sat.document.payment_order_id mientras no exista '
             'move_id todavía). Puramente informativo - el candado real de cada uno vive donde '
             'corresponda según su estado, ver _resolve_sat_document_ids().')

    @api.depends('factura_ids.sat_document_id')
    def _compute_sat_document_ids(self):
        """No-stored, recalculado en cada lectura (mismo criterio ya usado en este módulo para
        `diferencia_conciliacion`/`viaticos_sin_liquidar_count`) - un Documento SAT todavía
        Pendiente no dispara ningún `@api.depends` hacia esta Orden (su `payment_order_id` es
        un campo de OTRO modelo, escrito por `_resolve_sat_document_ids()`/`action_approve()`),
        así que se busca en vivo en vez de depender de un tracking exacto."""
        Document = self.env['construtec.sat.document']
        for rec in self:
            pendientes = Document.search([
                ('payment_order_id', '=', rec.id), ('state', '=', 'pendiente')])
            rec.sat_document_ids = rec.factura_ids.sat_document_id | pendientes

    def _resolve_sat_document_ids(self, sat_document_ids):
        """Vincula esta Orden (tipo pago_directo, recién creada/recibida por sincronización
        desde Community) a los Documentos SAT reales que el jefe de técnicos eligió en el
        mirror - `sat_document_ids` son ids reales de `construtec.sat.document` en esta base
        (Community los tomó de `construtec.sat.invoice.mirror.origin_id`, que ES el id real del
        Documento SAT aquí, sin importar su estado - Community nunca sabe ni necesita saber si ya
        es factura o no).

        Cada documento se resuelve según su estado REAL en este momento (nunca el que tenía
        cuando Community lo sincronizó por última vez - puede haber cambiado desde entonces):
        - `convertido_factura`: ya tiene un `move_id` real - se vincula directo
          (`account.move.write()`, que ya valida con `_check_payment_order_disponible()` -
          mismo candado que usa el widget many2many normal de `factura_ids` en Enterprise).
        - `pendiente`: se reclama (`payment_order_id`) - la validación real (¿ya lo reclamó otra
          Solicitud viva?) vive en `construtec.sat.document.write()`
          (`_check_payment_order_disponible_pendiente()`), disparada automáticamente. El
          Contador lo convierte a factura real al Aprobar (ver `action_approve()` abajo).

        Si cualquier documento falla, la excepción se propaga tal cual - todo el `create()` se
        revierte (una sola transacción), y del lado Community el fallo llega como cualquier otro
        error de sincronización (`sync_state='error'`, ver `_sync_to_enterprise()`)."""
        self.ensure_one()
        documentos = self.env['construtec.sat.document'].browse(sat_document_ids).exists()
        convertidos = documentos.filtered(lambda d: d.state == 'convertido_factura')
        pendientes = documentos.filtered(lambda d: d.state == 'pendiente')
        if convertidos:
            convertidos.move_id.write({'payment_order_id': self.id})
        if pendientes:
            pendientes.write({'payment_order_id': self.id})

    def action_approve(self):
        """Al Aprobar una Solicitud de Pago Directo, el Contador convierte a factura real
        cualquier Documento SAT todavía pendiente que esta Orden haya reclamado (ver
        _resolve_sat_document_ids()) - decisión explícita del usuario ("El Contador la convierte
        al Aprobar"), nunca automático al sincronizar. action_convertir_a_factura()
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
