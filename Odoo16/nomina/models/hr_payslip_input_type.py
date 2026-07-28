from odoo import models, fields


class HrPayslipInputType(models.Model):
    _inherit = 'hr.payslip.input.type'

    active = fields.Boolean('Active', default=True, store=True)