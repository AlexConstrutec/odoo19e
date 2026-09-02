# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this module is — now deployed in BOTH Community and Enterprise

Originally built as Community-only (the receiving side of the catalog Enterprise builds from imported SAT invoices). Since the "Anticipo Materiales" catalog integration (`construtec_account_payment_order_19`, sección "Catálogo SAT en la Solicitud de Materiales"), this exact module/model also lives in Enterprise (this copy), and in Community (`Odoo19C\server\odoo19c\construtec_sat_catalog_sync_19`, same folder copied verbatim, kept in sync manually) — **same `_name`, same fields, same file layout on both sides**, per explicit user request ("que sea el mismo nombre de modelo... reflejarse en ambos Odoo"). Whatever consumes this catalog (`construtec_account_payment_order_19`'s Materiales tab, or anything else) depends on this module directly, on either edition.

- **En Community**: sigue siendo receptor puro - `construtec.materials.catalog.mirror` se llena vía `sync_from_enterprise()`, ahora llamado **localmente en Community** (no por RPC entrante) desde su propio pull (`res_company.py::_sync_materials_catalog_from_enterprise()`, ver más abajo).
- **En Enterprise (este árbol)**: `sync_from_enterprise()` se llama **localmente, sin red** (misma base de datos), desde `construtec_account_19.sat_product_catalog.py::_sat_sync_local_mirror()` - ver el CLAUDE.md de ese módulo, sección "Catálogo de Productos de Proveedor". Enterprise nunca depende de Community para tener su propia copia consultable.

Standalone module (`depends: ['base']` only en ambos lados) - deliberadamente **no** depende de `construtec_account_19` ni de `construtec_account_payment_order_19`, para que ninguno de los dos tenga que estar instalado para que este exista - son ellos los que dependen de este módulo, nunca al revés (evita dependencia circular).

## Sincronización Community↔Enterprise: PULL, no push (cambio de diseño, 2026-09-01)

**Reemplaza el diseño original de esta sección** (Enterprise empujando por XML-RPC hacia Community en cada cambio del catálogo). Pedido explícito del usuario, comparando contra el patrón ya usado en `construtec_account_payment_order_19` para empleados/cuentas analíticas: *"¿no sería mejor que Community jale la información de Enterprise? Así lo hace con contactos."* Correcto y más consistente - empleados, cuentas analíticas y el estado de las Órdenes de Pago ya se jalan desde Community; el catálogo era la única pieza que empujaba en sentido contrario.

- **`tools/enterprise_sync_api.py`** (nuevo, en ambas copias) - copia deliberada del mismo patrón JSON-RPC ya usado en `construtec_account_payment_order_19/tools/enterprise_sync_api.py` (no una dependencia compartida - mismo criterio de "cada integración con sus propias credenciales", ver el CLAUDE.md de ese módulo). `fetch_materials_catalog()` hace `search_read` directo sobre la copia LOCAL de Enterprise de este mismo modelo (`construtec.materials.catalog.mirror`) - no sobre `construtec.sat.product.catalog` (el modelo de origen real, con campos relacionales) - porque Enterprise YA mantiene su propio espejo plano (mismo `_name`, mismos campos texto) vía `_sat_sync_local_mirror()`; leerlo directamente evita cualquier conversión de campos relacionales (`partner_id`→texto, etc.) del lado Community, que ya viene resuelta.
- **`res.company` (nuevo `models/res_company.py`, este módulo)**: 4 campos de conexión (`materials_catalog_sync_url`/`_db`/`_login`/`_api_key`) + `materials_catalog_sync_enabled` + intervalo configurable, **independientes** de los campos homónimos de `construtec_account_payment_order_19` (`payment_order_sync_*`) - aunque en la práctica apunten al mismo servidor Enterprise, son credenciales/configuración separadas a propósito: este módulo es deliberadamente standalone (`depends: ['base']`) y no puede depender de ese otro módulo sin crear una dependencia circular (ese módulo YA depende de este). Quien configure esto tendrá que capturar la misma URL/usuario/API Key una segunda vez, en una sección de Ajustes distinta - trade-off aceptado a cambio de no acoplar los dos módulos.
- **No hay una pantalla de Ajustes/Configuración dedicada** (como sí tiene `construtec_account_payment_order_19`, que cuelga de Ajustes > Facturación porque depende de `account`) - los 4 campos de conexión + intervalo + botón "Sincronizar Ahora" viven directo en la ficha de la Compañía (`base.view_company_form`, pestaña nueva "Catálogo de Materiales (Sync)") vía `views/res_company_views.xml` - el único lugar disponible sin agregar una dependencia nueva solo para tener una pantalla de Ajustes.
- **`_sync_materials_catalog_from_enterprise()`**: pull + upsert reutilizando el `sync_from_enterprise()` YA existente en este mismo modelo - antes ese método solo se llamaba desde una llamada RPC ENTRANTE (Enterprise empujando); ahora se llama LOCALMENTE en Community, con lo que se acaba de traer del `search_read`. Upsert por `origin_id` (el id de la entrada en `construtec.sat.product.catalog`, Enterprise) - mismo contrato de siempre, `sync_from_enterprise()` no cambió. Deliberadamente **no se reenvía `company_id`** de Enterprise (un id de compañía de otra base no significa nada aquí) - `sync_from_enterprise()` ya cae en `self.env.company.id` cuando falta, verificado que resuelve a la compañía activa de Community, no a ningún id cruzado.
- **Cron nuevo** (`data/ir_cron_materials_catalog_sync.xml`, cada 1 hora por defecto, mismo patrón/limitación de "un cron global, no por compañía" que el resto de los cron de sincronización de este proyecto) + botón manual "Sincronizar Ahora" en la ficha de Compañía.
- **`construtec_account_19` (Enterprise) simplificado**: `_sat_sync_to_community()` se renombró a `_sat_sync_local_mirror()` y perdió por completo el bloque XML-RPC saliente (los 4 Parámetros del Sistema `construtec_account_19.community_*`, las clases `_TimeoutTransport`/`_TimeoutSafeTransport`, el `xmlrpc.client.ServerProxy`) - ahora solo hace el upsert local (siempre lo hizo, sin cambios ahí). `sync_state`/`sync_error`/`sync_date` en `construtec.sat.product.catalog` (Enterprise) ahora reflejan solo esa copia local - ver el CLAUDE.md de ese módulo.
- **Verificado con `odoo-bin shell` en `construtec_test`** (2026-09-01): `-u` limpio de los 3 módulos (tras limpiar una vista huérfana preexistente, no relacionada con este cambio); sincronización deshabilitada por defecto (no-op limpio); habilitada sin credenciales falla limpio (`EnterpriseSyncError` capturado); la copia local de Enterprise (`_sat_sync_local_mirror()`) sigue funcionando igual que siempre; un pull simulado (mock de `fetch_materials_catalog()`) con una entrada Bien y una Servicio crea ambos espejos correctamente en Community, con `company_id` resolviendo a la compañía activa de Community (no a ningún id de Enterprise), y una segunda corrida con los mismos datos actualiza en vez de duplicar (upsert real, no create ciego).

## Qué llega aquí - se sincroniza TODO, el filtro vive en cada consumidor

Este modelo (`construtec.materials.catalog.mirror`) no filtra nada por sí mismo - recibe TODO lo que Enterprise sincroniza, bienes y servicios por igual, sin ningún gate en el origen (`construtec_account_19`, `_sat_sync_to_community()`). Decisión explícita del usuario, en dos pasadas: primero se descartó una curaduría manual por proveedor (`res.partner.materiales_catalogo_visible`); después, al construirse un filtro automático por `bien_o_servicio` en el origen, también se descartó eso - "se van a sincronizar todos los productos... en un futuro voy a necesitar los productos de tipo servicio también" (una sección futura, todavía no construida, va a consumir este mismo catálogo para Servicios).

- **`bien_o_servicio`** (Selection `B`/`S`, campo nuevo en este modelo) viaja en cada entrada, copiado de `construtec.sat.product.catalog.bien_o_servicio` (Enterprise) - dato real del propio Documento SAT, nunca recalculado aquí.
- **El filtro real vive en cada consumidor**, vía `domain=` sobre el campo Many2one que apunta a este modelo - hoy solo existe un consumidor: `account.payment.order.material.line.catalogo_id` (`construtec_account_payment_order_19`), con `domain="[('bien_o_servicio', '=', 'B')]"` porque la Solicitud de Materiales solo necesita Bienes. Un futuro consumidor de Servicios haría lo mismo con `'S'`, sin tocar nada de este módulo ni de la sincronización.

## `name_search()` con preferencia por proveedor, nunca restrictivo

Pedido explícito del usuario: al elegir un producto del catálogo desde una línea de materiales, si ya se escribió un proveedor sugerido, el buscador debe **preferir** mostrar primero lo de ese proveedor - pero sin ocultar el resto ("no es como que restringido... sino que pueda meter más productos"). `name_search()` (override, `models/sat_product_catalog_mirror.py`) lee `self.env.context.get('vendor_hint')`: si viene, busca normal (`name`/`codigo` ilike) y reordena para que los resultados con `partner_name` coincidente aparezcan primero - el resto del catálogo sigue ahí, solo después. Sin `vendor_hint` en el contexto, se comporta exactamente como el `name_search` nativo. El consumidor real (`account.payment.order.material.line.catalogo_id`, `construtec_account_payment_order_19`) pasa `context="{'vendor_hint': vendor_name}"` desde la vista, usando el `vendor_name` (Char) que el jefe de técnicos ya escribió en esa misma línea.

Verificado con `odoo-bin shell`: dos entradas de catálogo de proveedores distintos, `name_search` con `vendor_hint` del primero devuelve ambas, con la del proveedor preferido primero; sin `vendor_hint`, orden normal.

**Bug real encontrado en producción (Community, `erp.construtecasesores.com`, 2026-09-01)**: el override llamaba a `super().name_search(name=name, args=args, ...)` - Odoo 19 renombró ese parámetro de `args` a **`domain`** (`BaseModel.name_search()`, `..\odoo\orm\models.py`), así que la llamada tronaba con `TypeError: BaseModel.name_search() got an unexpected keyword argument 'args'` en cuanto el picker de `catalogo_id` se abría **sin** `vendor_hint` en el contexto (la rama que llama a `super()`). No se detectó localmente porque las pruebas por `odoo-bin shell` de este mismo archivo probaron ambos casos, pero aparentemente ninguna pasada real ejercitó la rama sin `vendor_hint` contra el `super()` real de un servidor vivo. **Fix**: el parámetro propio del método y la llamada a `super()` ahora usan `domain=`, no `args=`.

## `company_id` nuevo en el modelo

No existía cuando el modelo solo vivía en la Community de una sola compañía. Ahora que también vive en Enterprise (multi-compañía real), hace falta - se agregó al modelo y al payload de `sync_from_enterprise()`. Evolución seria del contrato porque ambos lados (emisor en Enterprise, receptor en ambas ediciones) se desplegaron juntos en la misma pasada - si no llega en `vals` (por ejemplo, una llamada RPC vieja sin el campo), cae en `self.env.company.id` como respaldo, nunca falla por su ausencia.

## Model technical name matches Enterprise's existing call exactly, on purpose

The model here is named `construtec.materials.catalog.mirror` (Python file is still `sat_product_catalog_mirror.py`, module folder is `construtec_sat_catalog_sync_19` - only the Odoo `_name` had to match) - **not** something under a `construtec.sat.*` namespace, even though that would read more consistently with this module's own name. Reason: Enterprise's `_sat_sync_to_community()` (`construtec_account_19/models/sat_product_catalog.py`, already deployed there) calls `execute_kw(..., 'construtec.materials.catalog.mirror', 'sync_from_enterprise', [vals])` (RPC path) or the equivalent local ORM call, with that exact string hardcoded. Matching it here means the sync works with zero changes needed on the caller's side. Do not rename this model without also changing (and redeploying) that caller.

## The contract (as documented in `construtec_account_19`'s CLAUDE.md)

`sync_from_enterprise()` se llama **localmente en ambos lados** (nunca por RPC entrante desde ahora - ver "Sincronización Community↔Enterprise: PULL, no push" arriba):

- **Enterprise**: `self.env['construtec.materials.catalog.mirror'].sudo().sync_from_enterprise(vals)` - llamada ORM directa, misma base de datos, con `vals` armado por `_sat_prepare_materials_catalog_vals()` (`construtec_account_19`).
- **Community**: también una llamada ORM directa, local - pero el `vals` para cada entrada viene de un `search_read` remoto propio (`tools/enterprise_sync_api.fetch_materials_catalog()`) sobre la copia local de Enterprise de este mismo modelo, no de una llamada que Enterprise inicia.

`vals` (mismo shape en ambos lados):
```python
{
    'origin_id': <int, the record's own id in Enterprise - the upsert key>,
    'name': <str>,
    'codigo': <str or False>,
    'partner_name': <str, plain text - NOT a res.partner id>,
    'partner_vat': <str or False>,
    'uom_name': <str or False>,
    'currency_name': <str>,
    'precio_referencia': <float>,
    'primera_fecha_compra': <'YYYY-MM-DD' str or False>,
    'ultima_fecha_compra': <'YYYY-MM-DD' str or False>,
    'company_id': <int, id de compañía - nuevo, ver sección de arriba>,
    'bien_o_servicio': <'B'/'S' str or False - ver "Qué llega aquí" arriba, nunca filtra el envío>,
}
```

`sync_from_enterprise(vals)` **upserts by `origin_id`** — unlike `helpdesk.material.requisition.mirror` (create-only, each requisition sent exactly once), this catalog changes over time (new price/last-purchase-date on every new invoice for the same product) and Enterprise resends the full row on every change, not just a diff. Deliberately **no `sudo()`** in this method — security here depends entirely on the calling user's own ACL (see below); a `sudo()` would let any authenticated Community user write to this catalog via RPC regardless of their real permissions, defeating the whole point of a minimally-privileged integration user. The Enterprise-local caller wraps the call in its OWN `sudo()` at the call site instead (see `construtec_account_19`'s CLAUDE.md) - the method itself stays sudo-free.

