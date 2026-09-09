# -*- coding: utf-8 -*-
from odoo import api, fields, models

MARK_TYPES = [
    ('inicio_labores', 'Inicio de Labores / Hora Extra'),
    ('inicio_alimentacion', 'Inicio de Alimentación'),
    ('fin_alimentacion', 'Fin de Alimentación'),
    ('fin_labores', 'Fin de Labores / Hora Extra'),
]


class ConstrutecAttendanceMarkMirror(models.Model):
    _name = 'construtec.attendance.mark.mirror'
    _description = 'Marcaje de Asistencia recibido de Community'
    _order = 'received_date desc'

    # Nunca se resuelve el empleado por nombre (ambiguo, no confiable entre
    # bases distintas) - employee_id solo se llena si employee_enterprise_ref
    # resolvió a un hr.employee real en ESTA base; employee_name (texto) es
    # el respaldo que siempre está presente, igual que el resto de mirrors
    # de este proyecto (ej. construtec.helpdesk.ticket.mirror.partner_name).
    employee_id = fields.Many2one('hr.employee', string="Empleado")
    employee_name = fields.Char(string="Empleado (texto)", required=True)
    mark_type = fields.Selection(MARK_TYPES, string="Tipo de Marcaje", required=True, index=True)
    analytic_account_id = fields.Many2one('account.analytic.account', string="Cuenta Analítica")
    observaciones = fields.Text(string="Observaciones")
    latitude = fields.Float(digits=(10, 7))
    longitude = fields.Float(digits=(10, 7))
    maps_url = fields.Char(string="Ver en Mapa", compute='_compute_maps_url')
    # El id del marcaje en Community - nunca se usa como relación real, solo
    # para no duplicar si el cron de reintento vuelve a empujar el mismo
    # marcaje (idempotencia), igual criterio que el resto de este proyecto
    # ("nunca ids entre bases independientes", salvo como llave de dedupe).
    source_record_id = fields.Integer(string="ID en Community", required=True, index=True)
    received_date = fields.Datetime(string="Fecha del marcaje (Community)", required=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    _sql_constraints = [
        ('source_record_id_uniq', 'unique(source_record_id)',
         'Ya existe un marcaje recibido con ese identificador de origen.'),
    ]

    @api.depends('latitude', 'longitude')
    def _compute_maps_url(self):
        for mark in self:
            if mark.latitude or mark.longitude:
                mark.maps_url = (
                    "https://www.openstreetmap.org/?mlat=%s&mlon=%s#map=17/%s/%s"
                    % (mark.latitude, mark.longitude, mark.latitude, mark.longitude)
                )
            else:
                mark.maps_url = False

    @api.model
    def sync_from_community(self, vals):
        """Punto de entrada del push - llamado vía /jsonrpc (execute_kw) por
        el usuario de integración. El `create()` real NO usa sudo() (mismo
        criterio que el resto de mirrors de este proyecto: las reglas de
        permisos del propio usuario de integración son las que de verdad
        gatean la escritura) - pero la búsqueda de deduplicación por
        source_record_id SÍ usa sudo(), porque el grupo de integración es
        deliberadamente solo-creación (sin perm_read) y este chequeo es
        puramente interno (nunca expone datos del registro al llamador,
        solo decide si hace falta crear uno nuevo)."""
        existing = self.sudo().search([('source_record_id', '=', vals.get('source_record_id'))], limit=1)
        if existing:
            return existing.id

        # sudo() aquí también - el usuario de integración no tiene (ni debe
        # tener) permiso de lectura sobre hr.employee/account.analytic.account;
        # esto solo resuelve un id ya conocido a una relación real, nunca
        # expone datos de esos modelos al llamador.
        employee_id = False
        ref = vals.get('employee_enterprise_ref')
        if ref:
            employee = self.env['hr.employee'].sudo().browse(int(ref)).exists()
            employee_id = employee.id if employee else False

        analytic_id = False
        analytic_ref = vals.get('analytic_enterprise_ref')
        if analytic_ref:
            analytic = self.env['account.analytic.account'].sudo().browse(int(analytic_ref)).exists()
            analytic_id = analytic.id if analytic else False

        mark = self.create({
            'employee_id': employee_id,
            'employee_name': vals.get('employee_name') or '',
            'mark_type': vals.get('mark_type'),
            'analytic_account_id': analytic_id,
            'observaciones': vals.get('observaciones') or False,
            'latitude': vals.get('latitude') or 0.0,
            'longitude': vals.get('longitude') or 0.0,
            'source_record_id': vals.get('source_record_id'),
            'received_date': vals.get('received_date'),
        })
        return mark.id
