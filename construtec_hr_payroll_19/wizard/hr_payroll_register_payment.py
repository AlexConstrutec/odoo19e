from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrPayslipRegisterPaymentWizard(models.TransientModel):
    _name = 'hr.payslip.register.payment.wizard'
    _description = 'Registrar Pago de Nómina'

    @api.model
    def _default_payslip(self):
        return self.env['hr.payslip'].browse(self.env.context.get('active_ids', []))

    @api.model
    def _default_partner_id(self):
        return self._default_payslip().employee_id.work_contact_id.id

    @api.model
    def _default_amount(self):
        return sum(self._default_payslip().mapped('balance'))

    partner_id = fields.Many2one('res.partner', string='Contacto', required=True, default=_default_partner_id)
    journal_id = fields.Many2one('account.journal', string='Diario de Pago', required=True,
                                  domain=[('type', 'in', ('bank', 'cash'))])
    company_id = fields.Many2one('res.company', related='journal_id.company_id', string='Compañía', readonly=True)
    amount = fields.Monetary(string='Monto a Pagar', required=True, default=_default_amount)
    currency_id = fields.Many2one('res.currency', string='Moneda', required=True,
                                   default=lambda self: self.env.company.currency_id)
    payment_date = fields.Date(string='Fecha de Pago', default=fields.Date.context_today, required=True)
    communication = fields.Char(string='Memo')
    payment_method_id = fields.Many2one(
        'account.payment.method', string='Método de Pago', required=True,
        default=lambda self: self.env.ref('account.account_payment_method_manual_in', raise_if_not_found=False))

    @api.constrains('amount')
    def _check_amount(self):
        for record in self:
            if record.amount <= 0.0:
                raise ValidationError(self.env._('El monto del pago debe ser mayor a cero.'))

    def _get_payment_vals(self, payslip):
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
        }

    def action_register_payment(self):
        self.ensure_one()
        payslip = self._default_payslip().filtered(lambda p: p.state == 'validated')
        if not payslip or sum(payslip.payment_ids.mapped('amount')) > 0:
            return {'type': 'ir.actions.act_window_close'}
        payment = self.env['account.payment'].create(self._get_payment_vals(payslip))
        payslip.write({'payment_ids': [(4, payment.id)]})
        return {'type': 'ir.actions.act_window_close'}