## Security

`group_sat_catalog_sync_integration` gets **read+write+create** (not unlink) on this one model only — read is required here (unlike the materials-requisition mirror's create-only pattern) because `sync_from_enterprise()` must search for an existing `origin_id` before deciding to create vs. update. `base.group_user` gets read-only (so any user can see what's in the catalog, on either edition). Only `base.group_system` can delete, for manual cleanup.

**Nota tras el cambio a pull (2026-09-01)**: este grupo quedó sin uso real en la práctica - ambos lados ahora llaman `sync_from_enterprise()` localmente con `sudo()` (Enterprise desde `_sat_sync_local_mirror()`, Community desde `res_company.py::_sync_materials_catalog_from_enterprise()`), nunca vía una llamada RPC entrante que dependa de este grupo. Se deja el grupo/permiso tal cual (no se eliminó) - sigue siendo el camino correcto si en el futuro alguien más necesita escribir en este modelo vía RPC con un usuario de permisos acotados.

## Setting this up (once code is deployed on both sides) — PULL, no push (ver sección de arriba)

1. En Enterprise: generar una API Key para cualquier usuario autenticado (Ajustes > Mi Perfil > Seguridad de la cuenta > Nueva clave API) - `base.group_user` ya tiene lectura sobre `construtec.materials.catalog.mirror` (security/ir.model.access.csv, este módulo), no hace falta ningún grupo/usuario de integración dedicado del lado Enterprise para esto.
2. En Community: Ajustes > Compañías > [tu compañía] > pestaña **"Catálogo de Materiales (Sync)"** - marcar "Sincronización... Habilitada" y capturar la URL/base de datos/usuario/API Key de Enterprise (paso 1). **No configurado en ningún ambiente real todavía** - hasta que se configure, cada intento falla limpio (`EnterpriseSyncError` capturado, notificación de error, nunca bloquea nada más).
3. Disparar la sincronización con el botón **"Sincronizar Ahora"** en esa misma pestaña, o esperar el cron horario (`ir_cron_materials_catalog_sync`) - confirmar que aparecen entradas en el propio menú "Catálogo de Materiales" de Community.

