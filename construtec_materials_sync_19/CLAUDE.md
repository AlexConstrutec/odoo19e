# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this module is

`construtec_materials_sync_19` is the **receiving side** of a one-way integration: when a Jefe submits a "Solicitud de Materiales" in Odoo19C (Community, module `construtec_materials_19`), Community pushes a read-only mirror of it here via Odoo's own built-in `/jsonrpc` API — no custom controller/webhook needed on this side, since every Odoo install already exposes that endpoint. `depends: ["base"]` only; this module is fully standalone.

## Why a separate mirror model, not a real business object

Community and Enterprise are **separate databases** with unrelated primary keys — a `product_id`/`partner_id` in one means nothing in the other. `helpdesk.material.requisition.mirror` (+ `.mirror.line`) therefore stores everything as **plain text** (`product_name`, `vendor_name`, etc.), not `Many2one`s. This is deliberately a one-way audit trail ("solo un registro espejo/resumen", per the scope Alex confirmed), not an attempt to recreate the requisition as a live Enterprise business document (no `purchase.order` is created here). See memory `construtec-ticketing-roadmap` for the decision context.

## Security: the integration user must be minimally privileged

`security/materials_sync_security.xml` defines `group_materials_sync_integration` — grant this (and *nothing else*) to whatever Enterprise user's API Key gets configured on the Community side (`res.company.enterprise_sync_login`/`enterprise_sync_api_key` in `construtec_materials_19`). Per `security/ir.model.access.csv`, that group has **create-only** access to both models — no read, write, or unlink. This is intentional defense-in-depth: if the API Key ever leaks, the worst case is someone can insert junk mirror records, never read or tamper with real data. Regular internal staff (`base.group_user`) get read-only; only `base.group_system` can delete (for cleanup).

**Do not** grant the integration user `base.group_user` or any broader group "to make things easier" — that would defeat the whole point of the dedicated low-privilege group.

## Setting up a new integration user (do this once per environment)

1. In Enterprise: create a dedicated user (e.g. "Integración Community"), not tied to a real employee/administrator.
2. Add that user to **only** `group_materials_sync_integration` (Ajustes > Usuarios y Compañías > Usuarios > pestaña *Access Rights*).
3. As that user (or as an admin editing that user's profile): Ajustes > Mi Perfil > Seguridad de la cuenta > **Nueva clave API** — copy the generated key immediately (Odoo shows it once).
4. On the **Community** side, fill in Ajustes > Helpdesk > *Sincronización con Enterprise*: URL, base de datos, ese usuario, y la API Key. Use "Probar conexión" there before relying on it.

## Gotcha: both editions currently can't run at once

Per the top-level `C:\Users\Alex\Documents\Proyectos\CLAUDE.md`, Odoo19C and Odoo19E share the same default port (8069) and `data_dir` — only one runs at a time without reconfiguring `odoo.conf` in one of them. To actually exercise this integration end-to-end locally, run Enterprise on a different port (`http_port` in its `odoo.conf`) while Community runs on the default, and point `enterprise_sync_url` at that alternate port.

## Reviewing received requests

Ajustes-independent menu **"Materiales (Sync)" > "Solicitudes Recibidas"** (top-level, not nested under Settings) shows every mirror received, newest first (`_order = "create_date desc"`). Nothing here is editable (`create="0" edit="0"` on the views, matching the ACL) — it's meant purely for visibility into what Community has sent, not a place to act on it directly.
