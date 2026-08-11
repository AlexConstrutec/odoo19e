# -*- coding: utf-8 -*-
{
    "name": "Construtec - Recepción de Solicitudes de Materiales (Community)",
    "version": "19.0.1.0.0",
    "category": "Inventory/Purchase",
    "summary": "Recibe, vía API, un espejo de solo lectura de las Solicitudes de "
    "Materiales enviadas desde el Odoo Community (Helpdesk).",
    "author": "Alex Martinez",
    "website": "https://www.construtecasesores.com",
    "license": "AGPL-3",
    "depends": ["base"],
    "data": [
        "security/materials_sync_security.xml",
        "security/ir.model.access.csv",
        "views/material_requisition_mirror_views.xml",
    ],
    "installable": True,
    "application": False,
}
