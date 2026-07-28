from odoo import models
from odoo.exceptions import UserError


class HrPayslipRun(models.Model):
    _inherit = 'hr.payslip.run'

    def action_confirm_and_validate(self):
        """Calcula y confirma en un solo paso todas las nóminas del lote."""
        self.action_confirm()
        if any(slip.net_wage < 0 for slip in self.slip_ids):
            raise UserError(self.env._('Ninguna nómina debe tener el salario neto negativo.'))
        self.action_validate()
