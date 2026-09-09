# -*- coding: utf-8 -*-
import logging
import time
from datetime import timedelta

from odoo import fields, http, _
from odoo.exceptions import UserError
from odoo.http import request
from odoo.tools import file_path
from odoo.addons.hr_attendance.controllers.main import HrAttendance
from odoo.addons.web.controllers.webmanifest import WebManifest

_logger = logging.getLogger(__name__)

# Distancia máxima (euclidiana) entre la huella de la cámara y una huella de
# referencia para considerarlas la misma persona. face-api.js documenta 0.6
# como umbral típico; acá se usa uno más estricto porque, además, se compara
# contra 3 fotos de referencia y se toma la MEJOR (menor distancia) de las 3
# — eso le da a un impostor 3 oportunidades de "acercarse" a alguna, no 1,
# así que el umbral tiene que compensar siendo más chico. Bajado de 0.5 a
# 0.42 el 2026-09-08 tras un falso positivo confirmado en pruebas reales
# (otro rostro distinto fue aceptado) - si sigue pasando, el siguiente paso
# es exigir coincidencia con más de una referencia a la vez, no solo la mejor.
MATCH_THRESHOLD = 0.42

# Token de verificación facial: de un solo uso y de vida corta, guardado en la
# sesión del propio usuario. Se exige antes de aceptar cualquier marcaje real,
# para que nadie pueda saltarse la cámara llamando la ruta directo.
SESSION_FACE_TS = 'construtec_face_verified_ts'
SESSION_FACE_UID = 'construtec_face_verified_uid'
FACE_VERIFY_TTL = 60  # segundos

MARK_TYPES = (
    'inicio_labores',
    'inicio_alimentacion',
    'fin_alimentacion',
    'fin_labores',
)

# Textos fijos (sin traducción perezosa: este módulo es español-only, y
# _() a nivel de módulo dispara advertencias porque no hay contexto de
# idioma en tiempo de import).
MARK_TYPE_LABELS = {
    'inicio_labores': 'Inicio de Labores / Hora Extra',
    'inicio_alimentacion': 'Inicio de Alimentación',
    'fin_alimentacion': 'Fin de Alimentación',
    'fin_labores': 'Fin de Labores / Hora Extra',
}

# Cada uno de los 4 botones tiene su propio enfriamiento independiente: no se
# puede repetir EL MISMO marcaje antes de que pasen estos minutos, para
# frenar los dobles-toques por duda ("¿me habrá marcado bien?").
COOLDOWN_MINUTES = 15

RECENT_MARKS_WINDOW_HOURS = 48

# Grupo que gatea el mapa/reporte de ubicaciones (dato sensible). Grupo
# nativo de Odoo, no de construtec_roles_permisos_19 (Community-only) - así
# este módulo funciona igual instalado en Community o en Enterprise.
ADMIN_GROUP_XMLID = 'hr.group_hr_manager'


def _euclidean_distance(vector_a, vector_b):
    if not vector_a or not vector_b or len(vector_a) != len(vector_b):
        return float('inf')
    return sum((a - b) ** 2 for a, b in zip(vector_a, vector_b)) ** 0.5


