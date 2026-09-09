# -*- coding: utf-8 -*-
from odoo import fields, http, _
from odoo.http import request

ADMIN_GROUP_XMLID = 'hr.group_hr_manager'

# Copia deliberada de construtec_face_attendance_19::MARK_TYPE_LABELS - este
# módulo ya no depende del núcleo (Enterprise nunca marca asistencia), así
# que no hay de dónde importarla. Si el núcleo agrega/cambia un tipo de
# marcaje, hay que reflejarlo acá a mano.
MARK_TYPE_LABELS = {
    'inicio_labores': 'Inicio de Labores / Hora Extra',
    'inicio_alimentacion': 'Inicio de Alimentación',
    'fin_alimentacion': 'Fin de Alimentación',
    'fin_labores': 'Fin de Labores / Hora Extra',
}


class ConstrutecAttendanceSyncController(http.Controller):

    @http.route('/construtec_attendance_sync/map_data', type='jsonrpc', auth='user', readonly=True)
    def map_data(self, date_from=None, date_to=None, employee_ids=None):
        """Datos para el wizard de mapa de marcajes recibidos de Community -
        reservado a Administrador (RRHH), mismo criterio que el núcleo."""
        if not request.env.user.has_group(ADMIN_GROUP_XMLID):
            return {'error': _("No tenés permiso para ver el mapa de marcajes.")}

        domain = ['|', ('latitude', '!=', 0.0), ('longitude', '!=', 0.0)]
        if employee_ids:
            domain.append(('employee_id', 'in', employee_ids))
        if date_from:
            domain.append(('received_date', '>=', '%s 00:00:00' % date_from))
        if date_to:
            domain.append(('received_date', '<=', '%s 23:59:59' % date_to))

        mirrors = request.env['construtec.attendance.mark.mirror'].sudo().search(
            domain, order='received_date desc', limit=2000,
        )
        return {'points': [{
            'id': mirror.id,
            'employee_id': mirror.employee_id.id or mirror.id,
            'employee_name': mirror.employee_id.name or mirror.employee_name,
            'mark_type': mirror.mark_type,
            'label': MARK_TYPE_LABELS.get(mirror.mark_type, mirror.mark_type),
            'datetime': fields.Datetime.to_string(mirror.received_date),
            'latitude': mirror.latitude,
            'longitude': mirror.longitude,
        } for mirror in mirrors]}
