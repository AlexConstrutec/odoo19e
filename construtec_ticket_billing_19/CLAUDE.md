# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this module is

`construtec_ticket_billing_19` is the **receiving side** of a two-way integration with `construtec_helpdesk_field_service` (Community, `Odoo19C`): Community pushes a read-only-ish mirror of each Helpdesk Ticket (number, name, `costo_total`, stage, client) via Odoo's own built-in `/jsonrpc` API whenever the ticket's cost/stage changes, and this module lets the accountant link one or several of those mirrored tickets to a real Enterprise `account.move` (customer invoice). Community then pulls back the resulting `billing_state` (Sin Facturar/Facturado/Cobrado) periodically. `depends: ['account']` only — deliberately does **not** depend on `construtec_account_payment_order_19` or `construtec_account_19`; the invoice link is a plain `Many2one` to core `account.move`, no SAT/Documentos SAT involvement needed.

Part of the "Facturación de Tickets" feature — see `construtec_helpdesk_field_service/CLAUDE.md` (Community side) for the full push/pull design and the plan that was presented to and approved by the user before building either side.

## Why a separate mirror model, not a real business object

Community and Enterprise are **separate databases** with unrelated primary keys — a `partner_id` in Community's ticket means nothing here. `construtec.helpdesk.ticket.mirror` therefore stores `number`/`name`/`stage_name`/`partner_name` as **plain text**, not `Many2one`s (same discipline as `construtec.materials.catalog.mirror`/`helpdesk.material.requisition.mirror`). The one deliberate exception is `move_id` (`Many2one account.move`) — that IS a real local relation, because the accountant links it by hand, inside this same database, to a real invoice that also lives here.

## `sync_from_community(vals)`: upsert by `number`, not create-only

