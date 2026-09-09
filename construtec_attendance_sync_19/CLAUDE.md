# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this module is

Lado receptor, **solo Enterprise**, del push de marcajes de asistencia que `construtec_face_attendance_19` (Community) dispara desde una instalación "Solicitante". `depends: ['hr', 'analytic', 'construtec_ticket_billing_19']` — **completamente independiente de `construtec_face_attendance_19` y de `hr_attendance`** (ver "Por qué es independiente" abajo). Enterprise nunca marca asistencia, solo recibe y muestra.

## Por qué es independiente del núcleo (2026-09-09)

Hasta el 2026-09-09 este módulo dependía de `construtec_face_attendance_19` únicamente para reusar 3 cosas suyas: la clase del controlador (`map_data()`), el diccionario `MARK_TYPE_LABELS`, y el wizard+mapa Leaflet ("Mapa de Marcajes"). Ese módulo trae `hr_attendance` como dependencia dura (lo necesita para el systray/enrolamiento, que Enterprise nunca usa) — así que instalar este receptor arrastraba `hr_attendance` a Enterprise sin ninguna necesidad real.

El usuario fue explícito: "no veo la necesidad de usar asistencias en Odoo Enterprise, a mí no me sirven de nada" — y pidió que el mapa se **adapte** (duplicado) en vez de compartirse, mismo criterio que ya usa el resto del proyecto para integraciones ("cada integración copia su propio cliente/UI" — ver `construtec_account_payment_order_19`, `construtec_ticket_billing_19`, etc.).

Por eso este módulo ahora tiene TODO lo que necesita por su cuenta:
- **`controllers/main.py`** — `ConstrutecAttendanceSyncController`, clase nueva (ya NO hereda de `ConstrutecFaceAttendanceController`), con su propia ruta `/construtec_attendance_sync/map_data` y su propia copia de `MARK_TYPE_LABELS`. Si el núcleo agrega/cambia un tipo de marcaje, hay que reflejarlo acá a mano (no hay ninguna comprobación automática).
- **`models/construtec_attendance_map_wizard.py`** — modelo `construtec.attendance.sync.map.wizard` (nombre distinto al del núcleo, `construtec.attendance.map.wizard`, para que no haya ninguna ambigüedad de que son cosas separadas).
- **`static/src/js/attendance_map_action.js` + `.xml`** — copia adaptada del Leaflet del núcleo (mismo tag ya no aplica: `construtec_attendance_sync_map`, ruta propia).
- **`static/src/lib/leaflet/`** — copia vendored de Leaflet.js (BSD-2-Clause), duplicada del núcleo (no hay ningún mecanismo de assets compartidos entre módulos de ediciones distintas).

Como consecuencia: aunque `construtec_face_attendance_19` técnicamente pueda instalarse en cualquier edición (no tiene dependencias Community-only en su código), la intención desde ahora es que **solo se instale en Community** — ver su propio CLAUDE.md ("Es un módulo de Community").

## Modelo: `construtec.attendance.mark.mirror` — upsert por `source_record_id` (ya NO create-only puro)

Antes del 2026-09-09 era create-only puro (un marcaje es un evento que nunca cambia después de creado). Ahora hace **upsert**: si el `source_record_id` ya existe, actualiza en vez de ignorar. La razón es el ticket (ver abajo) — sigue siendo cierto que un marcaje en sí no cambia, pero el vínculo a un ticket sí puede llegar en un segundo envío, después del primero.

`employee_id` (Many2one real a `hr.employee`) se resuelve por `employee_enterprise_ref`. `analytic_account_id` se resuelve por `analytic_enterprise_ref`. `ticket_mirror_id` (Many2one a `construtec.helpdesk.ticket.mirror`, de `construtec_ticket_billing_19` — el mismo espejo que ya usan para facturación) se resuelve por `ticket_number`, buscando por el campo `number` de ese modelo — nunca un id local de Community, mismo criterio "nunca ids entre bases" del proyecto.

## Por qué el ticket llega en un segundo envío (no en el primero)

En Community, `ticket_id` (agregado por `construtec_face_attendance_helpdesk_19`) se completa en un **segundo** `write()`, después de que `create()` del marcaje ya disparó el primer push (sin ticket, porque `_prepare_sync_vals()` corre en el momento del `create()`, antes de ese write). `construtec_face_attendance_helpdesk_19` sobreescribe `write()` para volver a llamar `_sync_to_enterprise()` cuando `ticket_id` cambia — eso es lo que llega acá como un segundo `sync_from_community(vals)` con el mismo `source_record_id` de antes.

## Seguridad

`group_construtec_attendance_sync_integration` — lectura + creación sobre `construtec.attendance.mark.mirror` a nivel ORM/UI (`perm_write=0`, `perm_unlink=0`). La actualización del segundo envío (ticket) pasa por `sudo()` DENTRO de `sync_from_community()` — una excepción puntual y acotada (nunca abre edición libre por ORM/UI con este grupo), documentada en el propio `security/construtec_attendance_sync_security.xml`.

**Bug real encontrado verificando el diseño anterior de punta a punta** (antes de este cambio, con un push HTTP real entre dos instancias locales): el grupo original era solo-creación (`perm_read=0`), pero un `create()` real vía `/jsonrpc` (`execute_kw`) exige que el usuario que llama tenga al menos permiso de **lectura** sobre el modelo para poder invocar *cualquier* método sobre él, incluso uno que nunca devuelve datos de lectura — chequeo anterior a que el método siquiera empiece a ejecutarse, ningún `sudo()` interno lo evita. Por eso el grupo tiene `perm_read=1`.

`hr.group_hr_manager` tiene lectura sobre el mirror y accede al wizard/mapa propio de este módulo (menú "Mapa de Marcajes (Community)", separado del "Marcajes de Asistencia (Community)").

## Qué NO hace este módulo

No sincroniza nada de vuelta hacia Community (salvo la actualización interna que ya se explicó arriba, que nunca sale de Enterprise) — si un marcaje recibido necesita corregirse más allá de eso, se hace acá mismo, directo sobre el mirror.

## Common commands

```
..\..\python\python.exe ..\odoo-bin -c ..\odoo.conf -d <dbname> -u construtec_attendance_sync_19 --stop-after-init
```

See `..\CLAUDE.md` for the disposable-test-DB verification workflow.

## Migración de una instalación existente

Si `construtec_attendance_sync_19` ya estaba instalado dependiendo del núcleo (versión anterior a 2026-09-09), actualizar el módulo (`-u construtec_attendance_sync_19`) NO desinstala `construtec_face_attendance_19`/`hr_attendance` automáticamente — eso hay que hacerlo a mano (Ajustes > Aplicaciones) si ya no hacen falta para nada más en esa base.
