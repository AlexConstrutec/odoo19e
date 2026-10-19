from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.construtec_account_payment_order_19.models.account_payment_order import (
    GASTOS_STATES_EDITABLES, GASTOS_TIPOS)


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
        inverse='_inverse_sat_document_ids', readonly=False,
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
        for rec in self:
            rec.sat_document_ids = rec._get_sat_documents_vinculados()

    def _get_sat_documents_vinculados(self):
        self.ensure_one()
        if not isinstance(self.id, int):
            return self.env['construtec.sat.document']
        pendientes = self.env['construtec.sat.document'].search([
            ('payment_order_id', '=', self.id), ('state', '=', 'pendiente')])
        return self.factura_ids.sat_document_id | pendientes

    def _inverse_sat_document_ids(self):
        """Requisición de Materiales (2026-10-19): el Contador agrega en Enterprise, desde la
        pestaña "Documentos SAT", los documentos del proveedor y luego los convierte a factura
        (la factura nace ya vinculada a la requisición - ver action_convertir_a_factura()).
        Agregar reclama el documento (pendiente) o vincula su factura (ya convertido) con
        _resolve_sat_document_ids(), cuyos candados ya bloquean un documento tomado por otra
        requisición viva o una factura pagada. Quitar libera ese vínculo. En los demás tipos el
        campo es de solo lectura en la vista y esto no hace nada."""
        for rec in self.filtered(lambda r: r.tipo == 'anticipo_materiales'):
            actuales = rec._get_sat_documents_vinculados()
            agregados = rec.sat_document_ids - actuales
            quitados = actuales - rec.sat_document_ids
            if agregados:
                rec._resolve_sat_document_ids(agregados.ids)
            for documento in quitados:
                if documento.state == 'pendiente' and documento.payment_order_id == rec:
                    documento.payment_order_id = False
                elif documento.move_id.payment_order_id == rec:
                    documento.move_id.payment_order_id = False
            if agregados or quitados:
                rec.message_post(body=self.env._(
                    'Documentos SAT agregados: %(add)s. Quitados: %(rem)s.',
                    add=', '.join(agregados.mapped('numero_autorizacion')) or '-',
                    rem=', '.join(quitados.mapped('numero_autorizacion')) or '-'))

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
        (sat_document.py) ya existe, ya está verificado, y crea el account.move ya vinculado a
        esta Orden (payment_order_id) - hereda el vínculo directo desde
        documento.payment_order_id (el candado que dejó _resolve_sat_document_ids() al reclamar
        el documento mientras seguía pendiente), sin que este método necesite repetir ningún
        write() aparte."""
        res = super().action_approve()
        for rec in self.filtered(lambda r: r.tipo == 'pago_directo'):
            pendientes = self.env['construtec.sat.document'].search([
                ('payment_order_id', '=', rec.id), ('state', '=', 'pendiente')])
            for documento in pendientes:
                documento.action_convertir_a_factura()
        return res

    @api.model
    def sync_gasto_documents_from_community(self, external_ref, sat_document_ids):
        """Método whitelisted, llamado vía JSON-RPC desde Community (ver
        `link_gasto_documents_in_enterprise()` en `tools/enterprise_sync_api.py`): el técnico
        vincula, DESPUÉS de enviar su Requisición de Viáticos, las facturas con las que gastó el
        anticipo (2026-10-17) - hacen falta para liquidarlo.

        La Requisición se localiza por `external_ref` (el `name` de su copia en Community, nunca un
        id) y debe seguir en Enviada/Aprobada/Aplicada. Cada Documento SAT se resuelve según su
        estado REAL ahora (`_resolve_sat_document_ids()`): ya convertido a factura se vincula su
        `move_id`; pendiente se reclama. Los candados reales (factura pagada, o ya tomada por otra
        requisición viva) los valida `account.move.write()`/`construtec.sat.document.write()`; si
        alguno falla, la excepción llega tal cual a Community y no se vincula NADA (una sola
        transacción).

        A diferencia de Pago Directo, un documento pendiente NO se convierte a factura aquí ni al
        Aprobar: convertirlo exige Cuenta Contable en cada línea y bloquearía la aprobación del
        anticipo. El Contador lo convierte desde el Documento SAT cuando le corresponda (la factura
        nace ya vinculada a esta requisición) y luego Liquida.

        `sudo()`: el usuario de integración solo puede crear Órdenes (ver security)."""
        order = self.sudo().search(
            [('external_ref', '=', external_ref), ('origin', '=', 'synced')], limit=1)
        if not order:
            raise UserError(self.env._(
                'No se encontró en Enterprise la requisición %s.', external_ref))
        if order.tipo not in GASTOS_TIPOS:
            raise UserError(self.env._(
                'La requisición %s no es de Viáticos: no lleva facturas de gastos.', order.name))
        if order.state not in GASTOS_STATES_EDITABLES:
            raise UserError(self.env._(
                'La requisición %(name)s ya no admite facturas de gastos (estado: %(state)s).',
                name=order.name, state=dict(order._fields['state'].selection)[order.state]))
        documentos = order.env['construtec.sat.document'].browse(sat_document_ids or []).exists()
        if not documentos:
            raise UserError(self.env._('No se recibió ninguna factura que vincular.'))
        order._resolve_sat_document_ids(documentos.ids)
        order.message_post(body=self.env._(
            'El técnico vinculó %(n)s factura(s) de gastos desde Community: %(docs)s.',
            n=len(documentos),
            docs=', '.join('%s (%s)' % (d.numero_autorizacion, d.partner_id.name or '-')
                           for d in documentos)))
        return True
