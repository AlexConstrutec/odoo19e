# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this module is

`construtec_ticket_billing_19` is the **receiving side** of a two-way integration with `construtec_helpdesk_field_service` (Community, `Odoo19C`): Community pushes a read-only-ish mirror of each Helpdesk Ticket (number, name, `costo_total`, stage, client) via Odoo's own built-in `/jsonrpc` API whenever the ticket's cost/stage changes, and this module lets the accountant link one or several of those mirrored tickets to a real Enterprise `account.move` (customer invoice). Community then pulls back the resulting `billing_state` (Sin Facturar/Facturado/Cobrado) periodically. `depends: ['account']` only — deliberately does **not** depend on `construtec_account_payment_order_19` or `construtec_account_19`; the invoice link is a plain `Many2one` to core `account.move`, no SAT/Documentos SAT involvement needed.

Part of the "Facturación de Tickets" feature — see `construtec_helpdesk_field_service/CLAUDE.md` (Community side) for the full push/pull design and the plan that was presented to and approved by the user before building either side.

## Why a separate mirror model, not a real business object

Community and Enterprise are **separate databases** with unrelated primary keys — a `partner_id` in Community's ticket means nothing here. `construtec.helpdesk.ticket.mirror` therefore stores `number`/`name`/`stage_name`/`partner_name` as **plain text**, not `Many2one`s (same discipline as `construtec.materials.catalog.mirror`/`helpdesk.material.requisition.mirror`). The one deliberate exception is `move_id` (`Many2one account.move`) — that IS a real local relation, because the accountant links it by hand, inside this same database, to a real invoice that also lives here.

## `sync_from_community(vals)`: upsert by `number`, not create-only

