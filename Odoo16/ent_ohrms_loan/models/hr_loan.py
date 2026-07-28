# -*- coding: utf-8 -*-
######################################################################################
#
#    A part of Open HRMS Project <https://www.openhrms.com>
#
#    Copyright (C) 2022-TODAY Cybrosys Technologies(<https://www.cybrosys.com>).
#    Author: Cybrosys Techno Solutions (odoo@cybrosys.com)
#
#    This program is under the terms of the Odoo Proprietary License v1.0 (OPL-1)
#    It is forbidden to publish, distribute, sublicense, or sell copies of the Software
#    or modified copies of the Software.
#
#    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
#    IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
#    DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
#    ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#    DEALINGS IN THE SOFTWARE.
#
########################################################################################

from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class HrLoan(models.Model):
    """Model for Loan Requests for employees."""
    _name = 'hr.loan'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Loan Request"

    @api.model
    def default_get(self, field_list):
        """Retrieve default values for specified fields."""
        result = super(HrLoan, self).default_get(field_list)
        if result.get('user_id'):
            ts_user_id = result['user_id']
        else:
            ts_user_id = self.env.context.get('user_id', self.env.user.id)
        result['employee_id'] = self.env['hr.employee'].search(
            [('user_id', '=', ts_user_id)], limit=1).id
        return result

    def _compute_loan_amount(self):
        """calculate the total amount paid towards the loan."""
        total_paid = 0.0
        for loan in self:
            for line in loan.loan_lines:
                if line.paid:
                    total_paid += line.amount
            balance_amount = loan.loan_amount - total_paid
            loan.total_amount = loan.loan_amount
            loan.balance_amount = balance_amount
            loan.total_paid_amount = total_paid

    name = fields.Char(string="Prestamo", default="/", readonly=True,
                       help="Name of the loan")
    date = fields.Date(string="Fecha", default=fields.Date.today(),
                       readonly=True, help="Date")
    employee_id = fields.Many2one('hr.employee', string="Empleado",
                                  required=True, help="Empleado")
    department_id = fields.Many2one('hr.department',
                                    related="employee_id.department_id",
                                    readonly=True,
                                    string="Departmento", help="Employee")
    installment = fields.Integer(string="Cant Pagos", default=1,
                                 help="Cantidad de pagos")
    payment_date = fields.Date(string="Fecha inicio pagos", required=True,
                               default=fields.Date.today(),
                               help="Fecha de inicio de pagos")
    loan_lines = fields.One2many('hr.loan.line',
                                 'loan_id', string="Pagos",
                                 index=True)
    company_id = fields.Many2one('res.company', 'Compania', readonly=True,
                                 help="Compania",
                                 #default=lambda self: self.env.user.company_id,
                                 default = lambda self: self.env.company.id,
                                 states={'draft': [('readonly', False)]})
    currency_id = fields.Many2one('res.currency', string='Moneda',
                                  required=True, help="Moneda",
                                  default=lambda
                                      self: self.env.user.company_id.currency_id)
    job_position = fields.Many2one('hr.job', related="employee_id.job_id",
                                   readonly=True, string="Puesto",
                                   help="Puesto")
    loan_amount = fields.Float(string="Monto Prestado", required=True,
                               help="Monto Prestado")
    total_amount = fields.Float(string="Monto Total", store=True,
                                readonly=True, compute='_compute_loan_amount',
                                help="Monto Total")
    balance_amount = fields.Float(string="Saldo", store=True,
                                  compute='_compute_loan_amount',
                                  help="Saldo")
    total_paid_amount = fields.Float(string="Monto Pagado", store=True,
                                     compute='_compute_loan_amount',
                                     help="Monto Pagado")

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('waiting_approval_1', 'Confirmado'),
        ('approve', 'Aprobado'),
        ('refuse', 'Rechazado'),
        ('cancel', 'Cancelado'),
    ], string="Estado", default='draft', tracking=True, copy=False, )
    dpi = fields.Char(string='DPI', related='employee_id.identification_id', store=True, readonly=True)
    employee_contract_id = fields.Many2one('hr.contract', string='Contrato', default=lambda self: self.env['hr.contract'].search([('employee_id', '=', self.employee_id.id), ('state', '=', 'open')], limit=1))
    contract_state = fields.Selection(related='employee_contract_id.state', string='Estado Contrato', store=True,
                                      readonly=True)
    concepto = fields.Many2one('hr.concepto.anticipo', string='Concepto', required=True,
                               domain=[('mostrar', '=', True)])
    reason = fields.Text(string='Descripcion', help="Reason")

    @api.model
    def create(self, values):
    # No permitia registrar mas de un prestamo a un empleado
    #     """creates a new HR loan record with the provided values."""
    #     loan_count = self.env['hr.loan'].search_count(
    #         [('employee_id', '=', values['employee_id']),
    #          ('state', '=', 'approve'),
    #          ('balance_amount', '!=', 0)])
    #     if loan_count:
    #         raise ValidationError(
    #             _("The employee has already a pending installment"))
    #     else:
    #         values['name'] = self.env['ir.sequence'].get('hr.loan.seq') or ' '
    #         res = super(HrLoan, self).create(values)
    #         return res
        values['name'] = self.env['ir.sequence'].get('hr.loan.seq') or ' '
        res = super(HrLoan, self).create(values)
        return res

    def compute_installment(self):
        """This automatically create the installment the employee need to pay
        to company based on payment start date and the no of installments."""
        for loan in self:
            loan.loan_lines.unlink()
            date_start = datetime.strptime(str(loan.payment_date), '%Y-%m-%d')
            amount = loan.loan_amount / loan.installment
            for i in range(1, loan.installment + 1):
                self.env['hr.loan.line'].create({
                    'date': date_start,
                    'amount': amount,
                    'employee_id': loan.employee_id.id,
                    'employee_contract_id': loan.employee_contract_id.id,
                    'loan_id': loan.id})
                date_start = date_start + relativedelta(months=1)
            loan._compute_loan_amount()
        return True

    def action_refuse(self):
        """Action to refuse the loan"""
        return self.write({'state': 'refuse'})

    def action_submit(self):
        """Action to submit the loan"""
        self.write({'state': 'waiting_approval_1'})

    def action_cancel(self):
        """Action to cancel the loan"""
        self.write({'state': 'cancel'})

    def action_approve(self):
        """Approve loan by the manager"""
        for data in self:
            if not data.loan_lines:
                raise ValidationError(_("Please Compute installment"))
            if not data.employee_contract_id:
                raise ValidationError(_("El empleado no tiene un contrato asignado."))
            else:
                self.write({'state': 'approve'})

    def unlink(self):
        """Unlink loan lines"""
        for loan in self:
            if loan.state in ('approve', 'cancel'):
                raise UserError('No puede eliminar un prestamo que este en estado aprobado o cancelado.')
        return super(HrLoan, self).unlink()

    @api.onchange('loan_lines')
    def _onchange_loan_lines(self):
        """Onchange function for loan lines"""
        for loan in self:
            if loan.loan_lines:
                loan.total_amount = sum([line.amount for line in loan.loan_lines])

    def write(self, vals):
        res = super(HrLoan, self).write(vals)
        """Write function for loan"""
        for record in self:
            if record.loan_lines:
                sumatoria = sum(line.amount for line in record.loan_lines)
                pres = round(sumatoria, 2)
                if (round(sumatoria, 2) != record.loan_amount):
                    self.env.cr.rollback()
                    raise ValidationError(_("La sumatoria de todos los pagos programados debe ser igual al monto del prestamo."))


        return res


