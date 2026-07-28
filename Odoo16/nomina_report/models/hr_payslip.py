
import logging

from odoo import models, api, fields
from odoo.exceptions import UserError


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def fechaDel(self):
        if (self.contract_id.date_start.month >= self.date_from.month and self.contract_id.date_start.year == self.date_from.year) and self.contract_id.date_start.day >= self.date_from.day:
            format = self.contract_id.date_start.strftime('%d/%m/%Y')
        else:
            format = self.date_from.strftime('%d/%m/%Y')
        return format

    def fechaAl(self):
        if self.contract_id.date_end:
            if (self.contract_id.date_end.month <= self.date_to.month and self.contract_id.date_end.year == self.date_to.year):
                format = self.contract_id.date_end.strftime('%d/%m/%Y')
            else:
                format = self.date_to.strftime('%d/%m/%Y')
        else:
            format = self.date_to.strftime('%d/%m/%Y')
        return format