class ConstrutecFaceAttendanceController(http.Controller):

    @http.route('/construtec_face_attendance/verify', type='jsonrpc', auth='user')
    def verify_face(self, descriptor=None):
        """Compara la huella facial recibida contra las 3 fotos de referencia
        del empleado del usuario logueado. Nunca confía en un employee_id
        mandado por el cliente: siempre usa request.env.user.employee_id.
        """
        if not descriptor or not isinstance(descriptor, list):
            return {'ok': False, 'allow': False, 'error': _("No se recibió una huella facial válida.")}

        employee = request.env.user.employee_id
        if not employee:
            return {'ok': False, 'allow': False, 'error': _("Tu usuario no está vinculado a un empleado.")}

        employee = employee.sudo()
        if not employee.face_enrolled:
            return {
                'ok': False, 'allow': False,
                'error': _("Todavía no tenés el rostro registrado. Pedile a un Administrador que lo cargue."),
            }

        references = employee._construtec_face_reference_descriptors()
        best_distance = min(
            (_euclidean_distance(descriptor, reference) for reference in references),
            default=float('inf'),
        )
        allow = best_distance <= MATCH_THRESHOLD

        # Registro de cada intento (permita o no) para poder ajustar
        # MATCH_THRESHOLD con datos reales, no a ciegas - ver nota arriba
        # sobre el falso positivo del 2026-09-08. A nivel WARNING a propósito
        # (no INFO): odoo.conf de este proyecto corre con log_level=warn, y
        # esto es justo el tipo de dato que no se quiere perder por eso.
        _logger.warning(
            "construtec_face_attendance: verify uid=%s employee=%s distance=%.4f threshold=%s allow=%s",
            request.env.user.id, employee.id, best_distance, MATCH_THRESHOLD, allow,
        )

        if allow:
            # Un solo uso: se consume en el próximo marcaje.
            request.session[SESSION_FACE_TS] = time.time()
            request.session[SESSION_FACE_UID] = request.env.user.id

        return {
            'ok': True,
            'allow': allow,
            'distance': best_distance,
            'error': None if allow else _("El rostro no coincide con el registrado."),
        }

    @http.route('/construtec_face_attendance/analytic_accounts', type='jsonrpc', auth='user')
    def analytic_accounts(self):
        accounts = request.env['account.analytic.account'].sudo().search(
            [], order='name', limit=200,
        )
        return [{'id': account.id, 'name': account.display_name} for account in accounts]

    @http.route('/construtec_face_attendance/map_data', type='jsonrpc', auth='user', readonly=True)
    def map_data(self, date_from=None, date_to=None, employee_ids=None):
        """Datos para el wizard de mapa de marcajes - control de ubicación
        de colaboradores, reservado a Administrador (RRHH)."""
        if not request.env.user.has_group(ADMIN_GROUP_XMLID):
            return {'error': _("No tenés permiso para ver el mapa de marcajes.")}

        domain = []
        if employee_ids:
            domain.append(('employee_id', 'in', employee_ids))
        if date_from:
            domain.append(('create_date', '>=', '%s 00:00:00' % date_from))
        if date_to:
            domain.append(('create_date', '<=', '%s 23:59:59' % date_to))
        # Solo marcajes con una ubicación real capturada (0,0 = sin GPS).
        domain += ['|', ('latitude', '!=', 0.0), ('longitude', '!=', 0.0)]

        marks = request.env['construtec.attendance.mark'].sudo().search(
            domain, order='create_date desc', limit=2000,
        )
        return {'points': [{
            'id': mark.id,
            'employee_id': mark.employee_id.id,
            'employee_name': mark.employee_id.name,
            'mark_type': mark.mark_type,
            'label': MARK_TYPE_LABELS.get(mark.mark_type, mark.mark_type),
            'datetime': fields.Datetime.to_string(mark.create_date),
            'latitude': mark.latitude,
            'longitude': mark.longitude,
        } for mark in marks]}

    @http.route('/construtec_face_attendance/recent_marks', type='jsonrpc', auth='user', readonly=True)
    def recent_marks(self):
        """Historial de marcajes propios de las últimas 48hs, para que el
        empleado (no solo el administrador) pueda revisar lo que marcó."""
        employee = request.env.user.employee_id
        if not employee:
            return []
        since = fields.Datetime.now() - timedelta(hours=RECENT_MARKS_WINDOW_HOURS)
        marks = request.env['construtec.attendance.mark'].sudo().search([
            ('employee_id', '=', employee.id),
            ('create_date', '>=', since),
        ], order='create_date desc', limit=100)
        return [{
            'id': mark.id,
            'mark_type': mark.mark_type,
            'label': str(MARK_TYPE_LABELS.get(mark.mark_type, mark.mark_type)),
            'datetime': fields.Datetime.to_string(mark.create_date),
        } for mark in marks]

    @http.route('/construtec_face_attendance/location_ping', type='jsonrpc', auth='user')
    def location_ping(self, latitude=None, longitude=None):
        """Ping de ubicación automático, disparado por un timer del lado del
        navegador SOLO mientras la pestaña/app está en primer plano y el
        empleado ya está fichado (ver attendance_menu_patch.js) - no exige
        verificación facial (no es un marcaje, es una lectura de fondo), pero
        sí exige que el empleado esté realmente fichado en este momento,
        sin confiar en lo que diga el cliente al respecto."""
        if latitude is None or longitude is None:
            return {'ok': False, 'error': _("Faltan coordenadas.")}

        employee = request.env.user.employee_id
        if not employee:
            return {'ok': False, 'error': _("Tu usuario no está vinculado a un empleado.")}

        employee = employee.sudo()
        if employee.attendance_state != 'checked_in':
            return {'ok': False, 'error': _("Solo se registra ubicación mientras estás fichado.")}

        request.env['construtec.attendance.location_ping'].sudo().create({
            'employee_id': employee.id,
            'latitude': latitude,
            'longitude': longitude,
        })
        return {'ok': True}