class InstallmentLine(models.Model):
    _name = "hr.loan.line"
    _description = "Installment Line"

    date = fields.Date(string="Fecha Pago", required=True,
                       help="Date of the payment")
    employee_id = fields.Many2one('hr.employee', string="Empleado",
                                  help="Empleado")
    employee_contract_id = fields.Many2one('hr.contract', string='Contrato', default=lambda self: self.env['hr.contract'].search([('employee_id', '=', self.employee_id.id), ('state', '=', 'open')], limit=1))
    contract_state = fields.Selection(related='employee_contract_id.state', string='Estado Contrato', store=True, readonly=True)
    amount = fields.Float(string="Monto", required=True, help="Monto")
    paid = fields.Boolean(string="Pagado", help="Esta pagado")
    loan_id = fields.Many2one('hr.loan', string="Prestamo", help="Prestamo")
    payslip_id = fields.Many2one('hr.payslip', string="Nomina", help="Nomina")
    state = fields.Selection([('draft', 'Borrador'),
        ('waiting_approval_1', 'Confirmado'),
        ('approve', 'Aprobado'),
        ('refuse', 'Rechazado'),
        ('cancel', 'Cancelado'), ], string="Estado", default='draft', tracking=True, copy=False, related='loan_id.state')


    def unlink(self):
        """Unlink loan lines"""
        for line in self:
            if line.paid and line.loan_id.state == 'approve':
                raise UserError('No se puede eliminar un pago que ya ha sido pagado.')
        return super(InstallmentLine, self).unlink()


class HrEmployee(models.Model):
    _inherit = "hr.employee"
    loan_count = fields.Integer(string="Loan Count",
                                compute='_compute_employee_loans')
    def _compute_employee_loans(self):
        """This compute the loan amount and total loans count of an employee.
            """
        self.loan_count = self.env['hr.loan'].search_count(
            [('employee_id', '=', self.id)])


