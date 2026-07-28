# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from werkzeug import urls

_logger = logging.getLogger(__name__)


class HrPayslipRegisterPaymentWizard(models.TransientModel):
    _name = "hr.payslip.register.payment.wizard"
    _description = "Expense Report Register Payment wizard"

    @api.model
    def _default_partner_id(self):
        context = dict(self._context or {})
        active_ids = context.get('active_ids', [])
        payslips = self.env['hr.payslip'].browse(active_ids)
        return payslips.employee_id.address_home_id.id

    partner_id = fields.Many2one('res.partner', string='Partner', required=True, default=_default_partner_id)
    journal_id = fields.Many2one('account.journal', string='Payment Method', required=True, domain=[('type', 'in', ('bank', 'cash'))])
    company_id = fields.Many2one('res.company', related='journal_id.company_id', string='Company', readonly=True, required=True)
    #payment_method_id = fields.Many2one('account.payment.method', string='Payment Type', required=True, default=lambda self: self.env.ref('account.account_payment_method_manual', raise_if_not_found=False))
    amount = fields.Monetary(string='Payment Amount', required=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, default=lambda self: self.env.user.company_id.currency_id)
    payment_date = fields.Date(string='Payment Date', default=fields.Date.context_today, required=True)
    communication = fields.Char(string='Memo')
    #hide_payment_method = fields.Boolean(compute='_compute_hide_payment_method', help="Technical field used to hide the payment method if the selected journal has only one available which is 'manual'")
    payment_method_id = fields.Many2one('account.payment.method', string='Payment Type', required=True, default=lambda self: self._default_payment_method_id())

    @api.model
    def _default_payment_method_id(self):
        return self.env['account.payment.method'].browse(2)
    #@api.one
    @api.constrains('amount')
    def _check_amount(self):
        for record in self:
            if not record.amount > 0.0:
                raise ValidationError(_('The payment amount must be strictly positive.'))

    # #@api.one
    # @api.depends('journal_id')
    # def _compute_hide_payment_method(self):
    #     for record in self:
    #         if not record.journal_id:
    #             record.hide_payment_method = True
    #             return
    #         journal_payment_methods = record.journal_id.outbound_payment_method_ids
    #         record.hide_payment_method = len(journal_payment_methods) == 1 and journal_payment_methods[0].code == 'manual'

    # @api.onchange('journal_id')
    # def _onchange_journal(self):
    #     if self.journal_id:
    #         # Set default payment method (we consider the first to be the default one)
    #         payment_methods = self.journal_id.outbound_payment_method_ids
    #         self.payment_method_id = payment_methods and payment_methods[0] or False
    #         # Set payment method domain (restrict to methods enabled for the journal and to selected payment type)
    #         return {'domain': {'payment_method_id': [('payment_type', '=', 'outbound'), ('id', 'in', payment_methods.ids)]}}
    #     return {}

    def _get_payment_vals(self, payslip):
        """ Hook for extension """
        aux = 1
        return {
            'partner_type': 'supplier',
            'payment_type': 'outbound',
            'partner_id': self.partner_id.id,
            'payslip_id': payslip.id,
            'journal_id': self.journal_id.id,
            'company_id': self.company_id.id,
            'payment_method_id': self.payment_method_id.id,
            'amount': self.amount,
            'currency_id': self.currency_id.id,
            'date': self.payment_date,
            'ref': self.communication,
            'narration': 'Nomina de empleado '+self.partner_id.name+' con un monto de '+str(self.amount)+' con fecha '+str(self.payment_date),
        }

    #@api.multi
    def expense_post_payment(self):
        for record in self:
            record.ensure_one()
            context = dict(record._context or {})
            active_ids = context.get('active_ids', [])
            #payslip = record.env['hr.payslip'].browse(active_ids)
            payslip = record.env['hr.payslip'].search([('id', 'in', active_ids), ('state', '=', 'done'), ('total_amount', '>', 0.0)])
            # Create payment and post it
            #if sum(payment.amount for payment in payslip.payment_ids if payment.state == 'posted') >= payslip.total_amount:
            if sum(payment.amount for payment in payslip.payment_ids) > 0:
                #raise ValidationError(_('La nomina %s ya ha sido pagada.') % (payslip.name))
                logging.error('La nomina %s no genera un segundo pago. Este mensaje es para no detener el flujo de nominas' % (payslip.name))
            else:
                payment = record.env['account.payment'].create(record._get_payment_vals(payslip))
                if payment:
                    payment.write({'payslip_id': payslip.id})
                    #payment.action_post()
                    #payslip.write({'payment_id': payment.id})
                    payslip.write({
                    'payment_ids': [(4, payment.id)],
                    #'state': 'paid',
                    })
            # for move in payment.move_line_ids:
            #     move.name = +
            # Log the payment in the chatter
            #body = (_("A payment of %s %s with the reference <a href='/mail/view?%s'>%s</a> related to your expense %s has been made.") % (payment.amount, payment.currency_id.symbol, urls({'model': 'account.payment', 'res_id': payment.id}), payment.name, payslip.name))
            # 29 01 2025
            #body = (_("Cuerpo correo"))
            #payslip.message_post(body=body)

            # Reconcile the payment, i.e. lookup on the payable account move lines
            # account_move_lines_to_reconcile = record.env['account.move.line']
            #
            # for line in payment.line_ids + payslip.move_id.line_ids:
            #     if line.account_id.account_type in ['liability_payable', 'expense']:
            #         account_move_lines_to_reconcile |= line
            # account_move_lines_to_reconcile.reconcile()
            # if payslip.payslip_run_id:
            #     payslip_paid_search = record.env['hr.payslip'].search([('payslip_run_id', '=', payslip.payslip_run_id.id), ('state', '=', 'paid')])
            #     if payslip_paid_search:
            #         if len(payslip.payslip_run_id.slip_ids) == len(payslip_paid_search):
            #             payslip.payslip_run_id.write({'state': 'paid'})

            return {'type': 'ir.actions.act_window_close'}