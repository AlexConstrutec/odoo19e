from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class HrLoan(models.Model):
    _name = 'hr.loan'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Loan Request'

    @api.model
    def default_get(self, field_list):
        result = super().default_get(field_list)
        user_id = result.get('user_id') or self.env.context.get('user_id', self.env.user.id)
        result['employee_id'] = self.env['hr.employee'].search([('user_id', '=', user_id)], limit=1).id
        return result

    name = fields.Char(string='Prestamo', default='/', readonly=True)
    date = fields.Date(string='Fecha', default=fields.Date.today, readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True)
    department_id = fields.Many2one('hr.department', related='employee_id.department_id', readonly=True, string='Departmento')
    installment = fields.Integer(string='Cant Pagos', default=1)
    payment_date = fields.Date(string='Fecha inicio pagos', required=True, default=fields.Date.today)
    loan_lines = fields.One2many('hr.loan.line', 'loan_id', string='Pagos', index=True)
    company_id = fields.Many2one('res.company', string='Compania', readonly=True,
                                  default=lambda self: self.env.company.id)
    currency_id = fields.Many2one('res.currency', string='Moneda', required=True,
                                   default=lambda self: self.env.company.currency_id)
    job_position = fields.Many2one('hr.job', related='employee_id.job_id', readonly=True, string='Puesto')
    loan_amount = fields.Float(string='Monto Prestado', required=True)
    total_amount = fields.Float(string='Monto Total', store=True, readonly=True, compute='_compute_loan_amount')
    balance_amount = fields.Float(string='Saldo', store=True, compute='_compute_loan_amount')
    total_paid_amount = fields.Float(string='Monto Pagado', store=True, compute='_compute_loan_amount')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('waiting_approval_1', 'Confirmado'),
        ('approve', 'Aprobado'),
        ('refuse', 'Rechazado'),
        ('cancel', 'Cancelado'),
    ], string='Estado', default='draft', tracking=True, copy=False)
    dpi = fields.Char(string='DPI', related='employee_id.identification_id', store=True, readonly=True)
    version_id = fields.Many2one('hr.version', string='Contrato',
                                  default=lambda self: self.employee_id.version_id)
    version_is_current = fields.Boolean(string='Contrato Vigente', related='version_id.is_in_contract', readonly=True)
    concepto = fields.Many2one('hr.concepto.anticipo', string='Concepto', required=True,
                                domain=[('mostrar', '=', True)])
    reason = fields.Text(string='Descripcion')

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        for loan in self:
            loan.version_id = loan.employee_id.version_id

    @api.depends('loan_lines.amount', 'loan_lines.paid')
    def _compute_loan_amount(self):
        for loan in self:
            total_paid = sum(loan.loan_lines.filtered('paid').mapped('amount'))
            loan.total_amount = loan.loan_amount
            loan.total_paid_amount = total_paid
            loan.balance_amount = loan.loan_amount - total_paid

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.loan.seq') or '/'
        return super().create(vals_list)

    def compute_installment(self):
        for loan in self:
            loan.loan_lines.unlink()
            date_start = datetime.strptime(str(loan.payment_date), '%Y-%m-%d')
            amount = loan.loan_amount / loan.installment
            lines = []
            for _i in range(loan.installment):
                lines.append({
                    'date': date_start,
                    'amount': amount,
                    'employee_id': loan.employee_id.id,
                    'version_id': loan.version_id.id,
                    'loan_id': loan.id,
                })
                date_start += relativedelta(months=1)
            self.env['hr.loan.line'].create(lines)

    def action_refuse(self):
        self.write({'state': 'refuse'})

    def action_submit(self):
        self.write({'state': 'waiting_approval_1'})

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def action_approve(self):
        for loan in self:
            if not loan.loan_lines:
                raise ValidationError(self.env._('Calcule los pagos antes de aprobar.'))
            if not loan.version_id:
                raise ValidationError(self.env._('El empleado no tiene un contrato asignado.'))
        self.write({'state': 'approve'})

    def unlink(self):
        for loan in self:
            if loan.state in ('approve', 'cancel'):
                raise UserError(self.env._('No puede eliminar un prestamo que esté en estado aprobado o cancelado.'))
        return super().unlink()

    def write(self, vals):
        res = super().write(vals)
        for loan in self:
            if loan.loan_lines and round(sum(loan.loan_lines.mapped('amount')), 2) != round(loan.loan_amount, 2):
                raise ValidationError(
                    self.env._('La sumatoria de todos los pagos programados debe ser igual al monto del prestamo.'))
        return res


class HrLoanLine(models.Model):
    _name = 'hr.loan.line'
    _description = 'Installment Line'

    date = fields.Date(string='Fecha Pago', required=True)
    employee_id = fields.Many2one('hr.employee', string='Empleado')
    version_id = fields.Many2one('hr.version', string='Contrato',
                                  default=lambda self: self.employee_id.version_id)
    version_is_current = fields.Boolean(string='Contrato Vigente', related='version_id.is_in_contract', readonly=True)
    amount = fields.Float(string='Monto', required=True)
    paid = fields.Boolean(string='Pagado')
    loan_id = fields.Many2one('hr.loan', string='Prestamo')
    payslip_id = fields.Many2one('hr.payslip', string='Nomina')
    state = fields.Selection(related='loan_id.state', string='Estado', store=True)

    def unlink(self):
        for line in self:
            if line.paid and line.loan_id.state == 'approve':
                raise UserError(self.env._('No se puede eliminar un pago que ya ha sido pagado.'))
        return super().unlink()
