# -*- coding: utf-8 -*-
import logging

import pytz
import time
import babel
from collections import defaultdict
from markupsafe import Markup

from odoo import _, api, fields, models, tools, _
#from odoo.addons.mail.models.mail_template import format_tz
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.translate import html_translate

from datetime import datetime
from datetime import time as datetime_time
from dateutil import relativedelta
from odoo.tools import float_compare, float_is_zero, plaintext2html

_logger = logging.getLogger(__name__)

class HrPayslipLine(models.Model):
    #_name = 'hr.payslip'
    _inherit = 'hr.payslip.line'

    @api.onchange('amount', 'total', 'write_date')
    def compute_balance(self):
        for payslip_line in self:
            if payslip_line.slip_id:
                payslip_line.slip_id.balance = 0.0
                for line in payslip_line.slip_id.line_ids:
                    if line.salary_rule_id.code == 'NET':
                        payslip_line.slip_id.balance += line.total
                if payslip_line.slip_id.payment_ids:
                    for payment in payslip_line.slip_id.payment_ids:
                        payslip_line.slip_id.balance -= payment.amount

class HrPayslip(models.Model):
    #_name = 'hr.payslip'
    _inherit = 'hr.payslip'

    #payment_id = fields.Many2one('account.payment', string='Payment', store=True, copy=False, help="Payment where the move line come from")
    payment_ids = fields.One2many('account.payment', 'payslip_id', string='Pagos', redadonly=True, copy=False)

    # state = fields.Selection([
    #     ('draft', 'Draft'),
    #     ('verify', 'Waiting'),
    #     ('done', 'Done'),
    #     ('paid', 'Paid'),
    #     ('cancel', 'Rejected'),
    # ], string='Status', index=True, readonly=True, copy=False, default='draft',
    #     help="""* When the payslip is created the status is \'Draft\'
    #             \n* If the payslip is under verification, the status is \'Waiting\'.
    #             \n* If the payslip is confirmed then status is set to \'Done\'.
    #             \n* When user cancel payslip the status is \'Rejected\'.""", track_visibility='onchange')
    total_amount = fields.Float(string='Total Amount', compute='compute_total_amount', store=True)
    balance = fields.Float(string='Balance', compute='compute_balance', store=True)

    @api.depends('line_ids')
    @api.onchange('line_ids')
    def compute_total_amount(self):
        for slip in self:
            total_amount_new = 0.0
            for line in slip.line_ids:
                if line.salary_rule_id.code == 'NET':
                    total_amount_new+=line.total
            slip.total_amount = total_amount_new

    @api.onchange('line_ids', 'payment_ids', 'state', 'write_date', 'move_id')
    def compute_balance(self):
        for slip in self:
            slip.balance = 0.0
            if slip.line_ids:
                for line in slip.line_ids:
                    if line.salary_rule_id.code == 'NET':
                        slip.balance += line.total
            if slip.payment_ids:
                for payment in slip.payment_ids:
                    slip.balance -= payment.amount

    def _prepare_line_values(self, line, account_id, date, debit, credit):
        if not line.employee_id.address_home_id:
            raise UserError(_('El empleado %s no un contacto vinculado.') % line.employee_id.name)
        return {
            'name': line.name,
            'partner_id': line.employee_id.address_home_id.id,
            'account_id': account_id,
            'journal_id': line.slip_id.struct_id.journal_id.id,
            'date': date,
            'debit': debit,
            'credit': credit,
            'analytic_distribution': (line.salary_rule_id.analytic_account_id and {line.salary_rule_id.analytic_account_id.id: 100}) or
                                     (line.slip_id.contract_id.analytic_account_id.id and {line.slip_id.contract_id.analytic_account_id.id: 100})
        }

    def _get_existing_lines(self, line_ids, line, account_id, debit, credit):
        existing_lines = (
            line_id for line_id in line_ids if
            line_id['partner_id'] == line.employee_id.address_home_id.id and
            line_id['name'] == line.name
            and line_id['account_id'] == account_id
            and ((line_id['debit'] > 0 and credit <= 0) or (line_id['credit'] > 0 and debit <= 0))
            and (
                    (
                        not line_id['analytic_distribution'] and
                        not line.salary_rule_id.analytic_account_id.id and
                        not line.slip_id.contract_id.analytic_account_id.id
                    )
                    or line_id['analytic_distribution'] and line.salary_rule_id.analytic_account_id.id in line_id['analytic_distribution']
                    or line_id['analytic_distribution'] and line.slip_id.contract_id.analytic_account_id.id in line_id['analytic_distribution']

                )
        )
        return next(existing_lines, False)
    # #@api.multi
    # def set_to_paid(self):
    #     self.write({'state': 'paid'})

class HrPayslipRun(models.Model):
    _inherit = 'hr.payslip.run'

    state = fields.Selection([
        ('draft', 'Nuevo'),
        ('verify', 'Confirmado'),
        ('close', 'Hecho'),
    ], string='Estado', index=True, readonly=True, copy=False, default='draft')

    total_amount = fields.Float(string='Total Amount', compute='compute_total_amount')

    #@api.multi
    def batch_wise_payslip_confirm(self):
        for record in self.slip_ids:
            if record.state in ['draft', 'verify']:
                record.compute_sheet()
                #record.action_payslip_done()
                if any([line.net_wage < 0 for line in self.slip_ids]):
                    raise UserError(_('Ninguna nómina debe tener negativo el salario neto.'))
            record.write({
                'state': 'done',
            })
        self.write({
            'state': 'verify',
        })

    def compute_sheet(self):
        res = super(HrPayslipRun, self).compute_sheet()
        for payslip in self.slip_ids:
            payslip.compute_sheet()
        return res

class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    payslip_id = fields.Many2one('hr.payslip', string='Expense', copy=False, help="Expense where the move line come from")

    #@api.multi
    # def reconcile(self):
    #     res = super(AccountMoveLine, self).reconcile()
    #     account_move_ids = [l.move_id.id for l in self if float_compare(l.move_id.matched_percentage, 1, precision_digits=5) == 0]
    #     if account_move_ids:
    #         payslip = self.env['hr.payslip'].search([
    #             ('move_id', 'in', account_move_ids), ('state', '=', 'done')
    #         ])
    #         payslip.set_to_paid()
    #     return res

    def reconcile(self):
        res = super(AccountMoveLine, self).reconcile()

        account_move_ids = []
        for line in self:
            if line.move_id.state == 'posted':  # Ejemplo de filtro por estado 'posted'
                account_move_ids.append(line.move_id.id)

        if account_move_ids:
            for move in account_move_ids:
                payslips = self.env['hr.payslip'].search([
                    ('move_id', '=', move), ('state', '=', 'done')
                ])
                if payslips:
                    payslips.set_to_paid()

        return res

# class HrPayslipEmployees(models.TransientModel):
#     _inherit = 'hr.payslip.employees'
#
#     def compute_sheet(self):
#         res = super(HrPayslipEmployees, self).compute_sheet()
#         for payslip in self.payslip_run.slip_ids:
#             payslip.compute_sheet()
#         return res

