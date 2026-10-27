# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Construtec - Materiales desde Bodega (Enterprise)",
    "version": "19.0.1.0.0",
    "category": "Inventory/Inventory",
    "summary": "Solicitudes de Materiales: Compras revisa la existencia en bodega, traslada lo que hay "
    "y compra solo el faltante.",
    "author": "Alex Martinez",
    "website": "https://www.construtecasesores.com",
    "license": "AGPL-3",
    "depends": ["construtec_account_payment_order_19", "purchase_stock"],
    "data": [
        "views/account_payment_order_views.xml",
    ],
    "installable": True,
    "application": False,
}
