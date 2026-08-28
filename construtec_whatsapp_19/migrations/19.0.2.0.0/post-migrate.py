# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Migra la configuración vieja de un solo par plantilla/grupo para el evento 'Enviado'
(`res_company.payment_order_whatsapp_template_id`/`_recipient_group_id`, ambos campos ya
eliminados del modelo en esta misma versión) hacia el nuevo modelo
`construtec.whatsapp.payment.order.notification` (una fila por evento). Lee las columnas viejas
por SQL directo porque para cuando corre un post-migrate, el ORM ya solo conoce los campos
NUEVOS - las columnas viejas siguen físicamente en la tabla (Odoo no las borra solo), pero ya
no hay un campo Python que las lea."""


def migrate(cr, version):
    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'res_company'
          AND column_name IN ('payment_order_whatsapp_template_id',
                               'payment_order_whatsapp_recipient_group_id')
    """)
    columnas = {row[0] for row in cr.fetchall()}
    if not {'payment_order_whatsapp_template_id',
            'payment_order_whatsapp_recipient_group_id'} <= columnas:
        return  # instalación nueva, sin datos que migrar

    cr.execute("""
        SELECT id, payment_order_whatsapp_template_id, payment_order_whatsapp_recipient_group_id
        FROM res_company
        WHERE payment_order_whatsapp_enabled IS TRUE
          AND payment_order_whatsapp_template_id IS NOT NULL
    """)
    filas = cr.fetchall()
    if not filas:
        return

    cr.execute("SELECT id FROM res_users WHERE login = 'admin' LIMIT 1")
    admin = cr.fetchone()
    uid = admin[0] if admin else 1

    for _company_id, template_id, recipient_group_id in filas:
        cr.execute("""
            INSERT INTO construtec_whatsapp_payment_order_notification
                (state, template_id, recipient_group_id, notify_interesado, active,
                 create_uid, create_date, write_uid, write_date)
            VALUES ('enviado', %s, %s, false, true, %s, now(), %s, now())
        """, (template_id, recipient_group_id, uid, uid))
