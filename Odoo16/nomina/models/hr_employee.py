from odoo import models, api, fields, exceptions


class HrEmployeePrivate(models.Model):
    _inherit = "hr.employee"

    descuentos = fields.One2many("salary.advance", "employee_id", string="Descuentos")
    prestamos = fields.One2many('hr.loan', 'employee_id', string='Prestamos', store=True)
    calificaciones = fields.One2many('hr.qualification', 'employee_id', string='Calificaciones', store=True)
    entradas_trabajo = fields.One2many('hr.work.entry', 'employee_id', string='Entradas de trabajo')
    job_title = fields.Char(string="Puesto de trabajo", store=True, readonly=True)
    estado_contrato = fields.Many2one('hr.contract.status', string='Estado de contrato',  store=True, related='contract_id.estado_contrato')
    frecuencia_pago = fields.Many2one('hr.contract.payment.frequency', string='Frecuencia de pago', store=True, related='contract_id.frecuencia_pago')
    identification_id = fields.Char(string="DPI", store=True)


    @api.onchange('job_id')
    def _onchange_job_id(self):
        if self.job_id:
            self.job_title = self.job_id.name
        else:
            self.job_title = False


