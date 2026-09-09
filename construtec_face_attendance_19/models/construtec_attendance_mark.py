# -*- coding: utf-8 -*-
import logging

from odoo import api, models, fields

from odoo.addons.construtec_account_payment_order_19.tools.enterprise_sync_api import (
    EnterpriseSyncError, _jsonrpc, authenticate,
)

_logger = logging.getLogger(__name__)

SYNC_MODEL = 'construtec.attendance.mark.mirror'


def _create_sync_record(url, db, login, api_key, vals):
    if not (url and db and login and api_key):
        raise EnterpriseSyncError(
            'Sincronización de Marcajes de Asistencia incompleta (falta URL, base de datos, '
            'usuario o API Key).')
    uid = authenticate(url, db, login, api_key)
    return _jsonrpc(
        url, 'object', 'execute_kw', [db, uid, api_key, SYNC_MODEL, 'sync_from_community', [vals]])


class ConstrutecAttendanceMark(models.Model):
    _name = 'construtec.attendance.mark'
    _description = 'Marcaje de Asistencia (Labores / Alimentación)'
    _order = 'create_date desc'

    employee_id = fields.Many2one('hr.employee', string="Empleado", required=True, ondelete='cascade', index=True)
    mark_type = fields.Selection([
        ('inicio_labores', 'Inicio de Labores / Hora Extra'),
        ('inicio_alimentacion', 'Inicio de Alimentación'),
        ('fin_alimentacion', 'Fin de Alimentación'),
        ('fin_labores', 'Fin de Labores / Hora Extra'),
    ], string="Tipo de Marcaje", required=True, index=True)
    # Solo se completa para inicio_labores/fin_labores: el registro real de
    # hr.attendance que ese marcaje generó o cerró. Los marcajes de
    # alimentación no tocan hr.attendance (Odoo no tiene ese concepto).
    attendance_id = fields.Many2one('hr.attendance', ondelete='set null')
    analytic_account_id = fields.Many2one('account.analytic.account', string="Cuenta Analítica")
    observaciones = fields.Text(string="Observaciones")
    latitude = fields.Float(digits=(10, 7))
    longitude = fields.Float(digits=(10, 7))
    maps_url = fields.Char(string="Ver en Mapa", compute='_compute_maps_url')

    # Sincronización hacia Enterprise (solo si esta compañía es "Solicitante" -
    # mismo mecanismo/campos de res.company ya construidos para Órdenes de
    # Pago en construtec_account_payment_order_19, reutilizados tal cual para
    # no pedirle al usuario una segunda URL/credencial para lo mismo).
    sync_state = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('enviado', 'Enviado'),
        ('error', 'Error'),
    ], default='pendiente', copy=False, index=True)
    sync_error = fields.Char(copy=False)
    sync_date = fields.Datetime(copy=False)

    @api.depends('latitude', 'longitude')
    def _compute_maps_url(self):
        for mark in self:
            if mark.latitude or mark.longitude:
                # OpenStreetMap: gratis, sin API key ni cuenta - mismo criterio
                # que el resto del módulo (nada de servicios de terceros con costo).
                mark.maps_url = (
                    "https://www.openstreetmap.org/?mlat=%s&mlon=%s#map=17/%s/%s"
                    % (mark.latitude, mark.longitude, mark.latitude, mark.longitude)
                )
            else:
                mark.maps_url = False

    @api.model_create_multi
    def create(self, vals_list):
        marks = super().create(vals_list)
        marks._sync_to_enterprise()
        return marks

    def _prepare_sync_vals(self):
        self.ensure_one()
        employee = self.employee_id
        return {
            'source_record_id': self.id,
            'employee_enterprise_ref': employee.enterprise_employee_ref,
            'employee_name': employee.name,
            'mark_type': self.mark_type,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'analytic_enterprise_ref': self.analytic_account_id.enterprise_analytic_ref,
            'observaciones': self.observaciones or False,
            'received_date': fields.Datetime.to_string(self.create_date),
        }

    def _sync_to_enterprise(self):
        # Un marcaje es un evento que nunca cambia después de creado - se
        # empuja una sola vez, al crear (no hace falta engancharse a write()).
        for mark in self:
            company = mark.employee_id.company_id
            if company.payment_order_role != 'solicitante' or not company.payment_order_sync_enabled:
                continue
            try:
                _create_sync_record(
                    company.payment_order_sync_url, company.payment_order_sync_db,
                    company.payment_order_sync_login, company.payment_order_sync_api_key,
                    mark._prepare_sync_vals())
            except EnterpriseSyncError as exc:
                _logger.warning('Error sincronizando marcaje %s hacia Enterprise: %s', mark.id, exc)
                mark.write({'sync_state': 'error', 'sync_error': str(exc)})
            else:
                mark.write({'sync_state': 'enviado', 'sync_error': False, 'sync_date': fields.Datetime.now()})

    def action_retry_sync(self):
        self.filtered(lambda m: m.sync_state == 'error')._sync_to_enterprise()

    @api.model
    def _cron_retry_sync(self):
        self.search([
            ('sync_state', '=', 'error'),
            ('employee_id.company_id.payment_order_role', '=', 'solicitante'),
        ])._sync_to_enterprise()
