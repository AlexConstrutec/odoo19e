# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this module is

Financial statement reports: Libro Diario, Libro Mayor, Balance de Saldos, Balance General, Estado de Resultados, Costo de Ventas/Producción, Estado de Cambios en el Patrimonio, Estado de Flujo de Efectivo, Libro de Inventario y Balances, Conciliación Bancaria, Reporte Bancarización — 12 XLSX wizards. Migrated from `account_report_financial` (`..\Odoo16\account_report_financial\`, a 13,888-line `wizard_report_financial.py`). Depends on `account_accountant` and `construtec_hr_payroll_19` (for `account.payment.payslip_id`, used by Bancarización).

**This was a re-engineering, not a port.** The original classified every balance-sheet/income-statement line by walking `account.group` parent/child prefixes plus dozens of literal hardcoded account codes (`'3010301'`, `'2010210'`, etc.) specific to one client's chart of accounts. That's gone — see below.

## Architecture

- **`models/account_classification.py`** is the single source of truth for financial-statement structure. `ACCOUNT_TYPE_INFO` maps Odoo's native `account.account.account_type` (e.g. `asset_cash`, `liability_payable`, `expense_direct_cost`) to `(nivel1, etiqueta_nivel1, etiqueta_nivel2, signo)`. `build_report_tree()` aggregates `account.move.line` balances into that hierarchy. **Every report in this module that needs balance-sheet/income-statement classification calls into this file — don't reintroduce per-wizard hardcoded account codes or `account.group` prefix walks.** If a report's numbers look wrong, check here first, not in the individual wizard.
- **"Resultado del Ejercicio" (current-year earnings)** is computed live (`compute_resultado_ejercicio()`: sum of income/expense account balances for the open fiscal year) — the original hardcoded a specific GL account (`3010301`) to receive this figure. There is no such fixed account here; if a report needs to *post* this figure (not just display it), that's new scope, not something this module currently does.
- **`account.move.partida_contable`** (`models/account_move.py`) is a field this module **had to invent** — the original's raw SQL read `am.partida_contable` but no module in `..\Odoo16\` defines it; it must have lived in some other module never handed over for this migration. It's now a sequence (`account.move.partida_contable`, global not per-company) assigned in `_post()`. If numbers from the legacy system don't match "número de partida" here, this is why — it's a fresh sequence starting at 1, not a continuation of the old numbering.
- **Flujo de Efectivo** classifies cash movements via 3 `account.account.tag` records (`data/account_account_tag_data.xml`: `tag_flujo_operacion`/`_inversion`/`_financiamiento`), replacing hardcoded tag **database IDs** (`1`/`2`/`3`/`4`) in the original. **These tags must be manually assigned to the relevant accounts** (Settings → Accounting → Chart of Accounts → tags) for the report to reconcile — it ships with the tags defined but unassigned, and the report itself prints a "Diferencia (cuentas sin clasificar)" line to make an incomplete setup visible rather than silently wrong.
- **Costo de Ventas / Costo de Producción** and **Capital vs Reservas** (in Cambios al Patrimonio) had no native-Odoo distinguishing field to replace the original's hardcoded prefixes — both use an `account.group`-name-`ilike` heuristic (`_group_name_filter()` in `wizard/report_costo_ventas.py`, `_component_accounts()` in `wizard/report_cambio_patrimonio.py`) as a soft, non-hardcoded fallback. If the client's chart of accounts doesn't name groups "Producción"/"Capital"/"Reserva", these reports degrade gracefully (Costo de Producción shows the same accounts as Costo de Ventas; Cambios al Patrimonio dumps everything into "Otras Cuentas de Capital") rather than crashing — that's expected, not a bug, unless you're told the client's groups ARE named that way and it's still not splitting.

## Known gaps (by design — confirmed with the user, not silently dropped)

- **Libro de Compras and Libro de Ventas were not built.** Both depend on ~15 custom Guatemala FEL (electronic invoicing) fields on `account.move` (`tipo_documento`, `serie_fel`, `numero_fel`, a dozen `txt_total_*` VAT-breakdown fields) that don't exist in any module handed over for this migration — they live in a FEL integration module that was never provided. Fabricating that VAT classification would risk an incorrect tax filing. If that module ever surfaces, these two reports still need to be built from `..\Odoo16\account_report_financial\wizard\wizard_report_financial.py` (`wizard_libro_compras`/`wizard_libro_ventas`, lines ~6713–7896 in the original).
- **Reporte Bancarización** ships with 2 of its 12 columns (`Total de Retención IVA`, `IVA Retenido`) always blank — same FEL dependency, but the rest of the report (payment/invoice listing) works on core fields and wasn't worth dropping over 2 columns.
- **Libro de Inventario** does not reproduce the original's "comercial vs. no comercial" receivables/payables sub-split — there was no defensible native-Odoo field to base that on (guessing via `partner_id` presence would misclassify real client data), so it wasn't attempted. It's otherwise a fully-detailed, paginated, per-account statutory balance sheet.

## Common commands

```
..\..\python\python.exe ..\odoo-bin -c ..\odoo.conf -d <dbname> -u construtec_account_reports_19 --stop-after-init
```

See `..\CLAUDE.md` for the disposable-test-DB verification workflow.
