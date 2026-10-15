# CLAUDE.md

`construtec_sat_payment_notify_enterprise_19`: **solo Enterprise** (2026-10-15). Es el lado Enterprise del aviso por
WhatsApp Alterno al proveedor cuando se registra un pago. El lado Community, que es el que manda el WhatsApp, es
`construtec_sat_payment_notify_19` en Odoo19C; ahí está el diseño completo (`CLAUDE.md` del módulo, más
`PLAN_PAGOS_PROVEEDOR_WHATSAPP.md` en la raíz de odoo19c).

`depends`:
- `account`;
- `construtec_account_19`, por `account.move.sat_document_id`.

**No toca `construtec_account_payment_order_19`**, que es compartido con Community.

## Qué hace

**Ventana "Registrar pago"** (`account.payment.register`):
- Casilla **"Avisar al proveedor por WhatsApp"**, **desmarcada por defecto** (decisión del usuario).
- Solo aparece si es un pago a proveedor (`supplier`/`outbound`) y alguna factura viene de un Documento SAT
  (`can_notify_supplier_whatsapp`).
- Se pasa al pago en `_create_payment_vals_from_wizard()` y en `_create_payment_vals_from_batch()`. Aunque alguien la
  marque, sin factura SAT no se activa.

**El pago (`account.payment`) tiene la cola**:
- `community_sync_seq` (compute store) = código del `state` × 10 + casilla. Cambia si cambia el estado o la casilla.
- `community_acked_seq`: la versión que Community confirmó.
- `community_sync_state` (compute store):
  - `pendiente` si el pago es relevante y `seq != acked`;
  - `sincronizado` si coinciden;
  - `no_aplica` si no es relevante.
  - Es relevante si es pago a proveedor y tiene la casilla marcada **o** Community ya lo había procesado (así una
    cancelación posterior vuelve a la cola).
- **¿Por qué un compute y no un flag en `write()`?** En Odoo 19 `account.payment.state` es compute: una cancelación
  desde el asiento cambia el estado sin pasar por `write()` del pago.

**`construtec_community_ack(seq, vals)`** es un método público (Community lo llama por JSON-RPC):
- Escribe solo `community_payment_url`, `whatsapp_notify_state`, `whatsapp_notify_error` y
  `whatsapp_cancel_notify_state`; cualquier otra clave se ignora.
- Guarda `community_acked_seq = seq`.
- Si el pago cambió mientras Community lo procesaba, `seq` ya no coincide y sigue `pendiente`: se vuelve a jalar y no
  se pierde un aviso de cancelación.

**Formulario del pago**: pestaña "Aviso por WhatsApp" (solo en pagos a proveedor), con:
- la casilla, editable hasta que el aviso salga;
- el estado de sincronización y el link **"Ver en Community"** (URL cruzada);
- los estados de los avisos de pago y de cancelación.

Enterprise **no llama a nadie** y no necesita credenciales hacia Community: Community jala la cola cada 20 minutos
(`fetch_pending_payments`) con las credenciales `materials_catalog_sync_*` que ya tiene. El usuario de integración de
Community necesita en Enterprise:
- lectura de `account.payment`, `account.move`, `construtec.sat.document` y `res.partner`;
- escritura de esos campos de `account.payment`.

## Gotcha de Odoo 19: `reconciled_bill_ids` de un pago sin asiento

Un pago "En proceso" puede no tener asiento (`move_id` vacío). Aun así `reconciled_bill_ids` incluye la factura,
porque el compute arranca de `invoice_ids`. Dentro de la **misma transacción** que crea el pago, el valor en caché
puede salir vacío (falso negativo en pruebas): hay que `env.invalidate_all()` antes de leerlo. Community lo lee 20
minutos después, en otra transacción, así que no le afecta.

## Verificado (2026-10-15, `construtec_test` con el Odoo de Enterprise, con rollback)

19 comprobaciones OK:
- **Factura SAT + "Registrar pago" con la casilla marcada**: el pago entra a la cola. Un `search_read` igual al de
  Community lo encuentra, con la factura y su documento SAT.
- **Confirmación (ack)**: deja el pago `sincronizado`, guarda la URL y el estado del aviso, e ignora las claves fuera
  del contrato.
- **Cancelación**: el pago vuelve a la cola. Un ack con el `seq` viejo no lo saca; con el `seq` actual sí.
- **Sin casilla** → `no_aplica`.
- **Factura sin SAT**: el asistente no ofrece la casilla, y si la marcan no se activa.
- **Casilla marcada después, en el pago** → vuelve a la cola.
- Vistas OK.

**No se probó de punta a punta contra un Community real por la red** (el contrato coincide campo por campo con
`tools/enterprise_payment_api.py` de Community).

**Instalar desde cero falla por un bug que ya existía en `construtec_account_payment_order_19`**: el manifiesto
carga `account_payment_order_bulk_import_wizard_views.xml` (que usa `menu_account_payment_order` como padre) antes de
`account_payment_order_views.xml`, que es donde se define ese menú. Por eso se probó en `construtec_test`, que ya
tiene esos módulos, y no en una base nueva.
