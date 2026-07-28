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
import time
from datetime import datetime
from odoo import fields, models, api, _
from odoo import exceptions
from odoo.exceptions import UserError


class SalaryAdvancePayment(models.Model):
    _name = "salary.advance"
    _description = "Salary Advance"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Name', readonly=True,
                       default=lambda self: 'Adv/')
    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True, help="Employee", store=True)
    date = fields.Date(string='Fecha', required=True,
                       default=lambda self: fields.Date.today(),
                       help="Submit date")
    reason = fields.Text(string='Descripcion', help="Reason")
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  required=True,
                                  default=lambda
                                      self: self.env.user.company_id.currency_id)
    company_id = fields.Many2one('res.company', string='Compania', required=True, default=lambda self: self.env.company)
    advance = fields.Float(string='Monto', required=True)
    payment_method = fields.Many2one('account.journal', string='Payment Method')
    exceed_condition = fields.Boolean(string='Exceed than Maximum',
                                      help="The Advance is greater than the maximum percentage in salary structure")
    department = fields.Many2one('hr.department', string='Departmento', related='employee_id.department_id', readonly=True)
    state = fields.Selection([('draft', 'Borrador'),
                              ('approve', 'Aprobado'),
                              ('cobrado', 'Cobrado'),
                              ('reject', 'Rechazado')], string='Estado',
                             default='draft')
    #debit = fields.Many2one('account.account', string='Debit Account')
    #credit = fields.Many2one('account.account', string='Credit Account')
    journal_id = fields.Many2one('account.journal', string='Diario', readonly=True, related='cheque.journal_id')
    employee_contract_id = fields.Many2one('hr.contract', string='Contrato', default=lambda self: self.env['hr.contract'].search([('employee_id', '=', self.employee_id.id)], limit=1))
    contract_state = fields.Selection(related='employee_contract_id.state', string='Estado Contrato', store=True,
                                      readonly=True)
    tipo_anticipo = fields.Many2one('hr.tipo.anticipo', string='Tipo de Anticipo', required=True, domain="[('mostrar', '=', True)]")
    concepto = fields.Many2one('hr.concepto.anticipo', string='Concepto', required=True, domain=[('mostrar', '=', True)])
    # tipo_anticipo = fields.Selection([
    #     ('1', 'Anticipo 1'),
    #     ('2', 'Anticipo 2'),
    #     ('3', 'Anticipo 3')
    # ], string='Tipo de Anticipo', default='1', store=True)
    #
    # concepto = fields.Selection([('1', 'Cupones Medicos'),
    #                             ('2', 'Uniformes'),
    #                             ('3', 'Varios'),
    #                             ('4', 'Credito Personal'),
    #                             ('5', 'Devoluciones Produccion'),
    #                             ('6', 'Faltante de Banco'),
    #                             ('7', 'Xelaxooper'),
    #                             ('8', 'Capacitaciones'),
    #                             ('10', 'Gafetes'),
    #                             ('12', 'Multas'),
    #                             ('13', 'Seguros'),
    #                             ('14', 'Billetes Falsos'),
    #                             ('15', 'Faltante en Caja'),
    #                             ('16', 'Faltante Inventario'),
    #                             ('17', 'Boleto de Ornato'),
    #                             ('18', 'Impuestos-Multa'),
    #                             ('19', 'Examen de Laboratorio'),
    #                             ('20', 'Examen de Torax'),
    #                             ('21', 'Fotografía para Tarjeta de Salud'),
    #                             ('22', 'Ticket Xrun'),
    #                             ('23', 'Playera de Niños Xrun'),
    #                             ('24', 'Gorras Xrun'),
    #                             ('25', 'Anticipo sobre sueldos')], string='Concepto',
    #                            default='3', store=True)

    cheque = fields.Many2one('account.payment', string='Cheque', store=True)
    dpi = fields.Char(string='DPI', related='employee_id.identification_id', store=True, readonly=True)

    # @api.onchange('cheque')
    # def onchange_cheque(self):
    #     if self.cheque:
    #         self.journal_id = self.cheque.journal_id.id
    #     else:
    #         self.journal_id = False

    @api.onchange('employee_id')
    def onchange_employee_id(self):
        department_id = self.employee_id.department_id.id
        domain = [('employee_id', '=', self.employee_id.id)]
        return {'value': {'department': department_id}, 'domain': {
            'employee_contract_id': domain,
        }}

    @api.onchange('company_id')
    def onchange_company_id(self):
        company = self.company_id
        domain = [('company_id.id', '=', company.id)]
        result = {
            'domain': {
                'journal': domain,
            },

        }
        return result

    def submit_to_manager(self):
        self.state = 'submit'

    def cancel(self):
        self.state = 'cancel'

    def reject(self):
        self.state = 'reject'

    @api.model
    def create(self, vals):
        vals['name'] = self.env['ir.sequence'].get('salary.advance.seq') or ' '
        res_id = super(SalaryAdvancePayment, self).create(vals)
        return res_id

    def approve_request(self):
        """This Approves the employee salary advance request.
                   """
        emp_obj = self.env['hr.employee']
        address = emp_obj.browse([self.employee_id.id]).address_home_id
        if not address.id:
            raise UserError(
                'Defina la dirección particular del empleado. es decir, dirección bajo información privada del empleado. Campo - Direccion - en la ficha del empleado')
        salary_advance_search = self.search(
            [('employee_id', '=', self.employee_id.id), ('id', '!=', self.id),
             ('state', '=', 'approve')])
        current_month = datetime.strptime(str(self.date), '%Y-%m-%d').date().month
        for each_advance in salary_advance_search:
            existing_month = datetime.strptime(str(each_advance.date),
                                               '%Y-%m-%d').date().month
            # if current_month == existing_month:
            #     raise UserError('El anticipo se puede solicitar una vez al mes')
        if not self.employee_contract_id:
            raise UserError('Seleccione un contrato para el empleado')

        struct_id = self.employee_contract_id.structure_type_id.default_struct_id
        adv = self.advance
        amt = self.employee_contract_id.wage
        if adv > amt and not self.exceed_condition:
            raise UserError('El monto del anticipo es mayor que el salario base')
        payslip_obj = self.env['hr.payslip'].search(
            [('employee_id', '=', self.employee_id.id),
             ('state', '=', 'done'), ('date_from', '<=', self.date),
             ('date_to', '>=', self.date)])
        if payslip_obj:
            raise UserError("This month salary already calculated")

        for slip in self.env['hr.payslip'].search(
                [('employee_id', '=', self.employee_id.id)]):
            slip_moth = datetime.strptime(str(slip.date_from),
                                          '%Y-%m-%d').date().month
            if current_month == slip_moth + 1:
                slip_day = datetime.strptime(str(slip.date_from),
                                             '%Y-%m-%d').date().day
                current_day = datetime.strptime(str(self.date),
                                                '%Y-%m-%d').date().day
                if current_day - slip_day < struct_id.advance_date:
                    raise exceptions.Warning(
                        _('Request can be done after "%s" Days From prevoius month salary') % struct_id.advance_date)
        self.state = 'waiting_approval'

    def approve_request_acc_dept(self):
        # """This Approves the employee salary advance request from accounting department.
        #            """
        # salary_advance_search = self.search(
        #     [('employee_id', '=', self.employee_id.id), ('id', '!=', self.id),
        #      ('state', '=', 'approve')])
        # current_month = datetime.strptime(str(self.date),
        #                                   '%Y-%m-%d').date().month
        # for each_advance in salary_advance_search:
        #     existing_month = datetime.strptime(str(each_advance.date),
        #                                        '%Y-%m-%d').date().month
        #     if current_month == existing_month:
        #         raise UserError('El anticipo se puede solicitar una vez al mes')
        # if not self.debit or not self.credit or not self.journal:
        #     raise UserError(
        #         "You must enter Debit & Credit account and journal to approve ")
        # if not self.advance:
        #     raise UserError('You must Enter the Salary Advance amount')
        #
        # timenow = time.strftime('%Y-%m-%d')
        # for request in self:
        #     amount = request.advance
        #     request_name = request.employee_id.name
        #     reference = request.name
        #     journal_id = request.journal.id
        #     debit_account_id = request.debit.id
        #     credit_account_id = request.credit.id
        #     debit_line = {
        #         'name': request_name,
        #         'account_id': debit_account_id,
        #         'journal_id': journal_id,
        #         'date': timenow,
        #         'debit': amount > 0.0 and amount or 0.0,
        #         'credit': amount < 0.0 and -amount or 0.0,
        #     }
        #     credit_line = {
        #         'name': request_name,
        #         'account_id': credit_account_id,
        #         'journal_id': journal_id,
        #         'date': timenow,
        #         'debit': amount < 0.0 and -amount or 0.0,
        #         'credit': amount > 0.0 and amount or 0.0,
        #     }
        #     vals = {
        #         'name': 'Salary Advance Of ' + ' ' + request_name,
        #         'narration': request_name,
        #         'ref': reference,
        #         'journal_id': journal_id,
        #         'date': timenow,
        #         'line_ids': [(0, 0, debit_line), (0, 0, credit_line)]
        #     }
        #
        #     move = self.env['account.move'].create(vals)
        #     move.action_post()
        self.write({'state': 'approve'})
        return True

    def set_to_draft(self):
        if self.state != 'cobrado':
            self.state = 'draft'

    def set_to_cobrado(self):
        if self.state == 'approve':
            self.state = 'cobrado'
        else:
            raise UserError('No se puede cobrar el descuento, debe estar aprobado')

class HrTipoAnticipo(models.Model):
    _name = 'hr.tipo.anticipo'
    _description = 'Tipo de anticipo'

    name = fields.Char(string='Nombre', required=True)
    mostrar = fields.Boolean(string='Mostrar en nómina', default=True)
    active = fields.Boolean(string='Activo', default=True)

class HrConceptoAnticipo(models.Model):
    _name = 'hr.concepto.anticipo'
    _description = 'Concepto de anticipo'

    name = fields.Char(string='Nombre', required=True)
    mostrar = fields.Boolean(string='Mostrar en nómina', default=True)
    active = fields.Boolean(string='Activo', default=True)