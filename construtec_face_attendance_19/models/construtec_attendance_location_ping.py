# -*- coding: utf-8 -*-
from odoo import fields, models


class ConstrutecAttendanceLocationPing(models.Model):
    _name = 'construtec.attendance.location_ping'
    _description = 'Ping de Ubicación Automático (mientras el empleado está fichado)'
    _order = 'create_date desc'

    # Deliberadamente separado de construtec.attendance.mark: un ping no es
    # un marcaje (no lo generó ninguno de los 4 botones), es una lectura de
    # ubicación de fondo mientras la app sigue abierta y el empleado ya
    # está fichado - mezclarlo en el mismo modelo confundiría el reporte de
    # marcajes con datos que el empleado nunca "marcó" activamente.
    employee_id = fields.Many2one(
        'hr.employee', string="Empleado", required=True, ondelete='cascade', index=True,
    )
    latitude = fields.Float(digits=(10, 7))
    longitude = fields.Float(digits=(10, 7))
