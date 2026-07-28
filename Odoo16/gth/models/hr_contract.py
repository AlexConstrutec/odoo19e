from collections import defaultdict

from odoo import models, fields, api
from datetime import date, datetime


class Contract(models.Model):
    _inherit = 'hr.contract'
    departure_reason_id = fields.Many2one('hr.departure.reason', string='Motivo de salida', store=True)
    registrar_fecha_inspeccion = fields.Boolean(string='Registrar fecha ante GT RECIT', default=False,
                                                help='Marque esta casilla si desea registrar la fecha de inspección ante GT RECIT')

    @api.model
    def create(self, vals_list):
        # Llama al método create original para mantener la lógica existente
        contracts = super(Contract, self).create(vals_list)
        # Recorre cada contrato creado
        for contract in contracts:
            # Crear un historial de trabajo para cada contrato creado
            if contract.state == 'draft' or contract.state == 'open':
                self.env['hr.employee.history.job.salary'].create({
                    'date_start': contract.date_start,
                    'date_end': contract.date_end or None,  # Deja este campo vacío si no se ha terminado el contrato
                    'company': contract.company_id.name,
                    'job': contract.job_id.name,
                    'employee': contract.employee_id.name,
                    'salary': contract.wage+contract.bonificacion_incentivo+contract.bonificacion_fija+contract.bonificacion_productividad,  # Asegúrate de que el campo 'wage' sea el salario
                    'identification_employee_id': contract.employee_id.identification_id,
                    'contract_id': contract.id,
                    'contrato_registrado': contract.registrar_fecha_inspeccion
                })
        return contracts

    @api.onchange('state')
    def _onchange_state(self):
        # Buscar el historial asociado al contrato actual
        historial = self.env['hr.employee.history.job.salary'].search([('contract_id', '=', self.ids)], limit=1)

        if self.state == 'close' or self.state == 'cancel':
            # Si el contrato se cierra, actualiza la fecha de finalización en el historial
            historial.date_end = self.date_end
        else:
            historial.date_end = None

    @api.onchange('date_start')
    def _onchange_date_start(self):
        # Buscar el historial asociado al contrato actual
        historial = self.env['hr.employee.history.job.salary'].search([('contract_id', '=', self.ids)], limit=1)
        historial.date_start = self.date_start

    @api.onchange('date_end')
    def _onchange_date_end(self):
        # Buscar el historial asociado al contrato actual
        historial = self.env['hr.employee.history.job.salary'].search([('contract_id', '=', self.ids)], limit=1)
        historial.date_end = self.date_end

    @api.onchange('registrar_fecha_inspeccion')
    def _onchange_registrar_fecha_inspeccion(self):
        # Buscar el historial asociado al contrato actual
        historial = self.env['hr.employee.history.job.salary'].search([('contract_id', '=', self.ids)], limit=1)
        historial.contrato_registrado = self.registrar_fecha_inspeccion

    # @api.onchange('wage')
    # def _onchange_wage(self):
    #     # Buscar el historial asociado al contrato actual
    #     self.env['hr.employee.history.job.salary'].create({
    #         'date_start': self.date_start,
    #         'date_end': self.date_end or None,
    #         'company': self.company_id.name,
    #         'job': self.job_id.name,
    #         'employee': self.employee_id.name,
    #         'salary': self.wage,
    #         'identification_employee_id': self.employee_id.identification_id,
    #         'contract_id': self.id
    #     })




