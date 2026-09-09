# -*- coding: utf-8 -*-
from odoo import fields, http
from odoo.http import request

# Mismo nombre de clase que el padre (convención de Odoo para "controller
# inheritance", ver el CLAUDE.md de construtec_face_attendance_helpdesk_19
# para la explicación completa del mecanismo).
from odoo.addons.construtec_face_attendance_19.controllers.main import (
    ConstrutecFaceAttendanceController, MARK_TYPE_LABELS,
)


class ConstrutecFaceAttendanceController(ConstrutecFaceAttendanceController):

    @http.route()
    def map_data(self, date_from=None, date_to=None, employee_ids=None):
        # El núcleo ya valida el permiso (hr.group_hr_manager) y arma los
        # puntos propios de esta base - acá solo se agregan, como pines
        # adicionales, los marcajes recibidos de Community.
        result = super().map_data(date_from=date_from, date_to=date_to, employee_ids=employee_ids)
        if 'error' in result:
            return result

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
        result['points'] += [{
            'id': 'mirror-%s' % mirror.id,
            'employee_id': mirror.employee_id.id or 'mirror-%s' % mirror.id,
            'employee_name': '%s (Community)' % (mirror.employee_id.name or mirror.employee_name),
            'mark_type': mirror.mark_type,
            'label': MARK_TYPE_LABELS.get(mirror.mark_type, mirror.mark_type),
            'datetime': fields.Datetime.to_string(mirror.received_date),
            'latitude': mirror.latitude,
            'longitude': mirror.longitude,
        } for mirror in mirrors]
        return result
