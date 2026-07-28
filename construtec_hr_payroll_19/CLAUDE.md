# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this module is

Guatemala payroll core: loans (`hr.loan`), salary advances (`salary.advance`), performance-bonus qualifications (`hr.qualification`), the unified `hr.payslip` extension, and batch payment wizards. Consolidates 5 Odoo 16 modules (`ent_hr_payroll_extension`, `ent_ohrms_loan`, `ent_ohrms_salary_advance`, `nomina`, `payslip_payment`, all under `..\Odoo16\`) into one. Enterprise-only (depends on `account_accountant`, `hr_payroll_account`, `hr_work_entry_enterprise`) — this was a deliberate scope decision, not an oversight; don't add Community-compatibility shims without checking with the user first.

No other `construtec_*` module depends on this one being anything other than what it is — this is the foundation; `construtec_hr_employee_19`, `construtec_hr_reports_19`, and `construtec_account_reports_19` all depend on it (directly or transitively) for `hr.version` fields (`bonificacion_incentivo`, `bonificacion_fija`, `bonificacion_productividad`, `horas_extra_valor`) and `hr.payslip`/`account.payment` fields.

## Architecture

- **`hr.contract` doesn't exist in Odoo 19** — it was replaced by `hr.version` (delegated onto `hr.employee` via a compute, not classic `_inherits`). Every field that used to live on `employee_contract_id`/`contract_id` in the Odoo 16 source now lives on `version_id` (`models/hr_version.py`, `models/hr_loan.py`, `models/salary_advance.py`). If you're porting more logic from `..\Odoo16\`, assume `contract_id`/`employee_contract_id` needs to become `version_id`, not just a rename — check field names still exist on `hr.version` in `..\..\odoo\addons\hr\models\hr_version.py` before assuming.
- **`hr.payslip` is extended in exactly one place**: `models/hr_payslip.py`. The 4 original modules each had their own separate `_inherit = 'hr.payslip'` class; they're merged into one here (`_compute_extra_inputs()` is the fan-in point for loan/advance/qualification input lines — search there before adding a 5th source of payslip inputs).
- **`balance`/`total_amount`** on `hr.payslip` are a single `@api.depends` compute (not stored `@api.onchange`, which was the original bug — balance didn't recompute outside a form context). Don't reintroduce `@api.onchange` for money fields that need to be correct from server-side code (wizards, reports).
- **Payment wizards are deliberately decoupled from `hr_payroll_account`'s internal accounting-move pipeline** (`_prepare_line_values`/`_get_existing_lines` changed shape substantially in v19). They create `account.payment` records directly linked via `payslip_id`, and leave journal-entry generation to core's own `action_payslip_done()` → `_action_create_account_move()`. Don't try to "fix" this by hooking into the core pipeline unless you've re-verified its current signature.
- **Security**: no more `gth.nominas_admin`/`informatica.informatica_admin` external groups (they were referenced but never declared in the original — a latent bug). Payment-wizard access is `hr.group_hr_manager` + `account.group_account_manager` directly, no custom group.
- **`send_salary_voucher()`** looks up `construtec_hr_reports_19.email_template_voucher` via `env.ref(..., raise_if_not_found=False)` — it's a soft, no-op-until-installed dependency, not a hard manifest dependency on that module (which itself depends back on this one). Don't add `construtec_hr_reports_19` to this module's `depends` — that would be circular.

## Known gaps (by design, not by accident)

- `hr_leave.py`'s automatic work-entry generation from the original `nomina` module was **not ported** — it was already dead code (import commented out) with a hardcoded 14:00–22:00 shift window, confirmed with the user as out of scope.
- `hr.payslip.employees`' forced-`False` employee-selection override was **removed**, restoring stock Odoo 19 bulk-payslip-generation behavior.

## Common commands

```
..\..\python\python.exe ..\odoo-bin -c ..\odoo.conf -d <dbname> -u construtec_hr_payroll_19 --stop-after-init
```

See `..\CLAUDE.md` for the disposable-test-DB verification workflow.
