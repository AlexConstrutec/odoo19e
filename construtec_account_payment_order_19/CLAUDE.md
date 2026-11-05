

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

## Diario con tarjeta de crédito y pregunta al Aplicar (2026-11-05)

Pedido del usuario (Enterprise): el diario de la requisición debe aceptar diarios de tipo **Tarjeta de crédito** además de Banco, y
mostrar solo los diarios de la compañía de la requisición; y al presionar **Aplicar**, preguntar si Odoo debe generar el pago.

- `journal_id` (vista): en Anticipo Viáticos / Materiales el dominio pasó de `type = bank` a `type in (bank, credit)`; para los demás
  tipos sigue sin restricción de tipo. En todos los casos se filtra por `company_id` de la requisición (la compañía actual del usuario
  al crearla) y se quitó "Crear" del desplegable.
- `action_aplicar()` ahora valida lo básico y abre el asistente `account.payment.order.aplicar.wizard` (Sí / No / Cancelar). La lógica
  de siempre vive en `_aplicar(crear_pago)`: **Sí** = igual que antes (valida diario, beneficiario, cuenta de anticipos; crea el pago,
  en borrador para Materiales y confirmado para los demás); **No** = solo pasa a Aplicado, deja nota en el chatter y no pide
  diario/beneficiario/cuenta. El pago se registra después con "Crear Pago" o agregándolo en Pagos.
- Versión 19.0.1.28.0. Verificado en `construtec_bankrec_test` (clon de Enterprise, shell + rollback): tarjeta de crédito + Sí crea 1
  pago (en proceso) con el diario de tarjeta; banco + No aplica sin pagos. **No verificado en el navegador.**
