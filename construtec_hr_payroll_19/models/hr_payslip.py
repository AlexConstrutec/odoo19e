from odoo import api, fields, models
from odoo.exceptions import UserError


class HrPayslipInput(models.Model):
    _inherit = 'hr.payslip.input'

    loan_line_id = fields.Many2one('hr.loan.line', string='Cuota de préstamo')


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    # parametro = fields.Many2one(
    #     'hr.rule.parameter', string='Parámetro', required=True,
    #     default=lambda self: self.env['hr.rule.parameter'].search([('code', '=', 'sm')], limit=1))
    # voucher_sent = fields.Integer(string='Voucher Enviado')
    payment_ids = fields.One2many('account.payment', 'payslip_id', string='Pagos', readonly=True, copy=False)
    total_amount = fields.Float(string='Monto Total', compute='_compute_balance', store=True)
    balance = fields.Float(string='Saldo', compute='_compute_balance', store=True)

    @api.depends('line_ids.total', 'line_ids.salary_rule_id', 'payment_ids.amount')
    def _compute_balance(self):
        for payslip in self:
            net_total = sum(payslip.line_ids.filtered(lambda l: l.salary_rule_id.code == 'NET').mapped('total'))
            payslip.total_amount = net_total
            payslip.balance = net_total - sum(payslip.payment_ids.mapped('amount'))

    def compute_sheet(self):
        self._adjust_worked_days_lines()
        self._compute_extra_inputs()
        return super().compute_sheet()

    def _adjust_worked_days_lines(self):
        """Convierte horas a días o calcula el monto de horas extra según el tipo de entrada."""
        for payslip in self:
            for worked_day in payslip.worked_days_line_ids:
                if worked_day.number_of_hours <= 0:
                    continue
                if worked_day.work_entry_type_id.round_days == 'FULL':
                    worked_day.number_of_days = worked_day.number_of_hours / 24
                elif worked_day.work_entry_type_id.round_days == 'NO':
                    worked_day.amount = worked_day.number_of_hours * payslip.version_id.x_horas_extra_valor

    def _compute_extra_inputs(self):
        """Genera las líneas de 'otras entradas' de préstamos, anticipos y calificaciones vigentes."""
        input_type_loan = self.env.ref('construtec_hr_payroll_19.hr_payslip_input_type_loan', raise_if_not_found=False)
        input_type_advance = self.env.ref('construtec_hr_payroll_19.hr_payslip_input_type_advance', raise_if_not_found=False)
        input_type_qualification = self.env.ref(
            'construtec_hr_payroll_19.hr_payslip_input_type_qualification', raise_if_not_found=False)

        for payslip in self:
            if not (payslip.employee_id and payslip.date_from and payslip.date_to):
                continue
            rule_codes = set(payslip.struct_id.rule_ids.mapped('code'))
            new_inputs = []
            codes_to_clear = []

            if input_type_loan and rule_codes & {'LO', 'ANT3'}:
                codes_to_clear.append('LO')
                loans = self.env['hr.loan'].search([
                    ('version_id', '=', payslip.version_id.id),
                    ('state', '=', 'approve'),
                ])
                pending_lines = loans.loan_lines.filtered(
                    lambda l: not l.paid and payslip.date_from <= l.date <= payslip.date_to)
                for line in pending_lines:
                    saldo = sum(line.loan_id.loan_lines.filtered(lambda l: not l.paid).mapped('amount')) - line.amount
                    new_inputs.append((0, 0, {
                        'input_type_id': input_type_loan.id,
                        'loan_line_id': line.id,
                        'amount': line.amount,
                        'name': self.env._(
                            'Fecha cobro: %(date)s Total: Q.%(total)s Saldo: Q.%(saldo)s',
                            date=line.date.strftime('%d/%m/%Y'),
                            total=f'{line.loan_id.loan_amount:,.2f}', saldo=f'{saldo:,.2f}'),
                    }))

            if input_type_advance and rule_codes & {'SAR', 'ANT1', 'ANT2', 'ANT3'}:
                codes_to_clear.append('SAR')
                advances = self.env['salary.advance'].search([
                    ('version_id', '=', payslip.version_id.id),
                    ('state', '=', 'approve'),
                    ('date', '>=', payslip.date_from),
                    ('date', '<=', payslip.date_to),
                ])
                for advance in advances:
                    new_inputs.append((0, 0, {
                        'input_type_id': input_type_advance.id,
                        'amount': advance.advance,
                        'name': self.env._(
                            'Concepto: %(concepto)s, Tipo anticipo: %(tipo)s, Fecha de descuento: %(date)s, Descripcion: %(desc)s',
                            concepto=advance.concepto.name, tipo=advance.tipo_anticipo.name,
                            date=advance.date.strftime('%d/%m/%Y'), desc=advance.reason or ''),
                    }))

            if input_type_qualification and 'BONPRO' in rule_codes:
                codes_to_clear.append('QUALY')
                qualifications = self.env['hr.qualification'].search([
                    ('employee_id', '=', payslip.employee_id.id),
                    ('state', '=', 'done'),
                    ('fecha_evaluacion', '>=', payslip.date_from),
                    ('fecha_evaluacion', '<=', payslip.date_to),
                ])
                for qualification in qualifications:
                    amount = qualification.bonificacion * qualification.calificacion
                    new_inputs.append((0, 0, {
                        'input_type_id': input_type_qualification.id,
                        'amount': amount,
                        'name': self.env._(
                            'Fecha evaluacion: %(date)s, Puntuacion: %(score)s%%, Total: Q.%(total)s',
                            date=qualification.fecha_evaluacion.strftime('%d/%m/%Y'),
                            score=qualification.calificacion * 100, total=f'{amount:,.2f}'),
                    }))

            # Otras entradas registradas a nivel de empleado (hr.payslip.input.employee),
            # p.ej. bonificaciones, gratificaciones, ajustes, etc. del catálogo hr.payslip.input.type.
            generic_entries = self.env['hr.payslip.input.employee'].search([
                ('version_id', '=', payslip.version_id.id),
                ('state', '=', 'approve'),
                ('date_from', '<=', payslip.date_to),
                ('date_to', '>=', payslip.date_from),
            ])
            if generic_entries:
                codes_to_clear.extend(generic_entries.mapped('input_type_id.code'))
                for entry in generic_entries:
                    new_inputs.append((0, 0, {
                        'input_type_id': entry.input_type_id.id,
                        'amount': entry.amount,
                        'name': entry.name or entry.input_type_id.name,
                    }))

            if codes_to_clear:
                payslip.input_line_ids.filtered(lambda l: l.code in codes_to_clear).unlink()
            if new_inputs:
                payslip.write({'input_line_ids': new_inputs})

        self.input_line_ids.filtered(lambda l: not l.amount).unlink()

    # def action_payslip_done(self):
    #     for payslip in self:
    #         mismatched = payslip.line_ids.filtered(lambda l: l.salary_rule_id.struct_id != payslip.struct_id)
    #         if mismatched:
    #             raise UserError(self.env._(
    #                 'La regla salarial %(rule)s no pertenece a la estructura de nómina %(struct)s.',
    #                 rule=mismatched[0].salary_rule_id.name, struct=payslip.struct_id.name))
    #     self.input_line_ids.filtered('loan_line_id').loan_line_id.write({'paid': True})
    #     return super().action_payslip_done()
    #
    # def write(self, vals):
    #     res = super().write(vals)
    #     if 'state' in vals:
    #         self.filtered(lambda p: p.state == 'validated').send_salary_voucher()
    #     return res
    #
    # def send_salary_voucher(self):
    #     template = self.env.ref('construtec_hr_reports_19.email_template_voucher', raise_if_not_found=False)
    #     if not template:
    #         return
    #     for payslip in self:
    #         if not payslip.struct_id.report_id:
    #             continue
    #         template.send_mail(payslip.id, force_send=True)
    #         payslip.voucher_sent += 1


class HrPayslipLine(models.Model):
    _inherit = 'hr.payslip.line'

    name = fields.Char(required=True, compute='_compute_display_name', store=True)

    @api.depends('salary_rule_id')
    def _compute_display_name(self):
        for line in self:
            line.name = line.salary_rule_id.name