## Status as of this writing (2026-09-01)

**Verificado con `odoo-bin shell` contra `construtec_test` (Enterprise), incluyendo el navegador real**: se sincroniza tanto una entrada tipo Bien como una tipo Servicio (ambas generan espejo local, `bien_o_servicio` viaja correctamente), la copia local en Enterprise (sin red, `company_id` incluido), el `name_search` con preferencia por proveedor (preferido primero, el resto sigue visible), y el autocompletado real en la pestaña Materiales de `construtec_account_payment_order_19` (elegir una entrada del catálogo llena Material/Proveedor Sugerido/Precio Estimado y recalcula los totales, y el picker de esa línea solo ofrece Bienes por su propio `domain=`) — todo funcionando de punta a punta en un solo Odoo (Enterprise).

**Lo que sigue sin poder probarse localmente, sin cambios respecto a antes**: el salto RPC real Enterprise→Community por red - Community y Enterprise comparten el mismo puerto/`data_dir` por defecto localmente y no corren a la vez en este entorno de desarrollo, y los 4 parámetros de sistema en Enterprise siguen sin configurarse en ningún ambiente real. Verificado que el intento de sync remoto falla limpio con el mensaje esperado (`sync_state='error'`, `sync_error` describiendo los parámetros faltantes) cuando no están configurados - comportamiento correcto, no un bug.
