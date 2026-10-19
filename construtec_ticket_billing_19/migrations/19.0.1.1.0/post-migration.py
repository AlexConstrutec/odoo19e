def migrate(cr, version):
    # Tres costos por ticket: lo que ya estaba guardado en `costo_total` eran solo las Requisiciones de
    # Pago (el plan no existia), asi que el total general de esos Tickets es ese mismo valor hasta que
    # Community reenvie el Ticket con los tres costos.
    cr.execute("""
        UPDATE construtec_helpdesk_ticket_mirror
           SET costo_general = COALESCE(costo_total, 0)
         WHERE costo_general IS NULL
    """)
