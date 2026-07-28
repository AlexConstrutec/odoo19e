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
from odoo import models, fields, api


# import locale
#
# locale.setlocale(locale.LC_ALL, 'es_GT.UTF-8')

class HrPayslipInput(models.Model):
    """Inherited model for 'hr.payslip.input'"""
    _inherit = 'hr.payslip.input'

    loan_line_id = fields.Many2one('hr.loan.line',
                                   string="Loan Installment",
                                   help="Loan installment")


class HrPayslip(models.Model):
    """Employee payslip"""
    _inherit = 'hr.payslip'

    def compute_sheet(self):
        """Update the computing sheet of a payslip by adding loan details
        to the 'Other Inputs' section."""
        self._compute_worked_days_line_ids()
        res = super(HrPayslip, self).compute_sheet()
        for data in self:
            if (not data.employee_id) or (not data.date_from) or (
                    not data.date_to):
                return
            # if data.input_line_ids.input_type_id:
            #     data.input_line_ids = [(5, 0, 0)]
            loan_line = data.struct_id.rule_ids.filtered(
                lambda x: x.code == 'LO' or x.code == 'ANT3')
            if loan_line:
                get_amount = self.env['hr.loan'].search([
                    #('employee_id', '=', data.employee_id.id),
                    ('employee_contract_id', '=', data.contract_id.id),
                    ('state', '=', 'approve')
                ])#, limit=1)
                if get_amount:
                    for lines in get_amount:
                        for line in lines.loan_lines:
                            if data.date_from <= line.date <= data.date_to:
                                if not line.paid:
                                    amount = line.amount
                                    name = 'Prestamo' #loan_line.id
                                    data.input_data_line(name, amount, line)
        self.onchange_employee_salary()
        self.compute_calification()
        for entra in self.input_line_ids:
            if entra.amount == 0:
                entra.unlink()
        return res

    def action_payslip_done(self):
        """Mark loan as paid on paying payslip"""
        for line in self.input_line_ids:
            if line.loan_line_id:
                line.loan_line_id.paid = True
                line.loan_line_id.loan_id._compute_loan_amount()
        return super(HrPayslip, self).action_payslip_done()

    def input_data_line(self, name, amount, loan):
        """Add loan details to payslip as other input"""
        check_lines = []
        new_name = self.env['hr.payslip.input.type'].search([
            ('name', '=', name)])
        if name == 'Prestamo':
            thName = 'Fecha cobro: '+str(loan.date.strftime('%d %m %Y') + ' Total: Q.'+str("{:,.2f}".format(loan.loan_id.loan_amount)) +' Saldo: Q.'+str("{:,.2f}".format(sum(loan.loan_id.loan_lines.filtered(lambda x: x.paid == False).mapped('amount'))-loan.amount)))
            for busca in self.input_line_ids:
                if busca.code == 'LO':
                    busca.unlink()
        elif name == 'Calificacion':
            thName = 'Fecha evaluacion: '+str(loan.fecha_evaluacion.strftime('%d %m %Y') + ', Puntuacion: %'+str(loan.calificacion*100) +', Total: Q.'+str("{:,.2f}".format(amount)))
            for busca in self.input_line_ids:
                if busca.code == 'QUALY':
                    busca.unlink()
        elif name == 'Descuento':
            thName = 'Concepto: '+str(loan.concepto.name)+', Tipo anticipo: '+str(loan.tipo_anticipo.name) +', Fecha de descuento: ' + str(loan.date.strftime('%d %m %Y')+', Descripcion: '+str(loan.reason))
            for busca in self.input_line_ids:
                #concepto = 'Concepto: '+str(loan.concepto.name if loan.concepto.name else '')
                if busca.code == 'SAR' and str('Concepto: '+loan.concepto.name) in busca.name and str('Tipo anticipo: '+loan.tipo_anticipo.name) in busca.name and str(', Fecha de descuento: '+loan.date.strftime('%d %m %Y')) in busca.name and str(', Descripcion: '+str(loan.reason)) in busca.name:
                    busca.unlink()

        # self.write({
        #         'input_line_ids': [(0, 0, {
        #             'input_type_id': new_name.id,
        #             #Descripcion del descuento
        #             'name': thName,
        #             'loan_line_id': loan.id,
        #             'amount': amount
        #         })],
        #     })
            # Crear la nueva línea
        new_line = {}
        if name == 'Prestamo' and loan.loan_id.state == 'approve':
            new_line = {
                'input_type_id': new_name.id,
                'name': thName,
                'loan_line_id': loan.id,
                'amount': amount
                }
        elif name == 'Descuento' and loan.state == 'approve':
            new_line = {
                'input_type_id': new_name.id,
                'name': thName,
                'amount': amount
            }
        elif name == 'Calificacion' and loan.state == 'done':
            new_line = {
                'input_type_id': new_name.id,
                'name': thName,
                'amount': amount
            }

        if new_line:
            # Agregar la nueva línea a las existentes
            # Agregar la nueva línea a las existentes
            existing_lines = self.input_line_ids
            combined_lines = [(0, 0, new_line)] + [(1, line.id, line._convert_to_write(line._cache)) for line in existing_lines]

            # Actualizar input_line_ids con las líneas combinadas
            self.write({
                'input_line_ids': combined_lines
            })
            self.env.cr.commit()
        # input_line_ids.create({
        #     'input_type_id': new_name.id,
        #     'amount': amount,
        #     'name': thName,
        #     'loan_line_id': loan.id,
        #     'payslip_id': self.id
        # })

        # line = (0, 0, {
        #     'input_type_id': new_name.id,
        #     'amount': amount,
        #     'name': thName,
        #     'loan_line_id': loan.id
        # })
        # check_lines.append(line)
        #
        # self.input_line_ids = self.input_line_ids + check_lines


class HrPayslipInputType(models.Model):
    """Inherited model for 'hr.payslip.input.type'"""
    _inherit = 'hr.payslip.input.type'

    input_id = fields.Many2one('hr.salary.rule')


class HrSalaryRule(models.Model):
    """New field company_id on salary rule model"""
    _inherit = 'hr.salary.rule'

    company_id = fields.Many2one('res.company', 'Company',
                                 copy=False, readonly=True, help="Comapny",
                                 default=lambda self: self.env.user.company_id)


class HrPayrollStructure(models.Model):
    """New field company_id on 'hr.payroll.structure'"""
    _inherit = 'hr.payroll.structure'

    company_id = fields.Many2one('res.company', 'Company',
                                 copy=False, readonly=True, help="Comapny",
                                 default=lambda self: self.env.user.company_id)
