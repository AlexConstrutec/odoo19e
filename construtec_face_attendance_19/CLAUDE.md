# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this module is

`construtec_face_attendance_19` replaces the single Check in/Check out button in `hr_attendance`'s systray widget with **4 marcajes** — Inicio de Labores/Hora Extra, Inicio de Alimentación, Fin de Alimentación, Fin de Labores/Hora Extra — each gated by real face recognition, done entirely with free/local tooling (no paid AI service, no API key, no third-party account). `depends: hr_attendance, mail, analytic, construtec_account_payment_order_19` (the last one purely to reuse the already-built Community→Enterprise sync channel/credentials — see "Sincronización de marcajes" below).

Built for técnicos who log into Odoo from their own phone (not the public kiosk) — the goal was to stop buddy-punching without depending on any external face-recognition vendor. See memory `construtec_face_attendance_project` (if present) for the full back-and-forth that led to this design; the short version is below.

## Es un módulo de Community (2026-09-09)

Entre 2026-09-08 y 2026-09-09 este módulo pasó por dos diseños: primero se lo hizo instalable "por igual" en Community y Enterprise (sin depender de nada Community-only), y un día después el usuario pidió revertir esa posición: **Enterprise nunca marca asistencia** (no tiene sentido arrastrar `hr_attendance` ahí solo para reusar 3 cosas del mapa/reporte), así que este módulo vuelve a pensarse como **de Community**, aunque el código en sí no tenga ninguna dependencia Community-only (nada le impide técnicamente instalarse en otro lado, pero no es la intención).

`construtec_attendance_sync_19` (Enterprise) dejó de depender de este módulo por completo - tiene su propio modelo espejo, su propio mapa (Leaflet duplicado, no compartido) y su propio controlador, sin `hr_attendance` en ningún lado de esa cadena. Ver su CLAUDE.md.

El gating a Administrador usa **`hr.group_hr_manager`** (grupo nativo de `hr`, no de `construtec_roles_permisos_19`) en los mismos 7 puntos de siempre (3 filas de `ir.model.access.csv`, 2 menús, la pestaña de enrolamiento facial, el chequeo manual `has_group()` en `/map_data`) - esto se mantiene igual que antes, es independiente de la decisión de dónde se instala el módulo.

## Sincronización de marcajes: Community → Enterprise (push, con upsert para el ticket)

Mismo patrón que `construtec_helpdesk_field_service`→`construtec_ticket_billing_19`: se dispara en `create()` (solo si `company.payment_order_role == 'solicitante'` y `payment_order_sync_enabled` - en cualquier otra compañía es un no-op silencioso).

- `construtec_attendance_mark.py`: `sync_state`/`sync_error`/`sync_date`, `_prepare_sync_vals()` (payload plano - `employee_enterprise_ref` del empleado, nunca su id local; `analytic_enterprise_ref` de la cuenta analítica si aplica; `source_record_id=self.id`, usado del lado receptor solo para idempotencia, nunca como llave de negocio), `_sync_to_enterprise()`, `action_retry_sync()`, `_cron_retry_sync()` (cron nuevo, `data/attendance_mark_sync_cron.xml`, cada 30 min).
- El helper JSON-RPC (`_jsonrpc`/`authenticate`) se importa directo de `construtec_account_payment_order_19.tools.enterprise_sync_api` (de ahí la nueva dependencia de módulo) - una excepción deliberada a la convención de "cada integración copia su propio cliente HTTP" ya documentada en ese módulo: aquí se quiere reutilizar la MISMA URL/credencial que ya usan las Órdenes de Pago (mismo Enterprise, mismo usuario de integración), no una integración independiente revocable por separado.
- **El núcleo NO manda `ticket_id`** en el payload (no sabe que ese campo existe - lo agrega `construtec_face_attendance_helpdesk_19` sobreescribiendo `_prepare_sync_vals()`). Como ese campo se completa en un `write()` DESPUÉS del `create()` que ya disparó el primer envío, el receptor tiene que aceptar una actualización posterior por `source_record_id` - ver el CLAUDE.md de ese módulo y el de `construtec_attendance_sync_19`.
- **Receptor**: `construtec_attendance_sync_19` (Enterprise-only, independiente de este módulo) - ver su propio CLAUDE.md.

## Architecture: client recognizes, server decides

The face matching itself runs **twice**, deliberately:

1. **Browser**: `face-api.js` (vendored under `static/src/js/`, TensorFlow.js underneath, MIT-licensed, no network calls) computes a 128-float descriptor from the live camera feed. This is the same library Cybrosys's `face_recognized_attendance_login` module uses — the difference here is what happens *after*.
2. **Server**: the browser sends only that 128-float vector (never the raw image) to `/construtec_face_attendance/verify` (`controllers/main.py`), which re-compares it — in plain Python, `_euclidean_distance()`, no ML library needed server-side — against the employee's own 3 reference descriptors (`hr.employee.face_descriptor_front/left/right`, computed once at enrollment the same client-side way). Only if the server's own comparison passes does it drop a **single-use, 60-second session token** (`SESSION_FACE_TS`/`SESSION_FACE_UID`).
3. Every real marcaje route (`ConstrutecHrAttendances.systray_attendance` override, and the new `/construtec_face_attendance/mark`) calls `_construtec_assert_face_verified()` first, which consumes that token. No token → `UserError`, no exceptions. This is what stops someone from just calling the check-in route directly to skip the camera — the gap that the stock Cybrosys module has.

**Enrollment** (loading the 3 reference photos) is Administrador (RRHH)-only — a new "Reconocimiento Facial" tab on the employee form (`views/hr_employee_views.xml`), using a custom `construtec_face_capture` field widget (`static/src/js/face_capture_field.js`) that offers both **live camera capture** and **upload an existing photo** (added because RRHH sometimes just gets a photo over WhatsApp rather than sitting the técnico in front of a webcam). Access is enforced twice: the view page has `groups="hr.group_hr_manager"`, and `security/ir.model.access.csv` grants that same group direct `hr.employee` read/write.

## The 4 marcajes: deliberately simple, no state machine

`mark_type` on `construtec.attendance.mark` is one of `inicio_labores` / `inicio_alimentacion` / `fin_alimentacion` / `fin_labores`. Two design choices the user was explicit about, both against my first instinct:

