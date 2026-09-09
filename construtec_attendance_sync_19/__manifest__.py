# -*- coding: utf-8 -*-
{
    'name': 'Construtec - Recepción de Marcajes de Asistencia (Community)',
    'version': '19.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Recibe los marcajes de asistencia empujados desde Odoo19 Community',
    'description': """
Lado receptor, solo Enterprise, del push de marcajes de asistencia que
construtec_face_attendance_19 dispara desde una instalación "Solicitante"
(Community). Modelo espejo create-only (un marcaje es un evento, no algo que
se edite después - mismo patrón que helpdesk.material.requisition.mirror),
más una extensión del mapa de marcajes del propio núcleo para que también
se vean ahí los marcajes recibidos de Community, junto a los propios de
Enterprise.
""",
    'author': 'Construtec',
    'company': 'Construtec',
    'depends': ['construtec_face_attendance_19'],
    'data': [
        'security/construtec_attendance_sync_security.xml',
        'security/ir.model.access.csv',
        'views/construtec_attendance_mark_mirror_views.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
