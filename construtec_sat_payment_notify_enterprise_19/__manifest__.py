# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Construtec - Aviso de Pagos a Proveedores por WhatsApp (lado Enterprise)",
    "summary": "Casilla 'Avisar al proveedor por WhatsApp' en Registrar pago y cola para que "
               "Community (construtec_sat_payment_notify_19) mande el aviso por WhatsApp Alterno",
    "version": "19.0.1.0.0",
    "license": "AGPL-3",
    "category": "Accounting",
    "author": "Alex Martinez",
    "website": "https://www.linkedin.com/in/baterodedios/",
    "depends": ["account", "construtec_account_19"],
    "data": [
        "views/account_payment_register_views.xml",
        "views/account_payment_views.xml",
    ],
    "installable": True,
    "application": False,
}
