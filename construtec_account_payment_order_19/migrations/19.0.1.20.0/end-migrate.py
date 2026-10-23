"""Unificación de los Documentos SAT (2026-10-23), segunda parte.

`post-migrate.py` ya pasó los documentos y los vínculos a la réplica `construtec.sat.document`.
Al actualizar (a diferencia de desinstalar) Odoo quita el modelo viejo pero deja su tabla en la base
de datos; aquí se borran esa tabla y las tres tablas de vínculos viejas para que los Documentos SAT
queden guardados una sola vez. En Enterprise esas tablas nunca se llenaron; se borran igual."""
import logging

_logger = logging.getLogger(__name__)

TABLAS_VIEJAS = (
    'account_payment_order_construtec_sat_invoice_mirror_rel',
    'account_payment_order_gasto_mirror_rel',
    'account_payment_order_gasto_pendiente_rel',
    'construtec_sat_invoice_mirror',
)


def migrate(cr, version):
    if not version:
        return
    for tabla in TABLAS_VIEJAS:
        cr.execute(f'DROP TABLE IF EXISTS "{tabla}" CASCADE')
    _logger.info('Unificación de Documentos SAT: tablas viejas eliminadas (%s).',
                 ', '.join(TABLAS_VIEJAS))
