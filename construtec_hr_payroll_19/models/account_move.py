from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    slip_ids = fields.One2many('hr.payslip', 'move_id', string='Nóminas', readonly=True)


# class AccountMoveLine(models.Model):
#     _inherit = 'account.move.line'
#
#     payslip_id = fields.Many2one('hr.payslip', string='Nómina', copy=False)
#
#     def reconcile(self):
#         res = super().reconcile()
#         posted_moves = self.move_id.filtered(lambda m: m.state == 'posted')
#         if posted_moves:
#             payslips = self.env['hr.payslip'].search([
#                 ('move_id', 'in', posted_moves.ids),
#                 ('state', '=', 'validated'),
#             ])
#             payslips.action_payslip_paid()
#         return res
