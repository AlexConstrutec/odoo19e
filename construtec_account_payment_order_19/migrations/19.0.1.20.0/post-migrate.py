"""Unificación de los Documentos SAT (2026-10-23).

Antes Community guardaba los Documentos SAT dos veces: en `construtec.sat.invoice.mirror` (lo que
usaban los selectores de las requisiciones) y en la réplica `construtec.sat.document`. Ahora solo
queda la réplica. Este script:
1. crea en la réplica los documentos que solo existían en la copia vieja (con lo que esa copia
   sabía; `enterprise_write_date` queda vacío para que la próxima sincronización los complete);
2. copia los vínculos de las requisiciones (Pago Directo, Facturas de Gastos y pendientes de
   enviar) a las tablas nuevas, traduciendo cada documento por su `origin_id`.

Corre antes de que Odoo borre el modelo viejo (eso pasa al final de la actualización), así que la
tabla vieja todavía existe. En Enterprise no hace nada: ahí `construtec.sat.document` es el modelo
real (sin `origin_id`) y la copia vieja nunca se llenó."""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

RELACIONES = [
    # (tabla vieja, columna requisición, columna documento, tabla nueva)
    ('account_payment_order_construtec_sat_invoice_mirror_rel', 'account_payment_order_id',
     'construtec_sat_invoice_mirror_id', 'account_payment_order_factura_sat_rel'),
    ('account_payment_order_gasto_mirror_rel', 'order_id', 'mirror_id',
     'account_payment_order_gasto_sat_rel'),
    ('account_payment_order_gasto_pendiente_rel', 'order_id', 'mirror_id',
     'account_payment_order_gasto_pendiente_sat_rel'),
]


def _tabla(cr, nombre):
    cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = %s", (nombre,))
    return bool(cr.fetchone())


def _columna(cr, tabla, columna):
    cr.execute("SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
               (tabla, columna))
    return bool(cr.fetchone())


def migrate(cr, version):
    if not version:
        return
    if not _tabla(cr, 'construtec_sat_invoice_mirror') or \
            not _columna(cr, 'construtec_sat_document', 'origin_id'):
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    Document = env['construtec.sat.document'].with_context(active_test=False)

    cr.execute("""
        SELECT m.origin_id, m.state, m.numero_autorizacion, m.numero_documento, m.serie,
               m.partner_name, m.partner_vat, m.fecha, m.currency_name, m.monto_total,
               m.amount_residual, m.payment_state, m.linked_order_name, m.company_id
          FROM construtec_sat_invoice_mirror m
         WHERE NOT EXISTS (SELECT 1 FROM construtec_sat_document d WHERE d.origin_id = m.origin_id)
    """)
    filas = cr.dictfetchall()
    company_id = env.company.id
    vals_list = [{
        'origin_id': f['origin_id'],
        'direction': 'recibida',  # provisional: la próxima sincronización trae el valor real
        'tipo_dte': 'FACT',       # provisional, ídem
        'state': f['state'],
        'numero_autorizacion': f['numero_autorizacion'] or str(f['origin_id']),
        'numero_documento': f['numero_documento'],
        'serie': f['serie'],
        'partner_name': f['partner_name'],
        'nit_contacto': f['partner_vat'],
        'fecha_certificacion': f['fecha'] or '2000-01-01',
        'currency_name': f['currency_name'],
        'monto_total': f['monto_total'],
        'move_amount_residual': f['amount_residual'],
        'move_payment_state': f['payment_state'],
        'linked_order_name': f['linked_order_name'],
        'disponible_pago': f['payment_state'] != 'paid',
        'company_id': f['company_id'] or company_id,
    } for f in filas]
    if vals_list:
        Document.create(vals_list)

    # Los que ya existían en la réplica toman de la copia vieja lo que la réplica no tenía.
    cr.execute("""
        UPDATE construtec_sat_document d
           SET linked_order_name = m.linked_order_name,
               disponible_pago = (COALESCE(m.payment_state, '') != 'paid')
          FROM construtec_sat_invoice_mirror m
         WHERE d.origin_id = m.origin_id
    """)

    copiados = 0
    for vieja, col_orden, col_doc, nueva in RELACIONES:
        if not _tabla(cr, vieja) or not _tabla(cr, nueva):
            continue
        cr.execute(f"""
            INSERT INTO {nueva} (order_id, sat_document_id)
            SELECT r.{col_orden}, d.id
              FROM {vieja} r
              JOIN construtec_sat_invoice_mirror m ON m.id = r.{col_doc}
              JOIN construtec_sat_document d ON d.origin_id = m.origin_id
            ON CONFLICT DO NOTHING
        """)
        copiados += cr.rowcount
    _logger.info('Unificación de Documentos SAT: %s documentos creados en la réplica, %s vínculos '
                 'de requisiciones copiados.', len(vals_list), copiados)
