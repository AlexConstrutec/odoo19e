# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this module is

`account.payment.order` — a header model with a `tipo` field (`anticipo` / `liquidacion` / `pago_directo`) representing three flavors of a real Construtec accounting flow: money moves through an intermediary (an advance to a contact, or an employee reimbursement) and later has to be reconciled against vendor bills that belong to a **different partner** than the payment. Native Odoo reconciliation works per-partner/account and can't do this on its own. Migrated from the Odoo 16 module `bolson` (`..\Odoo16\bolson\`, "Manejo de cajas chicas y liquidaciones").

Only `tipo == 'liquidacion'` has real logic right now — it's the direct port of `bolson.bolson.conciliar()`/`cancelar()`. `anticipo` and `pago_directo` are structure only (the `tipo` selection value exists, the form shows a "not implemented yet" banner instead of action buttons) — do not add buttons for those without a fuller business-flow discussion first, this was an explicit scope decision, not an oversight.

## What each `tipo` means (for whoever implements the other two)

- **Anticipo**: hand a contact money up front, before any invoices exist. Confirmed design (user, this session): it's a normal `account.payment` to that contact, posted against an "anticipos por liquidar" account rather than the contact's normal payable — no invoices involved yet.
- **Liquidación**: the one that's built. Takes N vendor bills (`factura_ids`, possibly different suppliers) + N payments (`pago_ids`, e.g. a previous Anticipo's payment or loose cheques), nets them, and posts one regularizing `account.move` that reconciles everything — tolerating a mismatch via `cuenta_ajuste_id` if the totals don't line up exactly.
- **Pago Directo**: the 1:1 case — an employee pays a vendor bill out of pocket, in the company's name. Odoo ends up with a vendor bill (in the *vendor's* name) and needs a reimbursement payment (in the *employee's* name); the same cross-partner reconciling-move mechanism as Liquidación applies, just usually with one invoice and one payment.

## Architecture

- **`action_conciliar()`/`action_cancelar()`** (`models/account_payment_order.py`) are the ported `bolson.bolson.conciliar()`/`cancelar()`, guarded with `if self.tipo != 'liquidacion': raise UserError(...)`.
- **`factura_ids`/`pago_ids`** are `One2many` via the new `payment_order_id` field added to `account.move`/`account.payment` (`models/account_move.py`, `models/account_payment.py`) — same pattern as the original's `bolson_id`. The form uses `widget="many2many"` on these One2many fields (a deliberate Odoo trick, kept from the original) so users can search/attach *existing* posted bills/payments instead of creating new ones inline.
- **`no_liquidacion`** is a `related` field to itself (`payment_order_id.no_liquidacion`) on both `account.move` and `account.payment`, `store=True, readonly=False`, PLUS an `@api.onchange` + `create()`/`write()` override that looks up an order by that number and sets `payment_order_id` — this looks redundant but it's intentional and matches the original `bolson` pattern: typing a `no_liquidacion` value directly on an invoice/payment auto-attaches it to the matching order.
- **Domain fix vs. the original**: `bolson`'s `facturas` field filtered `[('payment_id', '=', False)]` — that field never existed on `account.move` (checked against `..\odoo\addons\account\models\account_move.py`; only `account.move.line.payment_id` and `account.move.origin_payment_id` exist). Replaced with `[('move_type', 'in', ('in_invoice', 'in_refund')), ('state', '=', 'posted')]`, which also fixes the original never actually restricting to vendor bills.

## Odoo 16 → 19 API deltas that mattered (checked against `..\odoo\addons\account\models\`)

| v16 (`bolson`) | v19 |
|---|---|
| `made_sequence_hole` | renamed **`made_sequence_gap`** |
| `communication` (account.payment) | renamed **`memo`** |
| `payment_state` selection (account.move) | gained a **`blocked`** value — don't hardcode a 6-item list |
| **`account.payment.state`** | **completely different lifecycle**: no longer `draft`/`posted`/`cancel`. Now `draft` / **`in_process`** / **`paid`** / `canceled` / `rejected` (`account_payment.py:36-43`). `action_post()` on a payment lands it in `in_process`, not `posted` — it only reaches `paid` once its "Outstanding Payments/Receipts" bridge account nets to zero (`_compute_state`, `account_payment.py:454-467`). **This bit us**: `pago_ids`'s domain and `action_conciliar()`'s loop originally filtered `state == 'posted'` (copied from the v16 pattern) and silently matched *zero* payments — `orden.pago_ids` came back empty with no error, because a One2many field's `domain=` is enforced on *read*, not just in the UI. Fixed to `state in ('in_process', 'paid')`. If you see a payment mysteriously missing from `factura_ids`/`pago_ids`, check its actual `state` value first, not just whether it "looks posted" in the UI. |
| `account.payment` no longer delegates to `account.move` for `line_ids` | `payment.line_ids` **raises `AttributeError`** — use **`payment.move_id.line_ids`**. The v16 module's `for l in c.line_ids:` relied on old-style `_inherits` delegation that no longer applies. |
| Payments post through an **"Outstanding Payments"/"Outstanding Receipts" bridge account** (`account_type='asset_current'` in this DB, not `asset_cash`) before ever touching the bank | `bolson`'s netting filter (`account_type not in ['asset_cash']`) is **not enough** in v19 — that bridge account passes the same filter, and since it's always a balanced in/out pair *within the payment itself*, including it silently cancels out and produces a totals mismatch that has nothing to do with the real invoice/payment imbalance. Fixed by filtering explicitly to `account_type in ('asset_receivable', 'liability_payable')` — the only two account types that represent an actual amount owed to/from a partner, regardless of what the "other leg" of any given line turns out to be (cash, bridge account, whatever). This is more robust than the original's approach for any Odoo version, not just a v19 patch. |
| `account.payment.reconciled_invoice_ids`/`reconciled_bill_ids` are **computed fields with a custom `_search`** (`_search_reconciled_invoice_ids`, `account_payment.py:783`) that only implements `'in'`/`'='` against a **concrete id** (`browse(value).reconciled_payment_ids.ids`) | Putting `('reconciled_invoice_ids', '=', False)` in a domain silently becomes `browse(False)` → empty recordset → `[('id', 'in', [])]`, i.e. **matches nothing, ever** — not an error, just an empty result. This made `pago_ids` come back empty exactly like the `state` bug above, for a different reason. Fixed by **dropping both from the field's `domain=`** and keeping the check only as a plain Python attribute read inside `action_conciliar()` (`if pago.reconciled_invoice_ids or pago.reconciled_bill_ids: raise UserError(...)`), which goes through the normal compute and works fine. **Lesson for this module**: any computed field with a non-trivial custom `_search` is suspect as a domain filter for `=False`/`!=False` — verify empirically (as done here, via `odoo-bin shell`) rather than assuming `=False` means "is empty" the way it does for a plain stored field. |
| `reconciled_invoice_ids`, `reconciled_bill_ids`, `destination_account_id`, `amount_total_signed`, `amount_untaxed_signed`, `account_type`, `account.account.reconcile`, `account.move.line.reconcile()`/`.remove_move_reconcile()` | unchanged |

## Known gaps / dead code NOT ported

- `Odoo16\bolson\wizard\asignar.py` and `wizard\factura_selection_wizard.py`: use `account.invoice`/`@api.multi` (gone since Odoo 13), and the latter's domain even filters `move_type='out_invoice'` (customer invoices) despite the module being about vendor bills. Confirmed dead: `wizard/factura_selection_wizard.xml` is commented out in the v16 manifest, so this code never loaded. Not ported — the real "attach facturas/pagos" flow is the `widget="many2many"` trick on the main form.
- The v16 QWeb report (`reporte_bolson.xml`) referenced `f.number`/`f.reference` (removed from `account.move` since v13; use `f.name`/`f.ref`) and had a stray `-<t t-esc="foo"/>` (undefined variable, a leftover bug) — fixed when porting to `report/account_payment_order_report.xml`.

## Future: Community mirror

The user's stated plan: a future Odoo19 Community counterpart where more users create payment order *requests* through several approval phases before they land here as "aplicado". That's why `state` exists as a Selection now (`borrador`/`aplicado`/`cancelado`) even though today only two transitions are used — expect this field (or a linked request model) to grow more values later. Nothing else is built for that yet.

## Common commands

```
..\..\python\python.exe ..\odoo-bin -c ..\odoo.conf -d <dbname> -u construtec_account_payment_order_19 --stop-after-init
```

See `..\CLAUDE.md` for the disposable-test-DB verification workflow.
