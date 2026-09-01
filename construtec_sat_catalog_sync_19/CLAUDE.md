# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this module is — now deployed in BOTH Community and Enterprise

Originally built as Community-only (the receiving side of the catalog Enterprise builds from imported SAT invoices). Since the "Anticipo Materiales" catalog integration (`construtec_account_payment_order_19`, sección "Catálogo SAT en la Solicitud de Materiales"), this exact module/model also lives in Enterprise (this copy), and in Community (`Odoo19C\server\odoo19c\construtec_sat_catalog_sync_19`, same folder copied verbatim, kept in sync manually) — **same `_name`, same fields, same file layout on both sides**, per explicit user request ("que sea el mismo nombre de modelo... reflejarse en ambos Odoo"). Whatever consumes this catalog (`construtec_account_payment_order_19`'s Materiales tab, or anything else) depends on this module directly, on either edition.

- **En Community**: sigue siendo receptor puro - `construtec.materials.catalog.mirror` se llena SOLO por `sync_from_enterprise()` llamado vía XML-RPC desde Enterprise (`construtec_account_19`). Nada local lo alimenta aquí.
- **En Enterprise (este árbol)**: `sync_from_enterprise()` se llama **localmente, sin red** (misma base de datos), desde `construtec_account_19.sat_product_catalog.py::_sat_sync_to_community()` - ver el CLAUDE.md de ese módulo, sección "Catálogo de Productos de Proveedor". Enterprise nunca depende de Community para tener su propia copia consultable.

Standalone module (`depends: ['base']` only en ambos lados) - deliberadamente **no** depende de `construtec_account_19` ni de `construtec_account_payment_order_19`, para que ninguno de los dos tenga que estar instalado para que este exista - son ellos los que dependen de este módulo, nunca al revés (evita dependencia circular).

## Curaduría por proveedor - por qué no todo el catálogo SAT llega aquí

`res.partner.materiales_catalogo_visible` (Boolean, `models/res_partner.py`, nuevo) es el filtro real contra la basura: `construtec.sat.product.catalog` en Enterprise registra CUALQUIER línea de CUALQUIER factura recibida (combustible, servicios contables, luz, etc.), no solo materiales de construcción - sin este filtro, el catálogo que ve el jefe de técnicos al pedir materiales se llenaría de ruido. Solo un proveedor marcado aquí alimenta este modelo, ni siquiera localmente en Enterprise (mucho menos vía RPC a Community) - ver `_sat_sync_to_community()` en `construtec_account_19` para el guard real. Curar es una decisión de nivel de PROVEEDOR (decenas), no de cada línea de factura (miles) - baja carga de mantenimiento.

**Este campo también existe en Community** (mismo archivo `res_partner.py`, por consistencia de modelo compartido) pero **no tiene ningún efecto ahí** - no hay ningún `construtec.sat.product.catalog` local en Community que filtrar. No confundir "el campo existe" con "el campo hace algo" en esa edición.

## `name_search()` con preferencia por proveedor, nunca restrictivo

Pedido explícito del usuario: al elegir un producto del catálogo desde una línea de materiales, si ya se escribió un proveedor sugerido, el buscador debe **preferir** mostrar primero lo de ese proveedor - pero sin ocultar el resto ("no es como que restringido... sino que pueda meter más productos"). `name_search()` (override, `models/sat_product_catalog_mirror.py`) lee `self.env.context.get('vendor_hint')`: si viene, busca normal (`name`/`codigo` ilike) y reordena para que los resultados con `partner_name` coincidente aparezcan primero - el resto del catálogo sigue ahí, solo después. Sin `vendor_hint` en el contexto, se comporta exactamente como el `name_search` nativo. El consumidor real (`account.payment.order.material.line.catalogo_id`, `construtec_account_payment_order_19`) pasa `context="{'vendor_hint': vendor_name}"` desde la vista, usando el `vendor_name` (Char) que el jefe de técnicos ya escribió en esa misma línea.

Verificado con `odoo-bin shell`: dos entradas de catálogo de proveedores distintos, `name_search` con `vendor_hint` del primero devuelve ambas, con la del proveedor preferido primero; sin `vendor_hint`, orden normal.

## `company_id` nuevo en el modelo

No existía cuando el modelo solo vivía en la Community de una sola compañía. Ahora que también vive en Enterprise (multi-compañía real), hace falta - se agregó al modelo y al payload de `sync_from_enterprise()`. Evolución seria del contrato porque ambos lados (emisor en Enterprise, receptor en ambas ediciones) se desplegaron juntos en la misma pasada - si no llega en `vals` (por ejemplo, una llamada RPC vieja sin el campo), cae en `self.env.company.id` como respaldo, nunca falla por su ausencia.

## Model technical name matches Enterprise's existing call exactly, on purpose

The model here is named `construtec.materials.catalog.mirror` (Python file is still `sat_product_catalog_mirror.py`, module folder is `construtec_sat_catalog_sync_19` - only the Odoo `_name` had to match) - **not** something under a `construtec.sat.*` namespace, even though that would read more consistently with this module's own name. Reason: Enterprise's `_sat_sync_to_community()` (`construtec_account_19/models/sat_product_catalog.py`, already deployed there) calls `execute_kw(..., 'construtec.materials.catalog.mirror', 'sync_from_enterprise', [vals])` (RPC path) or the equivalent local ORM call, with that exact string hardcoded. Matching it here means the sync works with zero changes needed on the caller's side. Do not rename this model without also changing (and redeploying) that caller.

## The contract (as documented in `construtec_account_19`'s CLAUDE.md)

Enterprise calls this in two ways now, same `vals` shape either way (see `_sat_prepare_materials_catalog_vals()` in `construtec_account_19`, the single place that builds it):

- **Local (Enterprise), no red**: `self.env['construtec.materials.catalog.mirror'].sudo().sync_from_enterprise(vals)` - llamada ORM directa, misma base de datos.
- **Remoto (Community)**, XML-RPC estándar de Odoo:
```python
models_proxy.execute_kw(db, uid, api_key, 'construtec.materials.catalog.mirror', 'sync_from_enterprise', [vals])
```
`vals`:
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
}
```

`sync_from_enterprise(vals)` **upserts by `origin_id`** — unlike `helpdesk.material.requisition.mirror` (create-only, each requisition sent exactly once), this catalog changes over time (new price/last-purchase-date on every new invoice for the same product) and Enterprise resends the full row on every change, not just a diff. Deliberately **no `sudo()`** in this method — security here depends entirely on the calling user's own ACL (see below); a `sudo()` would let any authenticated Community user write to this catalog via RPC regardless of their real permissions, defeating the whole point of a minimally-privileged integration user. The Enterprise-local caller wraps the call in its OWN `sudo()` at the call site instead (see `construtec_account_19`'s CLAUDE.md) - the method itself stays sudo-free.

## Security

`group_sat_catalog_sync_integration` gets **read+write+create** (not unlink) on this one model only — read is required here (unlike the materials-requisition mirror's create-only pattern) because `sync_from_enterprise()` must search for an existing `origin_id` before deciding to create vs. update. `base.group_user` gets read-only (so any user can see what's in the catalog, on either edition). Only `base.group_system` can delete, for manual cleanup. This group only matters for the RPC path (Community) - the Enterprise-local caller uses `sudo()` instead, see above.

## Setting this up (once code is deployed on both sides)

1. In Community: create a dedicated user (e.g. "Integración Catálogo SAT"), add it to **only** `group_sat_catalog_sync_integration`, generate an API Key for it (Ajustes > Mi Perfil > Seguridad de la cuenta > Nueva clave API).
2. In Enterprise: Ajustes > Técnico > Parámetros del Sistema, set the 4 keys `construtec_account_19.community_url` / `.community_db` / `.community_login` / `.community_api_key` to point at Community and that integration user. **Not set on any environment as of this writing** — until they are, every remote sync attempt fails cleanly (`sync_state='error'`, descriptive `sync_error`, never blocks the SAT document import itself or the local copy).
3. Trigger a sync from Enterprise (edit any `construtec.sat.product.catalog` entry of a curated proveedor, or run `action_retry_pending_sync_notify` from its menu) and confirm a matching row appears in Community's own "Catálogo de Materiales" menu.

## Status as of this writing (2026-09-01)

**Verificado con `odoo-bin shell` contra `construtec_test` (Enterprise), incluyendo el navegador real**: la curaduría por proveedor (entrada de proveedor NO curado → `sync_state='no_aplica'`, sin espejo local; curar tarde → re-sincroniza retroactivamente todo lo histórico de ese proveedor), la copia local en Enterprise (sin red, `company_id` incluido), el `name_search` con preferencia por proveedor (preferido primero, el resto sigue visible), y el autocompletado real en la pestaña Materiales de `construtec_account_payment_order_19` (elegir una entrada del catálogo llena Material/Proveedor Sugerido/Precio Estimado y recalcula los totales) — todo funcionando de punta a punta en un solo Odoo (Enterprise).

**Lo que sigue sin poder probarse localmente, sin cambios respecto a antes**: el salto RPC real Enterprise→Community por red - Community y Enterprise comparten el mismo puerto/`data_dir` por defecto localmente y no corren a la vez en este entorno de desarrollo, y los 4 parámetros de sistema en Enterprise siguen sin configurarse en ningún ambiente real. Verificado que el intento de sync remoto falla limpio con el mensaje esperado (`sync_state='error'`, `sync_error` describiendo los parámetros faltantes) cuando no están configurados - comportamiento correcto, no un bug.