- **No sequence validation.** All 4 buttons are always clickable regardless of the employee's current state. Pressing "Inicio de Labores" while already checked in just does whatever `hr.attendance`'s own toggle does (checks them out, since that's the only mechanically possible action) — the mismatch between what was pressed and what happened gets corrected by a human reviewing the report afterward, not blocked by the app. This was a conscious user decision ("no es algo tan complejo... que alguien aplique el criterio"), not an oversight.
- **"Labores" vs "Hora Extra" is just button text, not two different flows.** There is no logic anywhere trying to detect what counts as overtime — shift start times vary too much (8am, 2am, 8pm) to make that determination automatically. The button always says "Inicio de Labores / Hora Extra"; a human classifies it later.
- **15-minute cooldown, same rule for all 4 buttons independently** — `_construtec_check_cooldown()` looks at that employee's own last row of that *same* `mark_type` and blocks a repeat within 15 min (server-enforced; the client also does a lightweight local check in `attendance_menu_patch.js` purely to skip opening the camera for nothing, but the server call is what actually matters).

`inicio_labores`/`fin_labores` still drive real `hr.attendance` check-in/out (so worked-hours reporting keeps working natively); `inicio_alimentacion`/`fin_alimentacion` only ever write to `construtec.attendance.mark` — Odoo has no native meal-break concept, so this module doesn't try to bolt one onto `hr.attendance` itself.

## Reporting: list + map

- **Marcajes de Asistencia** (`views/construtec_attendance_mark_views.xml`) — list/pivot of every `construtec.attendance.mark` row: employee, tipo, cuenta analítica, observaciones, and a `maps_url` computed field (`widget="url" text="Ver en mapa"`) that opens the single point in **OpenStreetMap** (not Google Maps — no API key, no account, matches the rest of this module's "no paid third party" rule).
- **Mapa de Marcajes** (`construtec_attendance_map_wizard.py` + `construtec_attendance_map_action.js`) — a wizard (date range + optional employee filter) opens an `ir.actions.client` that renders an actual **Leaflet.js** map (vendored under `static/src/lib/leaflet/`, BSD-2-Clause, OpenStreetMap tiles) with one pin per marcaje, colored per employee, popup with name/tipo/datetime. This is the only one of the three options that supports *multiple* points at once — Odoo's native Map View (`web_map`) is Enterprise-only in a stock install (this same module now runs on Enterprise too, but there was no reason to swap a working, free solution for a native one).
- Both are gated to `hr.group_hr_manager` (location data is sensitive) — the `/construtec_face_attendance/map_data` route re-checks that group server-side too, not just via the menu's `groups=` attribute. In Enterprise, `construtec_attendance_sync_19` extends this same route to also plot marcajes received from Community.

Ticket linking (opcional, solo Community) vive en `construtec_face_attendance_helpdesk_19` — ver su propio CLAUDE.md.

## Company settings this module depends on (but doesn't install/enable itself)

Two stock `hr_attendance` company-level toggles must be ON for anything here to work, and neither defaults to `True`:
- `attendance_from_systray` — without it the systray icon (and therefore all 4 buttons) never renders at all.
- `attendance_device_tracking` — without it the browser never even asks for geolocation, so every marcaje silently saves `latitude=longitude=0.0` and the map/link features have nothing to show. Both bit me during testing on a copied database (`construtec_community_0509`) where they were off by default — check `Ajustes > Asistencias` first if marcajes look "broken" but the camera step worked fine.

## Gotchas hit while building this (Odoo 19 specifics)

- **`<group>` inside a `<search>` view no longer accepts `expand=`/`string=` attributes** in this Odoo 19 — stock examples with `<group expand="0" string="Group By">` you'll find in older docs/tutorials will fail RNG validation here (`Invalid attribute expand for element group`). Use bare `<group>`.
- **Don't call `_()` at Python module level** (e.g. building a labels dict as a global) — it logs "no translation language detected" warnings on every import because there's no request context yet at import time. Use plain strings for module-level constants; only call `_()` inside request-handling methods.
- **Field widgets register as a plain descriptor object**, not `Component.extractProps = ...`: `registry.category("fields").add(name, { component, extractProps, supportedTypes })`, matching stock widgets like `badge_field.js` — not the pattern some older-version examples show.
- A running dev server (`odoo-bin`, no `--dev=reload`) **does not pick up Python changes** from a separate `-u module --stop-after-init` upgrade run — that upgrade touches the DB schema but the already-running process keeps the old code in memory. Always kill and restart the live process after any Python (not just JS/XML) change, or you'll chase phantom bugs that are actually just stale code.

### Bug real: el popup del mapa mostraba la hora UTC cruda, no la hora local del marcaje (2026-09-08)

Reportado por el usuario en producción (AWS/Docker): marcó a las 18:30 hora de Guatemala, pero el popup del pin en "Mapa de Marcajes" mostraba 23:30. Se descartó primero un problema de reloj del servidor (`date -u` en la instancia real coincidía exactamente con la hora UTC verdadera para ese instante - `00:37 UTC` = `18:37` Guatemala, UTC-6 correcto) - el reloj del servidor está bien, no hay que tocarlo ni editar nada en la base de datos.

**Causa real**: `controllers/main.py` (`map_data()`/`recent_marks()`) manda `fields.Datetime.to_string(mark.create_date)` - una hora UTC cruda, sin convertir - y `attendance_map_action.js` la imprimía tal cual en el popup del pin (`${point.datetime}`, sin ningún tratamiento). La tabla ("Marcajes de Asistencia") y el mini-historial del propio systray (`attendance_menu_patch.js`, `formatMarkDatetime()`) SÍ mostraban la hora correcta, porque ambos ya pasan el valor por `deserializeDateTime()` (`@web/core/l10n/dates`, el helper oficial de Odoo que convierte una hora UTC cruda a la zona horaria del usuario) antes de mostrarla - el mapa era el único lugar que se saltaba ese paso.

**El fix**: `attendance_map_action.js` importa el mismo `deserializeDateTime` y aplica el mismo tratamiento (`formatPointDatetime()`, mismo patrón que `formatMarkDatetime()`) antes de insertar la hora en el popup. Ningún cambio en Python/backend - el dato guardado (`create_date`, UTC) siempre estuvo correcto, solo la vista del mapa no lo convertía.

**Pendiente de verificar**: no se pudo probar en vivo en un navegador en esta sesión porque otra sesión de Claude Code ya tenía ocupado el servidor de desarrollo local en el puerto 8069 - confirmar visualmente en el mapa real (AWS) tras desplegar este archivo, o en un servidor local libre.

## Adding to this module

Same layout/update rules as the rest of `odoo19c` — see the top-level `CLAUDE.md`. If you rename this folder, update the `depends` entries in any module that references it and the module-prefixed asset paths in `__manifest__.py`.
