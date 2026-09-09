# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this module is

Lado receptor, **solo Enterprise**, del push de marcajes de asistencia que `construtec_face_attendance_19` (el núcleo, instalable en ambas ediciones) dispara desde una instalación "Solicitante" (Community, `res.company.payment_order_role == 'solicitante'`). `depends: ['construtec_face_attendance_19']` únicamente — no depende de `construtec_account_payment_order_19` directamente (el lado que RECIBE nunca necesita el helper de JSON-RPC ni los campos de configuración de sync, solo el modelo/vistas del núcleo que extiende).

## Modelo: `construtec.attendance.mark.mirror` — create-only, igual que `helpdesk.material.requisition.mirror`

Un marcaje es un evento que nunca cambia después de creado (a diferencia de `construtec.helpdesk.ticket.mirror`, que hace upsert por número porque un ticket SÍ cambia de estado con el tiempo) — por eso este mirror es **create-only puro**: `sync_from_community(vals)` busca primero por `source_record_id` (el id del marcaje en Community, nunca tratado como relación real — solo como llave de idempotencia, mismo criterio "nunca ids entre bases" de todo el proyecto) y si ya existe simplemente devuelve ese id sin crear un duplicado; si no, lo crea.

`employee_id` (Many2one real a `hr.employee`) se resuelve por `employee_enterprise_ref` — el mismo id que `hr.employee.enterprise_employee_ref` ya guarda en Community para el pull de catálogo de empleados (`construtec_account_payment_order_19`). `employee_name` (Char) es el respaldo de texto siempre presente, por si ese id no resuelve (empleado no sincronizado, o de una compañía distinta). `analytic_account_id` se resuelve igual, vía `analytic_enterprise_ref` (mismo mecanismo que `account.analytic.account.enterprise_analytic_ref`).

**Sin `sudo()`** en `sync_from_community()` — las reglas de permisos del propio usuario de integración son las que de verdad gatean esto (mismo criterio que `construtec.helpdesk.ticket.mirror`).

## Seguridad

`group_construtec_attendance_sync_integration` — grupo nuevo, dedicado, con **lectura + creación** sobre este modelo (`security/ir.model.access.csv`), nada más. Se prefirió un grupo dedicado en vez de reutilizar uno existente (a diferencia de `construtec_ticket_billing_19`, que reutilizó `account.group_account_manager` a pedido explícito del usuario en esa ocasión) — sigue el patrón mayoritario de este proyecto (`construtec_materials_sync_19`, `construtec_sat_catalog_sync_19`, `construtec_whatsapp_19`: cada integración con su propio grupo mínimo, defensa en profundidad). **No agregar `base.group_user` ni ningún otro grupo al usuario de integración**.

**Bug real encontrado verificando esto de punta a punta (no solo con `odoo-bin shell`, con un push HTTP real entre dos instancias locales)**: el diseño original de este grupo era **solo creación** (`perm_read=0`), calcando el criterio de `construtec_materials_sync_19`/`construtec_sat_catalog_sync_19`. Un `create()` directo probado con `with_user()` funcionaba perfecto, pero el push REAL vía `/jsonrpc` (`execute_kw`) fallaba con `AccessError` incluso con `sync_from_community()` usando `sudo()` en sus lecturas internas (la búsqueda de deduplicación por `source_record_id`, la resolución de `employee_id`/`analytic_account_id`). Causa real: Odoo exige que el usuario que llama a `execute_kw` tenga al menos **permiso de lectura** sobre el modelo para poder invocar **cualquier** método sobre él — incluido un método propio que nunca devuelve datos de lectura al llamador — porque el framework no puede saber de antemano qué hace un método arbitrario. Esta exigencia es un chequeo ANTERIOR a que el método siquiera empiece a ejecutarse, así que ningún `sudo()` interno lo evita. **Por eso el grupo terminó con `perm_read=1`** — la alternativa (llamar directo al `create()` estándar en vez de un método propio) habría evitado el problema, pero mover la lógica de deduplicación/resolución al `create()` override del modelo mismo era más cambio de diseño del que ameritaba esta corrección puntual.

`hr.group_hr_manager` (el mismo grupo que ya gatea todo lo sensible en el núcleo) tiene lectura sobre el mirror, para poder revisarlo desde el menú "Marcajes de Asistencia (Community)" (`hr.menu_hr_root`).

## Mapa consolidado: extiende el del núcleo, sin que el núcleo sepa de este módulo

`controllers/main.py` — misma convención de "controller inheritance" ya documentada en `construtec_face_attendance_helpdesk_19` (heredar con el MISMO nombre de clase). Sobreescribe `map_data` (mismo `@http.route()` bare que ya usa `systray_attendance` en el núcleo para este caso — "misma ruta, sin params nuevos, solo redefinir el cuerpo"): llama a `super()` (que ya valida `hr.group_hr_manager` y arma los puntos propios de Enterprise) y le agrega, como pines adicionales, los `construtec.attendance.mark.mirror` que calcen con el mismo filtro de fecha/empleado/ubicación-real — así el mapa de Enterprise muestra en un solo lugar tanto sus propios marcajes como los recibidos de Community, sin que `construtec_face_attendance_19` necesite saber que este módulo existe.

Los `id`/`employee_id` de los puntos del mirror se prefijan/marcan como `'mirror-<id>'` cuando no hay un `employee_id` real resuelto (para no colisionar con los ids reales del núcleo, que son enteros) y el nombre del empleado se sufija con " (Community)" para distinguir el origen a simple vista en el popup del mapa.

## Qué NO hace este módulo

No sincroniza nada de vuelta hacia Community (mismo criterio que el resto de syncs de este proyecto salvo el pull explícito de estado de Órdenes de Pago) — si un marcaje recibido necesita corregirse, se hace aquí mismo en Enterprise, directo sobre el mirror (de solo lectura para `hr.group_hr_manager` en la vista, pero no hay ninguna restricción de modelo que lo impida a nivel de shell/script si hiciera falta).

## Common commands

```
..\..\python\python.exe ..\odoo-bin -c ..\odoo.conf -d <dbname> -u construtec_attendance_sync_19 --stop-after-init
```

See `..\CLAUDE.md` for the disposable-test-DB verification workflow.
