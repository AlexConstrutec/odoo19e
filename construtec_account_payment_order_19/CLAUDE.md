

## Prioridad de la requisición (estrellas) y etiqueta al Gerente Financiero (2026-10-29)

Pedido del usuario: un campo de prioridad con el widget de estrellas de los tickets, y que una requisición de prioridad más alta
etiquete al puesto de Gerente Financiero en el grupo de notificación.

- `prioridad` (Selection `0` Baja / `1` Media / `2` Alta / `3` Muy Alta, default `1`, widget `priority`): en el formulario junto a la
  fecha, columna de la lista, filtro "Prioridad Muy Alta" y agrupar por Prioridad. Se edita libremente en Borrador; después de enviar,
  solo en Enterprise (`es_procesador`).
- Viaja a Enterprise al enviar (`_prepare_sync_vals()`), y un cambio hecho allá regresa a Community con el pull de estado
  (`_pull_payment_order_status()` la pide y compara). Un cambio hecho en Community después de enviar no viaja (por eso es de solo lectura).
- La etiqueta en WhatsApp vive en `construtec_whatsapp_alterno_notify_19` (ver su CLAUDE.md). Versión 19.0.1.27.0.
- Verificado en `construtec_test` (Community 12 comprobaciones). **No verificado en el navegador.**
