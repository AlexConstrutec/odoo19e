# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this module is

Guatemala payroll compliance reports: 10 XLSX-generating wizards (Planilla de Sueldos, Libro de Sueldos y Salarios, Informe del Empleador, Planilla IGSS, Reporte de Descuentos, Pasivo Laboral × 3, Reporte de Facturación, Reporte Liquidación Empleados) plus QWeb PDF reports (constancia laboral, constancia de ingresos, historial laboral, solicitud IRTRA, salary voucher). Migrated from `gth_reports` + `nomina_report` (`..\Odoo16\`). Depends on both `construtec_hr_payroll_19` and `construtec_hr_employee_19`.

## Architecture

- **`wizard/wizard_mixin.py`** (`construtec.nomina.report.wizard.mixin`, an `AbstractModel`) carries `state`/`name`/`data`/`company_id`, `check_date()`, `got_back()`, `new_workbook()`/`finalize_workbook()` (in-memory `xlsxwriter`, no temp files — the original wrote to `tempfile.gettempdir()`), and `selection_label()`. All 10 wizard classes inherit it — don't re-declare that boilerplate in a new wizard, inherit the mixin.
- **`models/hr_dias_laborados_mes.py`**: replaces a hardcoded year-specific "días laborados por mes" table that was baked into the original `WizardInformeEmpleador` Python code. **This table needs manual review/update every calendar year** (Guatemala's official asuetos change) — it's now editable data (Settings → HR → Configuration → Días Laborados por Mes), not code, but nobody will remind you to update it; if you're touching `Informe del Empleador` around year-end, check this table's current year has rows.
- **`_compute_promedios()`** (`models/hr_employee.py`) is the 3-month rolling average salary calculation used by constancia-de-ingresos-style reports — genuinely intricate (quincena-pairing logic to reconstruct "full months" from biweekly payslips). It was restructured (dict-based buckets instead of ~24 parallel scalar variables) but the *math* was preserved exactly from the Odoo 16 source; if a client disputes a number here, diff against `..\Odoo16\gth_reports\models\hr_employee.py`'s `_compute_promedios` before assuming the port introduced a bug.
- **`send_salary_voucher()`** in `construtec_hr_payroll_19` resolves `construtec_hr_reports_19.email_template_voucher` via `env.ref(raise_if_not_found=False)` — that XML-ID is defined in `data/voucher_email_template.xml` here. If you rename it, the payroll module's voucher emailing silently stops (no error, just never sends).
- **`mail.template.report_template` → `report_template_ids`** (Many2many now) and **`report_name` field is gone** (Odoo 19 mail.template) — if you touch `data/voucher_email_template.xml`, use the current field names, not what the Odoo 16 source used.

## Known gaps (by design)

None currently — all 10 wizards + 6 PDF reports were built and smoke-tested. If a future report is added to this module, follow the existing pattern (inherit the mixin, use `hr.version`/`hr.employee` fields already established in the two dependency modules, don't reintroduce `hr.contract`).

## Common commands

```
..\..\python\python.exe ..\odoo-bin -c ..\odoo.conf -d <dbname> -u construtec_hr_reports_19 --stop-after-init
```

See `..\CLAUDE.md` for the disposable-test-DB verification workflow.