Unlike `helpdesk.material.requisition.mirror` (a pure create-only audit trail), this model needs **upsert**: Community re-pushes the whole ticket (including a growing `costo_total`) every time `payment_order_ids`/`stage_id` changes, and a ticket needs to keep the SAME mirror row so `move_id` (chosen once by the accountant) never gets orphaned by a duplicate. `number` (the ticket's own number in Community, e.g. `HT00094`) is the upsert key — never an id, since ids aren't shared between the two databases. Same pattern as `construtec.materials.catalog.mirror::sync_from_enterprise()` (`construtec_sat_catalog_sync_19`, Community): search-or-create by the stable key, deliberately **without `sudo()`** — see "Security" below for what group the calling integration user needs.

## `billing_state`: always derived from the real invoice, never written by hand

`billing_state` (`no_facturado`/`facturado`/`cobrado`) is `compute='_compute_billing_state', store=True`, `@api.depends('move_id.state', 'move_id.payment_state', 'move_id.reconciled_payment_ids')` — it can **never** drift from the actual invoice, because there is nothing else that writes to it:

- `move_id` empty, or `state != 'posted'` → `no_facturado`.
- Posted, `payment_state` not in `('paid', 'in_payment')` → `facturado`.
- Posted, `payment_state in ('paid', 'in_payment')` → `cobrado`, and `payment_id` (Many2one `account.payment`, also compute+store, same method) resolves to `move_id.reconciled_payment_ids[:1]` — **MVP**: if a factura has several partial payments reconciled, only the first is exposed. Revisit if partial-payment tracking per ticket is ever needed.

`account.move.reconciled_payment_ids` (Many2many, core field, confirmed by reading `..\odoo\addons\account\models\account_move.py` before using it — do not assume a field name here without checking, this model changes across Odoo versions) already resolves the real `account.payment`(s) reconciled against the invoice via `account.move.line`/`account.partial.reconcile` internally; no manual reconciliation-chain traversal needed.

## `account.move` gets a reverse `ticket_mirror_ids` + a smart button

`models/account_move.py` (`_inherit`) adds `ticket_mirror_ids` (One2many, `move_id`) so the accountant sees, right on the invoice form, every Community ticket already linked and their running `costo_total` (a new "Tickets (Community)" notebook page, `views/account_move_views.xml`, `invisible="move_type != 'out_invoice'"` — this is customer billing, not vendor bills) — plus a stat button (`ticket_mirror_count`) in the button box. The page's field uses `widget="many2many"` on the One2many (same deliberate trick already documented in `construtec_account_payment_order_19/CLAUDE.md` for `factura_ids`/`pago_ids`) so the accountant can search/attach *existing* mirror rows instead of trying to create new ones inline (`create="0"` on the nested list — mirrors are only ever created by `sync_from_community()`).

## Security: reutiliza `account.group_account_manager`, sin grupo dedicado (2026-09-04)

**Diseño original (retirado)**: un grupo dedicado de mínimo privilegio, `group_ticket_billing_sync_integration` (`security/ticket_billing_security.xml`), create+write+read SOLO sobre `construtec.helpdesk.ticket.mirror` — nada más. El usuario explícitamente pidió lo contrario ("reutiliza los grupos, no crea grupos nuevos") tras ver que el módulo nunca se había instalado en producción — el momento correcto para el cambio, sin datos/usuarios reales todavía dependiendo del grupo viejo.

**Diseño actual**: `security/ir.model.access.csv` tiene una sola fila de escritura, sobre **`account.group_account_manager`** ("Facturación: Administrador", grupo nativo ya usado en todo este proyecto para acciones privilegiadas de contabilidad) con **read+write+create+unlink completo** — el usuario de integración se agrega a ESE grupo, no a uno nuevo. `account.group_account_invoice` conserva su fila de solo read+write (sin create/unlink) para el personal normal de contabilidad, sin cambios.

**Trade-off aceptado explícitamente, no un descuido**: esto es más amplio que el grupo dedicado anterior — cualquier humano con "Facturación: Administrador" (no solo la integración) ya tenía create/unlink aquí, y la superficie de la API Key de integración crece de "solo este modelo" a "todo lo que ese grupo alcanza en Contabilidad" si llegara a filtrarse. Confirmado con el usuario vía `AskUserQuestion` antes de implementar (eligió expresamente el nivel Administrador, no el básico de Facturación) - prioriza simplicidad de Ajustes/menos grupos que administrar sobre superficie de ataque mínima.

**Deliberadamente reutiliza la MISMA integración ya provisionada para `construtec_account_payment_order_19`** (confirmado con el usuario 2026-09-03) — sin usuario dedicado aparte para facturación de tickets. Consistente con la reutilización de credenciales ya en el lado Community (`construtec_helpdesk_field_service/tools/enterprise_sync_api.py` lee `company.payment_order_sync_url/_db/_login/_api_key` directo, los mismos 4 campos ya configurados para Órdenes de Pago). El único paso en Enterprise es **agregar `account.group_account_manager` a ese usuario ya existente** (Ajustes > Usuarios y Compañías > Usuarios > ese usuario > pestaña *Access Rights*, o directo en la ficha del usuario el campo "Facturación" = Administrador) — nunca crear un segundo usuario de integración solo para esto.

## Menu placement

`account.menu_finance_receivables` ("Customers", not "Vendors" — this is billing tickets to clients) — a standalone "Tickets (Community)" list/form, filtered to "Listos para Facturar" by default (`context: {'search_default_listos_para_facturar': 1}` — Hecho + Sin Facturar combined, see below), so the accountant opens straight into what's actually ready to invoice.

## `is_closed`: no se puede facturar un ticket que no está hecho (2026-09-04)

Requisito explícito del usuario, confirmado vía `AskUserQuestion` (eligió el filtro **duro**, no solo visual): un ticket todavía abierto en Community no debe poder vincularse a una Factura en Enterprise, aunque el contable lo busque a propósito.

- **`is_closed`** (Boolean, nuevo, este modelo) — espejo de `helpdesk.ticket.closed` (Community, `related="stage_id.closed"`) al momento del último empuje. `_prepare_ticket_sync_vals()` (Community, `construtec_helpdesk_field_service/models/helpdesk_ticket.py`) ahora manda `is_closed: self.closed` — no hizo falta ningún disparador nuevo, un cambio de etapa ya dispara `_sync_ticket_to_enterprise()` vía el `write()` existente (`'stage_id' in vals`).
- **Filtro duro en el selector de la Factura** (`account.move.ticket_mirror_ids`, `views/account_move_views.xml`): en vez de poner `domain=` directo sobre `ticket_mirror_ids` (revienta exactamente igual que el bug real ya documentado en `construtec_account_payment_order_19/CLAUDE.md` para `factura_ids`/`pago_ids` - un domain sobre un One2many se aplica también al LEER, no solo al buscar candidatos, así que un ticket ya vinculado desaparecería de la factura en cuanto cambiara de estado, ej. al postear), se usa el mismo patrón ya probado ahí (`anticipos_disponibles_ids`/`available_payment_method_line_ids`): un campo Many2many auxiliar **`available_ticket_mirror_ids`** (`account_move.py`, compute no-stored) calcula `Mirror.search([('billing_state','=','no_facturado'), ('is_closed','=',True)])` **más los ya vinculados a esta misma factura** (`| move.ticket_mirror_ids` — así uno que deja de calificar después, ej. al postear, nunca desaparece de su propia factura). La vista pone `domain="[('id', 'in', available_ticket_mirror_ids)]"` sobre `ticket_mirror_ids`, con el auxiliar oculto (`invisible="1"`) en la misma página.
- **Lista/búsqueda de "Tickets (Community)"**: nuevo filtro combinado "Listos para Facturar" (`billing_state='no_facturado' AND is_closed=True`) — es el nuevo default de la acción, reemplazando al antiguo "Sin Facturar" solo. "Sin Facturar"/"Hecho" siguen existiendo como filtros individuales, por si el contable quiere ver todo lo que llega sin importar si ya está listo. Columna `is_closed` ("Hecho") agregada a la lista y al formulario.

Verificado con `odoo-bin shell` en `construtec_test`: un ticket abierto (`is_closed=False`) y uno ya facturado (`billing_state='facturado'`, tras postear su propia factura) **no** aparecen en `available_ticket_mirror_ids` de una factura nueva; uno hecho y sin facturar sí aparece. Vinculado ese último a la factura y posteada (pasa a `billing_state='facturado'`), **sigue** apareciendo en `ticket_mirror_ids` de esa misma factura pese a ya no calificar para el domain — confirma que no se reabrió el bug de "desaparición" ya documentado en el otro módulo. `-u` limpio en `construtec_test`, sin `ERROR`/`CRITICAL` nuevos.

## `ticket_label`: evita mostrar `number`/`name` como dos columnas casi siempre idénticas (2026-09-04)

Reportado por el usuario en el selector de tickets de una Factura: "No. Ticket" y "Ticket" mostraban el mismo texto lado a lado. Causa: en Community, `helpdesk.ticket.name` se autocompleta con el propio `number` cuando el ticket nunca tuvo un título real (`create()`, `construtec_helpdesk_mgmt`) - así que en el caso normal, `number`/`name` llegan idénticos a este espejo.

**Fix**: `ticket_label` (Char, compute+store, `@api.depends('number', 'name')`) - mismo criterio exacto que `helpdesk.ticket._compute_display_name()` (Community): `number` a secas si `name` está vacío o es igual a `number`; `"{number} - {name}"` solo cuando de verdad difieren (un título real). Reemplaza las columnas separadas `number`/`name` por una sola (`ticket_label`, string "Ticket") en la lista standalone y en la lista anidada dentro de la Factura (`ticket_mirror_ids`) - `number`/`name` quedan como columnas `optional="hide"` en la lista standalone, por si hace falta buscar/ver el dato crudo. El formulario (`h1`/`h3`) también oculta el `h3` de `name` cuando coincide con `number` (`invisible="not name or name == number"`).

**Nota de UI real, no asumida**: el diálogo "Agregar" del widget `many2many` sobre `ticket_mirror_ids` (Factura → pestaña Tickets) usa la vista de LISTA STANDALONE del modelo (`construtec_helpdesk_ticket_mirror_view_list`), no la lista anidada definida dentro de `account_move_views.xml` - confirmado por captura real del usuario, que mostraba columnas (`Hecho`, `Factura`) que solo existen en la lista standalone. Por eso el fix se aplicó en AMBOS lugares para quedar consistente en toda la UI, aunque solo uno de los dos alimenta ese diálogo específico.

Verificado con `odoo-bin shell`: `number == name` → `ticket_label == number`; `number != name` (título real) → `ticket_label == "number - name"`; sin `name` → `ticket_label == number`. `-u` limpio en `construtec_test`, sin `ERROR`/`CRITICAL` nuevos.

## Bug real: `community_url` nunca llegaba a poblarse - Community no mandaba `origin_record_id`/`origin_base_url` (2026-09-04)

Reportado por el usuario: quería un link visible, justo en el momento de vincular un ticket a una Factura, para poder consultar el ticket real en Community sin salir de Enterprise. El campo `community_url` (compute, `@api.depends('origin_record_id', 'origin_base_url')`) y el grupo "Vínculo Community / Enterprise" en el formulario **ya existían** desde el diseño original de este módulo - mismo patrón exacto que `account.payment.order.community_url` (`construtec_account_payment_order_19`) - pero **nunca se veía nada** porque `origin_record_id`/`origin_base_url` se quedaban vacíos para siempre.

**Causa real**: `_prepare_ticket_sync_vals()` (`construtec_helpdesk_field_service/models/helpdesk_ticket.py`, Community) nunca mandaba esos dos campos en el payload del push - a diferencia de `account.payment.order._prepare_sync_vals()`, que sí los manda desde que se construyó ese mecanismo. Un descuido real al construir el push de tickets, no un cambio de diseño.

**El fix**: `_prepare_ticket_sync_vals()` ahora también manda `origin_record_id: self.id` y `origin_base_url: self.get_base_url()` - mismo criterio exacto que el otro módulo. `sync_from_community()` (este módulo) no necesitó ningún cambio - ya escribía cualquier clave del payload tal cual, incluidas estas dos, solo que nunca las recibía.

**Además, se agregó `community_url` (`widget="url"`) como columna visible en los dos lugares donde de verdad se "está vinculando"** (antes solo se veía dentro del formulario individual de un ticket, un lugar al que nadie entra durante el flujo real de facturación):
- La lista standalone (`construtec_helpdesk_ticket_mirror_view_list`) - es la que alimenta el diálogo "Agregar" del selector `ticket_mirror_ids` en la Factura (confirmado en la sesión anterior: ese diálogo usa esta vista, no la lista anidada del formulario de la Factura).
- La lista anidada dentro de la pestaña "Tickets (Community)" de la propia Factura (`account_move_views.xml`) - para revisar un ticket ya vinculado sin salir de ahí.

Verificado con `odoo-bin shell`: `sync_from_community()` con un payload que incluye `origin_record_id`/`origin_base_url` (simulando el push ya corregido de Community) arma correctamente `community_url = '<origin_base_url>/web#id=<origin_record_id>&model=helpdesk.ticket&view_type=form'`. `-u` limpio en ambos lados (`construtec_helpdesk_field_service` en Community, `construtec_ticket_billing_19` en Enterprise), sin `ERROR`/`CRITICAL` nuevos.

## Verified

`odoo-bin shell` against `construtec_test` (`Odoo19E`): `sync_from_community()` creates on first call, upserts (same id, updated `costo_total`) on a second call with the same `number` — never duplicates; linking `move_id` to a draft invoice keeps `billing_state='no_facturado'`; posting the invoice (unpaid) flips it to `facturado`; two different mirror tickets sharing the same `move_id` both read `facturado`/`cobrado` together and `account.move.ticket_mirror_count == 2`; registering full payment via `account.payment.register` flips both to `cobrado` with `payment_id` resolved; `action_view_ticket_mirrors()` builds the correct domain. `-u`/`-i` clean on `construtec_test`, no new `ERROR`/`CRITICAL` in `odoo.log` (only pre-existing, differently-dated noise already documented in the top-level `Odoo19E\server\odoo19e\CLAUDE.md`).

## Dual-repo deployment

Installed verbatim in both `odoo19e` and `odoo19enterprise` (same convention as `construtec_account_payment_order_19`, `construtec_materials_sync_19`, etc.) — any change here must be copied to both and committed/pushed in both.
