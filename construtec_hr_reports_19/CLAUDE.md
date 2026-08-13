# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this module is

Guatemala payroll compliance reports: 11 XLSX-generating wizards (Planilla de Sueldos, Libro de Sueldos y Salarios, Informe del Empleador, Planilla IGSS, Reporte de Descuentos, Pasivo Laboral × 3, Reporte de Facturación, Reporte Liquidación Empleados, Detalle de Recibos de Nómina) plus QWeb PDF reports (constancia laboral, constancia de ingresos, historial laboral, solicitud IRTRA, salary voucher). Migrated from `gth_reports` + `nomina_report` (`..\Odoo16\`). Depends on both `construtec_hr_payroll_19` and `construtec_hr_employee_19`.

## Architecture

- **`wizard/wizard_mixin.py`** (`construtec.nomina.report.wizard.mixin`, an `AbstractModel`) carries `state`/`name`/`data`/`company_id`, `check_date()`, `got_back()`, `new_workbook()`/`finalize_workbook()` (in-memory `xlsxwriter`, no temp files — the original wrote to `tempfile.gettempdir()`), and `selection_label()`. All 10 wizard classes inherit it — don't re-declare that boilerplate in a new wizard, inherit the mixin.
- **`models/hr_dias_laborados_mes.py`**: replaces a hardcoded year-specific "días laborados por mes" table that was baked into the original `WizardInformeEmpleador` Python code. **This table needs manual review/update every calendar year** (Guatemala's official asuetos change) — it's now editable data (Settings → HR → Configuration → Días Laborados por Mes), not code, but nobody will remind you to update it; if you're touching `Informe del Empleador` around year-end, check this table's current year has rows.
- **`_compute_promedios()`** (`models/hr_employee.py`) is the 3-month rolling average salary calculation used by constancia-de-ingresos-style reports — genuinely intricate (quincena-pairing logic to reconstruct "full months" from biweekly payslips). It was restructured (dict-based buckets instead of ~24 parallel scalar variables) but the *math* was preserved exactly from the Odoo 16 source; if a client disputes a number here, diff against `..\Odoo16\gth_reports\models\hr_employee.py`'s `_compute_promedios` before assuming the port introduced a bug.
- **`send_salary_voucher()`** in `construtec_hr_payroll_19` resolves `construtec_hr_reports_19.email_template_voucher` via `env.ref(raise_if_not_found=False)` — that XML-ID is defined in `data/voucher_email_template.xml` here. If you rename it, the payroll module's voucher emailing silently stops (no error, just never sends).
- **`mail.template.report_template` → `report_template_ids`** (Many2many now) and **`report_name` field is gone** (Odoo 19 mail.template) — if you touch `data/voucher_email_template.xml`, use the current field names, not what the Odoo 16 source used.
- **`wizard/report_detalle_nomina.py` (`wizard.reporte.detalle.nomina`) deliberately does NOT use a fixed `COLUMNS` list** like the other 10 wizards do. It builds columns dynamically from whatever `code`/`name` actually appear across `payslip.line_ids` in the selected date range (`_compute_matrix()`), because different salary structures don't all share the same rule set, and this wizard's whole point is "show me exactly what's in these payslips' detail" rather than a fixed compliance-report layout. `EXCLUDED_CODES` drops accrual/reserve-only codes (`BONO14`/`AGUINALDO`/`INDM`/`VACAC`) that clutter the detail without being part of the actual payment. It's also the only wizard in this module with **two separate result screens instead of one**: "Visor" (`action_ver`, state `view`, an unsanitized `preview_html` Html field) and "Excel" (`action_excel`, state `get`, the usual binary download) are independent — clicking one does not generate the other. `_compute_matrix()` is still the single source of truth feeding both, so don't let them drift by computing the matrix twice. The Excel additionally colors each dynamic column light green/light red per `DEDUCTION_CODES` + a keyword fallback on the rule name (see `_is_deduction()`) — this is a best-effort classification based on rule codes already established elsewhere in this module (`report_planilla_sueldos.py`/`report_libro_sueldos.py`/`report_planilla_igss.py`), **not** verified against production salary rule configuration (those rules live directly in the Odoo UI, not in this repo) — if a client reports a column colored backwards, add/adjust its code or a keyword in that constant rather than guessing again. The `date_start`/`date_end` filter uses **overlap** semantics (`date_from <= date_end AND date_to >= date_start`), not strict containment, so a payslip whose period only partially falls inside the selected range still shows up — don't "simplify" this back to containment, it was a deliberate fix for lotes being dropped when their period didn't nest exactly inside Del/Al. If you add a 12th wizard needing a fixed, known column layout (a legal/compliance report), copy the pattern from `report_planilla_igss.py` instead — don't copy this one's dynamic-columns approach for that case.

## Known gaps (by design)

None currently — all 10 wizards + 6 PDF reports were built and smoke-tested. If a future report is added to this module, follow the existing pattern (inherit the mixin, use `hr.version`/`hr.employee` fields already established in the two dependency modules, don't reintroduce `hr.contract`).

## Common commands

```
..\..\python\python.exe ..\odoo-bin -c ..\odoo.conf -d <dbname> -u construtec_hr_reports_19 --stop-after-init
```

See `..\CLAUDE.md` for the disposable-test-DB verification workflow.
