import logging

from odoo import models, api, fields
from odoo.exceptions import UserError


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    otras_entradas = fields.One2many('hr.payslip.input', 'payslip_id', string='Otras entradas')
    parametro = fields.Many2one('hr.rule.parameter', string='Parámetro', required=True, default=lambda self: self.env['hr.rule.parameter'].search([('code', '=', 'sm')], limit=1))
    voucher_sent = fields.Integer(string='Voucher Enviado', store=True)
    def _create(self, data_list):
        res = super(HrPayslip, self)._create(data_list)
        for payslip in res:
            for worked_day in payslip.worked_days_line_ids:
                if worked_day.work_entry_type_id.round_days == 'FULL' and worked_day.number_of_hours > 0:
                    worked_day.write({'number_of_days': worked_day.number_of_hours / 24})
                if worked_day.work_entry_type_id.round_days == 'NO' and worked_day.number_of_hours > 0:
                    worked_day.write({'amount': worked_day.number_of_hours * payslip.contract_id.horas_extra_valor})
        return res

    def write(self, vals):
        res = super(HrPayslip, self).write(vals)
        for payslip in self:
            for worked_day in payslip.worked_days_line_ids:
                if worked_day.work_entry_type_id.round_days == 'FULL' and worked_day.number_of_hours > 0:
                    worked_day.write({'number_of_days': worked_day.number_of_hours / 24})
                if worked_day.work_entry_type_id.round_days == 'NO' and worked_day.number_of_hours > 0:
                    worked_day.write({'amount': worked_day.number_of_hours * payslip.contract_id.horas_extra_valor})
        if 'state' in vals:
            for record in self:
                record.send_salary_voucher()
        return res

    def compute_calification(self):
        """Update the computing sheet of a payslip by adding loan details
        to the 'Other Inputs' section."""
        for data in self:
            if (not data.employee_id) or (not data.date_from) or (not data.date_to):
                return
            # if data.input_line_ids.input_type_id:
            #     data.input_line_ids = [(5, 0, 0)]
            loan_line = data.struct_id.rule_ids.filtered(lambda x: x.code == 'BONPRO')
            if loan_line:
                get_amount = self.env['hr.qualification'].search([
                    ('employee_id', '=', data.employee_id.id),
                    ('state', '=', 'done'),
                    ('fecha_evaluacion', '>=', data.date_from),
                    ('fecha_evaluacion', '<=', data.date_to)
                ])
                if get_amount:
                    for line in get_amount:
                        amount = line.bonificacion * line.calificacion
                        name = 'Calificacion' #loan_line.id
                        data.input_data_line(name, amount, line)
    def action_payslip_done(self):
        # comprobar si las lineas de nomina pertenecen a la estructura de nomina
        for payslip in self:
            # if not payslip.contract_id.analytic_account_id:
            #     raise UserError('El contrato %s no tiene cuenta analítica' % payslip.contract_id.name)
            for line in payslip.line_ids:
                if line.salary_rule_id.struct_id != payslip.struct_id:
                    raise UserError('La regla salarial %s no pertenece a la estructura de nómina %s' % (line.salary_rule_id.name, payslip.struct_id.name))
        res = super(HrPayslip, self).action_payslip_done()
        return res

    @api.onchange('state')
    def send_salary_voucher(self):
        #Función para enviar el correo dependiendo del cambio de estado de la nómina
        if self.state in ['done']:
            if self.struct_id.report_id.name:
                _logger = logging.getLogger(__name__)
                try:
                    template_id = self.env.ref('nomina_report.email_template_voucher').id
                    if not template_id:
                        _logger.error('The template ID could not be found.')
                    else:
                        email_template = self.env['mail.template'].browse(template_id)
                        email_template.send_mail(self.id, force_send=True)
                        self.voucher_sent += 1
                except Exception as e:
                    _logger.error('Error sending salary voucher email: %s' % str(e))

class HrPayslipLine(models.Model):
    _inherit = 'hr.payslip.line'

    name = fields.Char(required=True, compute='_compute_display_name', store=True)

    @api.depends('salary_rule_id')
    def _compute_display_name(self):
        for line in self:
            line.name = line.salary_rule_id.name