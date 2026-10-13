# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Renombre "Orden de Pago" -> "Requisición de Pago" (2026-10-13): al actualizar un campo traducible
desde XML, Odoo reescribe solo el valor en_US y CONSERVA el de otros idiomas. Un registro creado
cuando se instaló el módulo desde la interfaz con el idioma del usuario activo (ej. es_GT) tiene
ese valor guardado también bajo ese idioma, así que el usuario seguía viendo el nombre viejo
(ej. el título "Órdenes de Pago" de la lista) aunque en_US ya dijera "Requisiciones de Pago".
Aquí se deja solo en_US en los nombres renombrados - el módulo no trae traducciones propias
(i18n/), así que no se pierde ninguna."""
from odoo import SUPERUSER_ID, api

_TARGETS = [
    ('ir_act_window', [
        'construtec_account_payment_order_19.action_account_payment_order',
        'construtec_account_payment_order_19.action_account_payment_order_bulk_import_wizard',
        'construtec_whatsapp_19.action_construtec_whatsapp_payment_order_notification',
    ]),
    ('ir_ui_menu', [
        'construtec_account_payment_order_19.menu_account_payment_order',
        'construtec_account_payment_order_19.menu_account_payment_order_bulk_import',
    ]),
    ('res_groups', [
        'construtec_account_payment_order_19.group_payment_order_approver',
        'construtec_account_payment_order_19.group_payment_order_sync_integration',
    ]),
    ('ir_module_category', [
        'construtec_account_payment_order_19.module_construtec_payment_order_category',
    ]),
]


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for table, xmlids in _TARGETS:
        for xmlid in xmlids:
            res_id = env['ir.model.data']._xmlid_to_res_id(xmlid, raise_if_not_found=False)
            if not res_id:
                continue
            cr.execute(
                "UPDATE %s SET name = jsonb_build_object('en_US', name->>'en_US') "
                "WHERE id = %%s AND jsonb_typeof(name) = 'object' AND name ? 'en_US'" % table,
                (res_id,))
