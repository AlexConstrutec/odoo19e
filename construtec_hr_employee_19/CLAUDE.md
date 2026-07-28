# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this module is

Extended employee identity/personal-data fields (DPI, NIT, IGSS, name parts, family/education/work-history sub-models), Guatemala department/municipality catalogs (`hr.departamento`/`hr.municipio`), and a rehire snapshot cache (`hr.codigo.employee`). Migrated from the Odoo 16 module `gth` (`..\Odoo16\gth\`). Depends on `construtec_hr_payroll_19` (for `hr.version` bonus fields consumed by the employment-history salary snapshot).

## Architecture

- **`hr.version` fields already provided by core, not redeclared here**: `identification_id`, `job_title`, `registration_number`, `departure_reason_id`, `departure_date`, `km_home_work`, `sex` (not `gender` — Odoo 19 renamed it). If you're tempted to add a field, grep `..\..\odoo\addons\hr\models\hr_version.py` / `hr_employee.py` first — several fields the Odoo 16 source redeclared turned out to already exist natively in v19 and were dropped rather than duplicated.
- **`hr.codigo.employee` (rehire cache)**: when an employee's DPI matches a previously-known one, `apply_to_employee()`/`update_from_employee()` (`models/hr_codigo_employee.py`) sync ~25 fields between the two models via a field-name map (`IDENTITY_FIELDS`/`RENAMED_FIELDS`), not 3 separate 20-line hand-written blocks like the original. If you add a new synced field, add it to that map — don't hand-write another sync block in `hr_employee.py`.
- **`_sync_employment_history()`** on `hr.version` (`models/hr_version.py`) replaces 5 scattered `@api.onchange` methods from the original `hr_contract.py` with one method called from both `create()` and `write()` — meaning it now also fires on programmatic/API writes, not just form edits (a deliberate behavior improvement, not just a refactor).
- **`work_contact_id`**, not `address_home_id` (renamed in core). **`bank_account_ids`** (Many2many), not `bank_account_id` (Many2one, gone). Both matter if porting more of `..\Odoo16\gth\`'s address/bank onchange logic.

## Known gaps (by design)

- `_onchange_identification_id`'s duplicate-DPI check now excludes `self._origin.id` — the original didn't, so editing an existing employee could self-match as a "duplicate." Confirmed fixed via the module's own smoke test; don't remove that exclusion.
- `EnviarMensaje()` (a SOAP/`zeep` WhatsApp integration in the original `hr_employee.py`) was dropped — it had zero callers anywhere in the Odoo 16 source tree.
- `hr_request_employee*`, `request_jornada`, `request_experiencia`, `request_licencia`, `wizard_motivo_rechazo` from the original module were never imported in its own `models/__init__.py` — dead code, not ported.

## Common commands

```
..\..\python\python.exe ..\odoo-bin -c ..\odoo.conf -d <dbname> -u construtec_hr_employee_19 --stop-after-init
```

See `..\CLAUDE.md` for the disposable-test-DB verification workflow.
