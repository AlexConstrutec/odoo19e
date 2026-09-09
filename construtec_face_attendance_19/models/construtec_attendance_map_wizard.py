# -*- coding: utf-8 -*-
from odoo import fields, models


class ConstrutecAttendanceMapWizard(models.TransientModel):
    _name = 'construtec.attendance.map.wizard'
    _description = 'Mapa de Marcajes de Asistencia'

    date_from = fields.Date(string="Desde", required=True, default=fields.Date.today)
    date_to = fields.Date(string="Hasta", required=True, default=fields.Date.today)
    employee_ids = fields.Many2many(
        'hr.employee', string="Colaboradores",
        help="Vacío = todos los colaboradores.",
    )

    def action_view_map(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'construtec_attendance_map',
            'name': 'Mapa de Marcajes',
            'params': {
                'date_from': fields.Date.to_string(self.date_from),
                'date_to': fields.Date.to_string(self.date_to),
                'employee_ids': self.employee_ids.ids,
            },
        }
