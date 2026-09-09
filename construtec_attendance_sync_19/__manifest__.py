# -*- coding: utf-8 -*-
{
    'name': 'Construtec - Recepción de Marcajes de Asistencia (Community)',
    'version': '19.0.2.0.0',
    'category': 'Human Resources',
    'summary': 'Recibe los marcajes de asistencia empujados desde Odoo19 Community',
    'description': """
Lado receptor, solo Enterprise, del push de marcajes de asistencia que
construtec_face_attendance_19 dispara desde Community (una instalación
"Solicitante"). Enterprise nunca marca asistencia - este módulo es
completamente independiente del núcleo de marcaje (no depende de él ni de
hr_attendance): tiene su propio modelo espejo (create/upsert), su propio
mapa (Leaflet, copiado del de Community) y su propio reporte, con el ticket
resuelto contra el mismo espejo de tickets que ya usa
construtec_ticket_billing_19 para facturación.
""",
    'author': 'Construtec',
    'company': 'Construtec',
    'depends': ['hr', 'analytic', 'construtec_ticket_billing_19'],
    'data': [
        'security/construtec_attendance_sync_security.xml',
        'security/ir.model.access.csv',
        'views/construtec_attendance_mark_mirror_views.xml',
        'views/construtec_attendance_map_wizard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'construtec_attendance_sync_19/static/src/js/attendance_map_action.js',
            'construtec_attendance_sync_19/static/src/xml/attendance_map_action.xml',
        ],
    },
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
