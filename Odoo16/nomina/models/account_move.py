from odoo import api, fields, models, _


class AccountMove(models.Model):
    _inherit = "account.move"

    slip_ids = fields.One2many('hr.payslip', 'move_id', string='Nominas', readonly=True)