Unlike `helpdesk.material.requisition.mirror` (a pure create-only audit trail), this model needs **upsert**: Community re-pushes the whole ticket (including a growing `costo_total`) every time `payment_order_ids`/`stage_id` changes, and a ticket needs to keep the SAME mirror row so `move_id` (chosen once by the accountant) never gets orphaned by a duplicate. `number` (the ticket's own number in Community, e.g. `HT00094`) is the upsert key — never an id, since ids aren't shared between the two databases. Same pattern as `construtec.materials.catalog.mirror::sync_from_enterprise()` (`construtec_sat_catalog_sync_19`, Community): search-or-create by the stable key, deliberately **without `sudo()`** — security relies entirely on the calling integration user (`group_ticket_billing_sync_integration`) being scoped to nothing else.

## `billing_state`: always derived from the real invoice, never written by hand

`billing_state` (`no_facturado`/`facturado`/`cobrado`) is `compute='_compute_billing_state', store=True`, `@api.depends('move_id.state', 'move_id.payment_state', 'move_id.reconciled_payment_ids')` — it can **never** drift from the actual invoice, because there is nothing else that writes to it:

- `move_id` empty, or `state != 'posted'` → `no_facturado`.
- Posted, `payment_state` not in `('paid', 'in_payment')` → `facturado`.
- Posted, `payment_state in ('paid', 'in_payment')` → `cobrado`, and `payment_id` (Many2one `account.payment`, also compute+store, same method) resolves to `move_id.reconciled_payment_ids[:1]` — **MVP**: if a factura has several partial payments reconciled, only the first is exposed. Revisit if partial-payment tracking per ticket is ever needed.

`account.move.reconciled_payment_ids` (Many2many, core field, confirmed by reading `..\odoo\addons\account\models\account_move.py` before using it — do not assume a field name here without checking, this model changes across Odoo versions) already resolves the real `account.payment`(s) reconciled against the invoice via `account.move.line`/`account.partial.reconcile` internally; no manual reconciliation-chain traversal needed.

## `account.move` gets a reverse `ticket_mirror_ids` + a smart button

`models/account_move.py` (`_inherit`) adds `ticket_mirror_ids` (One2many, `move_id`) so the accountant sees, right on the invoice form, every Community ticket already linked and their running `costo_total` (a new "Tickets (Community)" notebook page, `views/account_move_views.xml`, `invisible="move_type != 'out_invoice'"` — this is customer billing, not vendor bills) — plus a stat button (`ticket_mirror_count`) in the button box. The page's field uses `widget="many2many"` on the One2many (same deliberate trick already documented in `construtec_account_payment_order_19/CLAUDE.md` for `factura_ids`/`pago_ids`) so the accountant can search/attach *existing* mirror rows instead of trying to create new ones inline (`create="0"` on the nested list — mirrors are only ever created by `sync_from_community()`).

## Security: the integration user needs read+write, not create-only

Unlike `helpdesk.material.requisition.mirror`'s deliberately create-only integration group, `group_ticket_billing_sync_integration` (`security/ticket_billing_security.xml`) grants **read+write+create** (no unlink) on `construtec.helpdesk.ticket.mirror` only — `sync_from_community()`'s upsert needs to `search()` (read) and `write()` an existing row, not just insert blindly. Still nothing beyond this one model — no access to `account.move`/`account.payment` or anything else. `account.group_account_invoice`/`account.group_account_manager` get normal read+write (no create/unlink — rows are only ever created by the sync) for regular accounting staff.

**Deliberately reuses the SAME integration user already provisioned for `construtec_account_payment_order_19`** (confirmed with the user 2026-09-03) — no separate dedicated user for ticket billing. This is consistent with the credential reuse already baked into the Community side (`construtec_helpdesk_field_service/tools/enterprise_sync_api.py` reads `company.payment_order_sync_url/_db/_login/_api_key` directly, the exact same 4 fields already configured for Órdenes de Pago — no new Ajustes screen, no new API Key). The only step needed on the Enterprise side is **adding `group_ticket_billing_sync_integration` to that already-existing user** (Ajustes > Usuarios y Compañías > Usuarios > ese usuario > pestaña *Access Rights* > marcar el grupo nuevo, además de los que ya tiene) — nunca crear un segundo usuario de integración solo para esto.

## Menu placement

`account.menu_finance_receivables` ("Customers", not "Vendors" — this is billing tickets to clients) — a standalone "Tickets (Community)" list/form, filtered to "Listos para Facturar" by default (`context: {'search_default_listos_para_facturar': 1}` — Hecho + Sin Facturar combined, see below), so the accountant opens straight into what's actually ready to invoice.

## `is_closed`: no se puede facturar un ticket que no está hecho (2026-09-04)

Requisito explícito del usuario, confirmado vía `AskUserQuestion` (eligió el filtro **duro**, no solo visual): un ticket todavía abierto en Community no debe poder vincularse a una Factura en Enterprise, aunque el contable lo busque a propósito.

- **`is_closed`** (Boolean, nuevo, este modelo) — espejo de `helpdesk.ticket.closed` (Community, `related="stage_id.closed"`) al momento del último empuje. `_prepare_ticket_sync_vals()` (Community, `construtec_helpdesk_field_service/models/helpdesk_ticket.py`) ahora manda `is_closed: self.closed` — no hizo falta ningún disparador nuevo, un cambio de etapa ya dispara `_sync_ticket_to_enterprise()` vía el `write()` existente (`'stage_id' in vals`).
- **Filtro duro en el selector de la Factura** (`account.move.ticket_mirror_ids`, `views/account_move_views.xml`): en vez de poner `domain=` directo sobre `ticket_mirror_ids` (revienta exactamente igual que el bug real ya documentado en `construtec_account_payment_order_19/CLAUDE.md` para `factura_ids`/`pago_ids` - un domain sobre un One2many se aplica también al LEER, no solo al buscar candidatos, así que un ticket ya vinculado desaparecería de la factura en cuanto cambiara de estado, ej. al postear), se usa el mismo patrón ya probado ahí (`anticipos_disponibles_ids`/`available_payment_method_line_ids`): un campo Many2many auxiliar **`available_ticket_mirror_ids`** (`account_move.py`, compute no-stored) calcula `Mirror.search([('billing_state','=','no_facturado'), ('is_closed','=',True)])` **más los ya vinculados a esta misma factura** (`| move.ticket_mirror_ids` — así uno que deja de calificar después, ej. al postear, nunca desaparece de su propia factura). La vista pone `domain="[('id', 'in', available_ticket_mirror_ids)]"` sobre `ticket_mirror_ids`, con el auxiliar oculto (`invisible="1"`) en la misma página.
- **Lista/búsqueda de "Tickets (Community)"**: nuevo filtro combinado "Listos para Facturar" (`billing_state='no_facturado' AND is_closed=True`) — es el nuevo default de la acción, reemplazando al antiguo "Sin Facturar" solo. "Sin Facturar"/"Hecho" siguen existiendo como filtros individuales, por si el contable quiere ver todo lo que llega sin importar si ya está listo. Columna `is_closed` ("Hecho") agregada a la lista y al formulario.

Verificado con `odoo-bin shell` en `construtec_test`: un ticket abierto (`is_closed=False`) y uno ya facturado (`billing_state='facturado'`, tras postear su propia factura) **no** aparecen en `available_ticket_mirror_ids` de una factura nueva; uno hecho y sin facturar sí aparece. Vinculado ese último a la factura y posteada (pasa a `billing_state='facturado'`), **sigue** apareciendo en `ticket_mirror_ids` de esa misma factura pese a ya no calificar para el domain — confirma que no se reabrió el bug de "desaparición" ya documentado en el otro módulo. `-u` limpio en `construtec_test`, sin `ERROR`/`CRITICAL` nuevos.

## Verified

`odoo-bin shell` against `construtec_test` (`Odoo19E`): `sync_from_community()` creates on first call, upserts (same id, updated `costo_total`) on a second call with the same `number` — never duplicates; linking `move_id` to a draft invoice keeps `billing_state='no_facturado'`; posting the invoice (unpaid) flips it to `facturado`; two different mirror tickets sharing the same `move_id` both read `facturado`/`cobrado` together and `account.move.ticket_mirror_count == 2`; registering full payment via `account.payment.register` flips both to `cobrado` with `payment_id` resolved; `action_view_ticket_mirrors()` builds the correct domain. `-u`/`-i` clean on `construtec_test`, no new `ERROR`/`CRITICAL` in `odoo.log` (only pre-existing, differently-dated noise already documented in the top-level `Odoo19E\server\odoo19e\CLAUDE.md`).

## Dual-repo deployment

Installed verbatim in both `odoo19e` and `odoo19enterprise` (same convention as `construtec_account_payment_order_19`, `construtec_materials_sync_19`, etc.) — any change here must be copied to both and committed/pushed in both.
