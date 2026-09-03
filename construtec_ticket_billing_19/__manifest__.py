# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Construtec - Facturación de Tickets (Community)",
    "version": "19.0.1.0.0",
    "category": "Accounting/Accounting",
    "summary": "Recibe, vía API, un espejo de los Tickets de Helpdesk enviados desde Odoo "
    "Community, y permite vincularlos a una Factura real para reflejar su costo/estado "
    "de facturación (Sin Facturar/Facturado/Cobrado).",
    "author": "Alex Martinez",
    "website": "https://www.construtecasesores.com",
    "license": "AGPL-3",
    "depends": ["account"],
    "data": [
        "security/ticket_billing_security.xml",
        "security/ir.model.access.csv",
        "views/construtec_helpdesk_ticket_mirror_views.xml",
        "views/account_move_views.xml",
    ],
    "installable": True,
    "application": False,
}