class ConstrutecWebManifest(WebManifest):
    """Ícono propio de Construtec para "Instalar Aplicación" (PWA) - stock
    Odoo lo tiene hardcodeado a su propio logo (ver
    odoo/addons/web/controllers/webmanifest.py, WebManifest._get_webmanifest).
    Con fallback automático: si todavía no se cargó el archivo del ícono acá,
    se sigue viendo el logo de Odoo, sin romper nada."""

    _PWA_ICON_SIZES = ('192x192', '512x512')

    def _get_webmanifest(self):
        manifest = super()._get_webmanifest()
        try:
            file_path('construtec_face_attendance_19/static/description/pwa-icon-192x192.png')
        except FileNotFoundError:
            return manifest
        manifest['icons'] = [{
            'src': '/construtec_face_attendance_19/static/description/pwa-icon-%s.png' % size,
            'sizes': size,
            'type': 'image/png',
        } for size in self._PWA_ICON_SIZES]
        return manifest


class ConstrutecHrAttendances(HrAttendance):
    """Exige verificación facial server-side antes de aceptar cualquier
    marcaje disparado desde el widget de asistencia (systray) del usuario
    logueado. No toca el kiosco público ni el flujo de código de barras.
    """

    def _construtec_assert_face_verified(self):
        uid = request.env.user.id
        ts = request.session.get(SESSION_FACE_TS)
        verified_uid = request.session.get(SESSION_FACE_UID)
        # se consume siempre, sea válido o no (token de un solo uso)
        request.session.pop(SESSION_FACE_TS, None)
        request.session.pop(SESSION_FACE_UID, None)
        valid = bool(ts) and verified_uid == uid and (time.time() - ts) <= FACE_VERIFY_TTL
        if not valid:
            raise UserError(_("Necesitás verificar tu rostro antes de marcar asistencia."))

    def _construtec_check_cooldown(self, employee, mark_type):
        last = request.env['construtec.attendance.mark'].sudo().search([
            ('employee_id', '=', employee.id),
            ('mark_type', '=', mark_type),
        ], order='create_date desc', limit=1)
        if not last:
            return
        elapsed = fields.Datetime.now() - last.create_date
        if elapsed < timedelta(minutes=COOLDOWN_MINUTES):
            remaining = COOLDOWN_MINUTES - int(elapsed.total_seconds() // 60)
            raise UserError(_(
                "Ya marcaste \"%(label)s\" hace poco. Esperá %(minutes)s minuto(s) más."
            ) % {
                'label': MARK_TYPE_LABELS.get(mark_type, mark_type),
                'minutes': max(remaining, 1),
            })

    @http.route()
    def systray_attendance(self, latitude=False, longitude=False):
        # Se mantiene por compatibilidad (kiosco/otros llamadores de esta
        # ruta stock), aunque el widget de asistencia ya no la usa: ahora
        # llama a /construtec_face_attendance/mark para los 4 botones.
        self._construtec_assert_face_verified()
        return super().systray_attendance(latitude=latitude, longitude=longitude)

    @http.route('/construtec_face_attendance/mark', type='jsonrpc', auth='user')
    def construtec_mark(self, mark_type=None, latitude=False, longitude=False,
                         analytic_account_id=False, observaciones=False):
        """Punto de entrada único para los 4 botones de marcaje. Cada uno
        exige verificación facial fresca (token de un solo uso) y respeta su
        propio enfriamiento de 15 minutos, pero no valida orden/secuencia
        entre ellos - eso queda para que RRHH lo revise después."""
        if mark_type not in MARK_TYPES:
            return {'ok': False, 'error': _("Tipo de marcaje inválido.")}

        employee = request.env.user.employee_id
        if not employee:
            return {'ok': False, 'error': _("Tu usuario no está vinculado a un empleado.")}

        try:
            self._construtec_assert_face_verified()
            self._construtec_check_cooldown(employee, mark_type)
        except UserError as error:
            return {'ok': False, 'error': str(error)}

        employee = employee.sudo()
        attendance = False
        if mark_type in ('inicio_labores', 'fin_labores'):
            geo_ip_response = self._get_geoip_response(
                'systray', latitude=latitude, longitude=longitude,
                device_tracking_enabled=employee.company_id.attendance_device_tracking,
            )
            employee._attendance_action_change(geo_ip_response)
            attendance = employee.last_attendance_id

        mark = request.env['construtec.attendance.mark'].sudo().create({
            'employee_id': employee.id,
            'mark_type': mark_type,
            'attendance_id': attendance.id if attendance else False,
            'analytic_account_id': int(analytic_account_id) if analytic_account_id else False,
            'observaciones': observaciones or False,
            'latitude': latitude or 0.0,
            'longitude': longitude or 0.0,
        })

        return {
            'ok': True,
            'mark_id': mark.id,
            'attendance_id': attendance.id if attendance else False,
            **self._get_employee_info_response(employee),
        }
