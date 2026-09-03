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

## Menu placement

`account.menu_finance_receivables` ("Customers", not "Vendors" — this is billing tickets to clients) — a standalone "Tickets (Community)" list/form, filtered to "Sin Facturar" by default (`context: {'search_default_sin_facturar': 1}`), so the accountant opens straight into what still needs a factura linked.

## Verified

`odoo-bin shell` against `construtec_test` (`Odoo19E`): `sync_from_community()` creates on first call, upserts (same id, updated `costo_total`) on a second call with the same `number` — never duplicates; linking `move_id` to a draft invoice keeps `billing_state='no_facturado'`; posting the invoice (unpaid) flips it to `facturado`; two different mirror tickets sharing the same `move_id` both read `facturado`/`cobrado` together and `account.move.ticket_mirror_count == 2`; registering full payment via `account.payment.register` flips both to `cobrado` with `payment_id` resolved; `action_view_ticket_mirrors()` builds the correct domain. `-u`/`-i` clean on `construtec_test`, no new `ERROR`/`CRITICAL` in `odoo.log` (only pre-existing, differently-dated noise already documented in the top-level `Odoo19E\server\odoo19e\CLAUDE.md`).

## Dual-repo deployment

Installed verbatim in both `odoo19e` and `odoo19enterprise` (same convention as `construtec_account_payment_order_19`, `construtec_materials_sync_19`, etc.) — any change here must be copied to both and committed/pushed in both.
