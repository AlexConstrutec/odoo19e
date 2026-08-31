# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this module is

Extended employee identity/personal-data fields (DPI, NIT, IGSS, name parts, family/education/work-history sub-models), Guatemala department/municipality catalogs (`hr.departamento`/`hr.municipio`), and a rehire snapshot cache (`hr.codigo.employee`). Migrated from the Odoo 16 module `gth` (`..\Odoo16\gth\`). Depends on `construtec_hr_payroll_19` (for `hr.version` bonus fields consumed by the employment-history salary snapshot).

## Architecture

- **`hr.version` fields already provided by core, not redeclared here**: `identification_id`, `job_title`, `registration_number`, `departure_reason_id`, `departure_date`, `km_home_work`, `sex` (not `gender` — Odoo 19 renamed it). If you're tempted to add a field, grep `..\..\odoo\addons\hr\models\hr_version.py` / `hr_employee.py` first — several fields the Odoo 16 source redeclared turned out to already exist natively in v19 and were dropped rather than duplicated.
- **`hr.codigo.employee` (rehire cache)**: when an employee's DPI matches a previously-known one, `apply_to_employee()`/`update_from_employee()` (`models/hr_codigo_employee.py`) sync ~25 fields between the two models via a field-name map (`IDENTITY_FIELDS`/`RENAMED_FIELDS`), not 3 separate 20-line hand-written blocks like the original. If you add a new synced field, add it to that map — don't hand-write another sync block in `hr_employee.py`.
- **`_sync_employment_history()`** on `hr.version` (`models/hr_version.py`) replaces 5 scattered `@api.onchange` methods from the original `hr_contract.py` with one method called from both `create()` and `write()` — meaning it now also fires on programmatic/API writes, not just form edits (a deliberate behavior improvement, not just a refactor).
- **`work_contact_id`**, not `address_home_id` (renamed in core). **`bank_account_ids`** (Many2many), not `bank_account_id` (Many2one, gone). Both matter if porting more of `..\Odoo16\gth\`'s address/bank onchange logic.

## CSV Banrural: carga masiva de cuentas por lote de nómina

`models/hr_payslip_run.py` (`_inherit = 'hr.payslip.run'`) — botón **"CSV Banrural"** (visible solo con el lote en `state == '02_close'`), previamente sin documentar aquí (agregado en un commit puntual, sin actualizar este CLAUDE.md - corregido ahora). Genera el archivo de carga masiva de cuentas para el portal de Banrural, un archivo por lote de nómina.

**No bloquea si hay empleados de otros bancos en el mismo lote** (cambio de comportamiento pedido por el usuario 2026-08-31 - la versión original bloqueaba con `UserError` en cuanto CUALQUIER empleado del lote no tuviera cuenta Banrural, obligando a corregir cuentas antes de poder generar nada útil, aunque la mayoría del lote sí fuera de Banrural). Diseño actual:
- **Bloque superior**: solo empleados con cuenta Banrural (`bank_account_ids` filtrado por `bank_id.name` conteniendo "banrural"), con las columnas exactas que espera el portal - listo para cargar tal cual.
- **3 líneas en blanco** de separador (solo si hay al menos un empleado sin cuenta Banrural en el lote - si todos son Banrural, no se agrega nada más).
- **Bloque inferior**: un aviso (`EMPLEADOS SIN CUENTA BANRURAL - eliminar estas filas antes de cargar al banco`), un segundo encabezado con una columna extra **"Banco real"**, y una fila por cada empleado que no tiene cuenta Banrural - con su banco real (`Sin cuenta bancaria registrada` si no tiene ninguna cuenta bancaria en absoluto). La idea: quien vaya a cargar el archivo al banco simplemente borra ese bloque completo antes de subirlo, en vez de tener que regenerar el archivo después de corregir cuentas.
- Método/botón renombrados de `action_generar_csv_banco`/"Generar CSV Banco" a **`action_generar_csv_banrural`**/"CSV Banrural" - el usuario planea agregar formatos CSV para otros bancos más adelante, así que el nombre genérico original ya no describía bien lo que hace (es específico de Banrural, no un CSV bancario genérico).
- Sigue codificado en **Windows-1252 (cp1252)**, no UTF-8 - confirmado contra un archivo real de referencia del portal de Banrural, que falla al decodificarse como UTF-8.

**Trampa real al escribir el script de verificación de esto**: `hr.employee.bank_account_ids` es un `Many2many` explícito (tabla `employee_bank_account_rel`, ver `odoo/addons/hr/models/hr_employee.py`) - **crear un `res.partner.bank` con `partner_id = employee.work_contact_id` NO lo agrega automáticamente a `bank_account_ids`** (el `domain` del campo solo restringe qué cuentas se PUEDEN elegir, no vincula nada solo). Hace falta un `employee.write({'bank_account_ids': [(4, cuenta.id)]})` explícito (que es justo lo que hace el widget nativo "Cuentas bancarias" del formulario de empleado) - de lo contrario `bank_account_ids` queda vacío y el filtro por banco no encuentra nada, aunque la cuenta exista en la base.

## Known gaps (by design)

- `_onchange_identification_id`'s duplicate-DPI check now excludes `self._origin.id` — the original didn't, so editing an existing employee could self-match as a "duplicate." Confirmed fixed via the module's own smoke test; don't remove that exclusion.
- `EnviarMensaje()` (a SOAP/`zeep` WhatsApp integration in the original `hr_employee.py`) was dropped — it had zero callers anywhere in the Odoo 16 source tree.
- `hr_request_employee*`, `request_jornada`, `request_experiencia`, `request_licencia`, `wizard_motivo_rechazo` from the original module were never imported in its own `models/__init__.py` — dead code, not ported.

## Common commands

```
..\..\python\python.exe ..\odoo-bin -c ..\odoo.conf -d <dbname> -u construtec_hr_employee_19 --stop-after-init
```

See `..\CLAUDE.md` for the disposable-test-DB verification workflow.
