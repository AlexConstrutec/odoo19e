from odoo import fields, models
from odoo.exceptions import ValidationError


class HrPayslipBatchwiseRegisterPaymentWizard(models.TransientModel):
    _name = 'hr.payslip.batchwise.register.payment.wizard'
    _description = 'Registrar Pagos de Nómina por Lote'

    batch_id = fields.Many2one('hr.payslip.run', string='Lote', required=True)
    journal_id = fields.Many2one('account.journal', string='Diario de Pago', required=True,
                                  domain=[('type', 'in', ('bank', 'cash'))])
    company_id = fields.Many2one('res.company', related='journal_id.company_id', string='Compañía', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Moneda', required=True,
                                   default=lambda self: self.env.company.currency_id)
    payment_date = fields.Date(string='Fecha de Pago', default=fields.Date.context_today, required=True)
    communication = fields.Char(string='Memo')
    payment_method_id = fields.Many2one(
        'account.payment.method', string='Método de Pago', required=True,
        default=lambda self: self.env.ref('account.account_payment_method_manual_out', raise_if_not_found=False))

    def action_register_payments(self):
        self.ensure_one()
        payslips = self.batch_id.slip_ids.filtered(lambda p: p.state == 'validated' and p.balance > 0)
        for payslip in payslips:
            if not payslip.employee_id.work_contact_id:
                raise ValidationError(self.env._('Defina un contacto para el empleado %s.', payslip.employee_id.name))

        for payslip in payslips:
            if sum(payslip.payment_ids.mapped('amount')) > 0:
                continue
            payment = self.env['account.payment'].create({
                'partner_type': 'supplier',
                'payment_type': 'outbound',
                'partner_id': payslip.employee_id.work_contact_id.id,
                'payslip_id': payslip.id,
                'journal_id': self.journal_id.id,
                'company_id': self.company_id.id,
                'payment_method_id': self.payment_method_id.id,
                'amount': payslip.balance,
                'currency_id': self.currency_id.id,
                'date': self.payment_date,
                'memo': self.communication,
            })
            payslip.write({'payment_ids': [(4, payment.id)]})
        return {'type': 'ir.actions.act_window_close'}
