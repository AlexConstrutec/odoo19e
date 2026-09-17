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

## Datos Personales cargados desde Community + fix de 5 campos falsos del Informe del Empleador (2026-09-16/17)

Pedido explícito del usuario: hay personas sin cuenta en Enterprise (y sin privilegios de nómina) que sí ayudan a cargar los datos personales de colaboradores para el "Informe del Empleador" (`construtec_hr_reports_19`, ver ese CLAUDE.md) - necesitaban poder editar estos campos desde **Community**. La decisión de arquitectura (confirmada con el usuario): **propiedad por campo, no por lado** - cada campo se edita en UN SOLO lugar y es de solo lectura en el otro, para que nunca haya dos versiones peleando por cuál respetar:

- **Datos personales/demográficos** (nombres, apellidos, DPI, NIT, IGSS, estado civil, nacionalidad, etc.) → se editan en **Community**, se empujan hacia acá.
- **Estado laboral, salario, banco** → siguen siendo dueño de **Enterprise**, sin cambios (Community solo tiene un espejo de lectura, como siempre).

### Dos campos nuevos: `pueblo_pertenencia`/`comunidad_linguistica`

Antes de esta pasada, el Informe del Empleador mandaba **siempre el mismo valor fijo** (`1`/`10`) para TODOS los empleados en estas dos columnas - no eran campos reales, estaban hardcodeados dentro del wizard del reporte (`construtec_hr_reports_19/wizard/report_informe_empleador.py`). Se agregaron como Selections reales aquí (`hr_employee_selections.py`: `PUEBLO_PERTENENCIA`/`COMUNIDAD_LINGUISTICA`).

**⚠️ Advertencia real, sin resolver todavía**: los **códigos numéricos** de estos dos catálogos (no las etiquetas en español, esas sí están bien) son una aproximación mía basada en las categorías oficiales de Guatemala (Ley de Idiomas Nacionales, Decreto 19-2003) - **NO se verificaron contra el catálogo numérico exacto que MITRAB espera** en el archivo del Informe del Empleador. Aun así, cualquier valor real por empleado ya es una mejora sobre el `1`/`10` fijo de antes. Verificar los códigos con el catálogo oficial de MITRAB antes de confiar un filing real en ellos - ver el comentario extendido en `hr_employee_selections.py`.

### Otros 3 campos que "faltaban" en el reporte en realidad ya existían - el wizard no los leía

Investigado antes de agregar nada nuevo: "Nacionalidad", "País de origen" y "Número de expediente del permiso de extranjero" **ya eran campos reales y nativos** de `hr.employee` (`country_id`, `country_of_birth`, `permit_no` - stock `hr`, no de este módulo) - el wizard simplemente los ignoraba y mandaba `'GTM'`/`''` fijos. Ver la sección de `construtec_hr_reports_19` para el fix del wizard - aquí no hizo falta ningún campo nuevo para estos tres.

### `sync_personal_data_from_community()`: método receptor whitelisted, no `write()` directo

Llamado vía XML-RPC por el mismo usuario de integración ya usado para Órdenes de Pago/Marcajes de Asistencia (`group_payment_order_sync_integration`, ver `construtec_account_payment_order_19`) - ese usuario solo necesita permiso de **lectura** sobre `hr.employee` para poder invocar el método (`security/ir.model.access.csv` de ese módulo, fila `access_hr_employee_sync`) - la escritura real la hace este método con `.sudo()` internamente.

**`PERSONAL_DATA_FIELDS`** (lista blanca a nivel de módulo, en `hr_employee.py`) - cualquier clave en `vals` que no esté en esa lista se ignora en silencio, nunca se escribe. Así una fuga de esa API Key nunca puede escribir salario/banco/estado laboral - solo lo que esta lista blanca decide aceptar. `nacionalidad_code`/`pais_origen_code` (código ISO alpha-2, resueltos aquí contra `res.country.code`) y `municipio_nombre` (texto libre, resuelto por nombre exacto contra `hr.municipio` - sin match, se queda vacío, no se adivina) son los 3 únicos campos del payload que NO son texto/selección plana.

**⚠️ Riesgo real de despliegue, sin resolver**: `construtec_account_payment_order_19` está en la lista de módulos que `sync-to-enterprise.ps1` (Odoo19E) copia automáticamente desde Community - pero la copia de ESE módulo en Community ahora agrega sus PROPIOS campos `primer_nombre`/`nit`/`igss`/etc. (ver el CLAUDE.md de ese módulo) que **ya existen aquí, en este módulo, con los mismos nombres**. Si ese script se corre sin excluir esto, Enterprise terminaría con DOS declaraciones del mismo campo sobre `hr.employee` desde dos módulos distintos - no necesariamente truena (Odoo permite fields del mismo nombre desde varios `_inherit`), pero es confuso y duplicado. **No resuelto en esta pasada** - antes de volver a correr ese script, hay que decidir si excluir `construtec_account_payment_order_19` de la lista, o excluir específicamente su `hr_employee.py`/vistas/seguridad relacionadas a Datos Personales.

Verificado con `odoo-bin shell` en `construtec_test`: los 3 módulos (`construtec_hr_employee_19`, `construtec_hr_reports_19`, `construtec_account_payment_order_19`) instalan limpio; `sync_personal_data_from_community()` escribe correctamente los campos de la lista blanca, resuelve `nacionalidad_code` contra `res.country` (probado con 'mx' minúscula → México, confirma que el `.upper()` funciona), deja `municipio_id` sin tocar cuando no hay match exacto, e **ignora silenciosamente** una clave fuera de la lista blanca (probado con un campo inventado tipo "salario" - nunca se escribió, ni siquiera como atributo).

## Known gaps (by design)

- `_onchange_identification_id`'s duplicate-DPI check now excludes `self._origin.id` — the original didn't, so editing an existing employee could self-match as a "duplicate." Confirmed fixed via the module's own smoke test; don't remove that exclusion.
- `EnviarMensaje()` (a SOAP/`zeep` WhatsApp integration in the original `hr_employee.py`) was dropped — it had zero callers anywhere in the Odoo 16 source tree.
- `hr_request_employee*`, `request_jornada`, `request_experiencia`, `request_licencia`, `wizard_motivo_rechazo` from the original module were never imported in its own `models/__init__.py` — dead code, not ported.

## Common commands

```
..\..\python\python.exe ..\odoo-bin -c ..\odoo.conf -d <dbname> -u construtec_hr_employee_19 --stop-after-init
```

See `..\CLAUDE.md` for the disposable-test-DB verification workflow.
