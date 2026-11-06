# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Construtec - Ubicación geográfica de Cuentas Analíticas",
    "summary": "Región y coordenada exacta (con mapa) en la cuenta analítica, sincronizadas "
               "entre Community y Enterprise en ambos sentidos.",
    "version": "19.0.1.1.0",
    "category": "Accounting/Accounting",
    "author": "Alex Martinez",
    "license": "AGPL-3",
    # Mismo módulo en Community y Enterprise (copia exacta). `construtec_account_payment_order_19`
    # aporta las credenciales de sincronización y el cliente JSON-RPC.
    "depends": ["account", "construtec_account_payment_order_19"],
    "data": [
        "security/ir.model.access.csv",
        "views/construtec_region_views.xml",
        "views/account_analytic_account_views.xml",
        "data/geo_sync_cron.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "construtec_analytic_geo_19/static/src/js/geo_map_field.js",
            "construtec_analytic_geo_19/static/src/xml/geo_map_field.xml",
        ],
    },
    "installable": True,
    "application": False,
}
