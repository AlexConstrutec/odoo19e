# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Construtec - Solicitud de Libro Mayor desde el Portal",
    "summary": "El contador externo (usuario portal) solicita el Libro Mayor de una empresa y rango de fechas; "
               "le llega por correo en Excel. Sin acceso al backend.",
    "version": "19.0.1.0.2",
    "license": "AGPL-3",
    "category": "Accounting",
    "author": "Alex Martinez",
    "website": "https://www.linkedin.com/in/baterodedios/",
    "depends": ["portal", "mail", "account_reports"],
    "data": [
        "security/ir.model.access.csv",
        "security/security.xml",
        "data/ir_cron.xml",
        "data/ir_config_parameter.xml",
        "views/ledger_request_views.xml",
        "views/res_users_views.xml",
        "views/portal_templates.xml",
    ],
    "installable": True,
    "application": False,
}
