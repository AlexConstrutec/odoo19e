# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this directory is

This is the **custom addons directory** for the Odoo19E (Enterprise) installation, referenced from `..\odoo.conf`:

```
addons_path = c:\users\alex\documents\proyectos\odoo19e\server\odoo\addons,c:\users\alex\documents\proyectos\odoo19e\server\odoo19e
```

It contains a set of custom modules being migrated from a legacy Odoo 16 deployment (source preserved under `Odoo16\`, one folder per legacy module — not wired into `addons_path`, kept only as migration source material) into 5 new Odoo 19 modules, each with its own `CLAUDE.md` with module-specific detail:

| Module | Migrated from | Status |
|---|---|---|
| [construtec_hr_payroll_19](construtec_hr_payroll_19/CLAUDE.md) | `ent_hr_payroll_extension`, `ent_ohrms_loan`, `ent_ohrms_salary_advance`, `nomina`, `payslip_payment` | Built |
| [construtec_hr_employee_19](construtec_hr_employee_19/CLAUDE.md) | `gth` | Built |
| [construtec_hr_reports_19](construtec_hr_reports_19/CLAUDE.md) | `gth_reports`, `nomina_report` | Built |
| [construtec_account_reports_19](construtec_account_reports_19/CLAUDE.md) | `account_report_financial` | Built |
| `construtec_petty_cash_19` | `bolson` | Not started |

Dependency order (each depends on the ones above it): `construtec_hr_payroll_19` → `construtec_hr_employee_19` → `construtec_hr_reports_19` → `construtec_account_reports_19` (also depends on `construtec_hr_payroll_19` directly, for `account.payment.payslip_id`).

## Why this isn't a straight port

Odoo 16 → 19 removed `hr.contract` entirely (merged into `hr.version`, delegated onto `hr.employee`), changed `hr.work.entry` from date-range to single-`date`+`duration`, renamed `hr.employee.address_home_id` → `work_contact_id`, dropped `attrs=`/`states=` in view XML, and reworked several core APIs referenced in the legacy modules (`mail.template.report_template`, `hr.payslip.run.state` values, etc.). Every module here was **redesigned against the current Odoo 19 source** (read directly from `..\odoo\addons\`), not translated line-by-line — see each module's own `CLAUDE.md` for the specific API deltas that mattered to it.

## Adding or updating a module here

Standard Odoo addon layout (`__manifest__.py`, `__init__.py`, `models/`, etc.). Install/update from `..\` (the `server\` directory) with the edition's bundled Python:

```
..\..\python\python.exe ..\odoo-bin -c ..\odoo.conf -d <dbname> -u <module_name> --stop-after-init
```

Two details in the top-level `C:\Users\Alex\Documents\Proyectos\CLAUDE.md` are stale relative to `..\odoo.conf`:
- `addons_path` now includes this `odoo19e` folder (the top-level doc still describes it as unwired)
- `db_user`/`db_password` in `..\odoo.conf` are `alex`/`123`, not the documented `openpg` default

## Verifying changes here

There's no CI — verification is manual, via a disposable test database:

```
..\..\python\python.exe ..\odoo-bin -c ..\odoo.conf -d construtec_test -i <module_name> --stop-after-init --without-demo=all
```

then check `..\odoo.log` for new `ERROR`/`CRITICAL` lines (the log file is never truncated, so filter by today's date, not just `tail`), and drop the test DB afterward (`dropdb -h localhost -U alex construtec_test`, password `123`). For business-logic changes, prefer a quick script piped into `odoo-bin shell` over trusting "it installed cleanly" — several real bugs in this codebase (wrong field names, broken view inheritance, missing sequences) only surfaced when something was actually exercised at runtime, not at install time.
