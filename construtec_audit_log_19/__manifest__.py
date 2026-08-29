{
    'name': 'Construtec Audit Log',
    'version': '19.0.1.0.0',
    'category': 'Tools',
    'summary': 'Bitácora de auditoría configurable (creación/modificación/eliminación) con '
               'retención automática, compatible con Community y Enterprise',
    'description': """
Construtec Audit Log
=====================
Bitácora de auditoría genérica: desde un panel de configuración se elige qué
modelos auditar (creación/modificación/eliminación), sin tocar código, y cada
modelo puede tener su propia retención (días/meses/años) para autoeliminarse
vía tarea planificada.
""",
    'author': 'Construtec Asesores',
    'depends': ['base'],
    'data': [
        'security/audit_log_security.xml',
        'security/ir.model.access.csv',
        'views/audit_log_rule_views.xml',
        'views/audit_log_views.xml',
        'views/menus.xml',
        'data/audit_log_cleanup_cron.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'AGPL-3',
}
