# -*- coding: utf-8 -*-
{
    'name': 'Construtec - Reconocimiento Facial en Asistencia',
    'version': '19.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Verifica el rostro del empleado (server-side, sin servicios de IA de terceros) antes de marcar asistencia',
    'description': """
Reconocimiento facial para Asistencia (Construtec)
====================================================
El empleado inicia sesión en Odoo, abre el widget de Asistencia (el mismo
"Check in / Check out" de la barra superior) y, antes de que se registre el
fichaje, debe mostrar su rostro a la cámara de su propio dispositivo.

* La comparación facial corre 100%% en el navegador (face-api.js /
  TensorFlow.js, modelos incluidos en este módulo) — sin tokens, sin cuentas,
  sin llamadas a ningún servicio de IA externo.
* El navegador solo envía al servidor la huella facial (128 números), nunca
  decide por sí solo: el servidor vuelve a comparar esa huella contra las 3
  fotos de referencia del empleado (frente/izquierda/derecha) y recién ahí
  habilita, por un token de sesión de un solo uso, la llamada real que marca
  la asistencia — así no se puede saltear la cámara llamando la ruta directo.
* Ubicación y hora ya las captura el propio `hr_attendance` de Odoo.
* Enrolamiento (carga de las 3 fotos de referencia) reservado a
  Administrador (RRHH), desde la ficha del empleado.
* Módulo de Community: acá es donde el colaborador realmente marca
  asistencia (cámara, ubicación, reporte, mapa). El vínculo opcional a un
  ticket de `construtec_helpdesk_mgmt` vive en el módulo aparte
  `construtec_face_attendance_helpdesk_19` (solo Community).
* Los marcajes se sincronizan hacia Enterprise (push, solo lectura del otro
  lado) - ver `construtec_attendance_sync_19`, que es 100% independiente de
  este módulo (no lo instala ni depende de `hr_attendance`).
""",
    'author': 'Construtec',
    'company': 'Construtec',
    'depends': ['hr_attendance', 'mail', 'analytic', 'construtec_account_payment_order_19'],
    'data': [
        'security/ir.model.access.csv',
        'data/attendance_mark_sync_cron.xml',
        'views/hr_employee_views.xml',
        'views/construtec_attendance_mark_views.xml',
        'views/construtec_attendance_map_wizard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'construtec_face_attendance_19/static/src/js/face_api_loader.js',
            'construtec_face_attendance_19/static/src/js/face_capture_field.js',
            'construtec_face_attendance_19/static/src/xml/face_capture_field.xml',
            'construtec_face_attendance_19/static/src/js/attendance_menu_patch.js',
            'construtec_face_attendance_19/static/src/xml/attendance_menu_patch.xml',
            'construtec_face_attendance_19/static/src/js/attendance_map_action.js',
            'construtec_face_attendance_19/static/src/xml/attendance_map_action.xml',
        ],
    },
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
