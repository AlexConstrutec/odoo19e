from odoo import models


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def fecha_del(self):
        self.ensure_one()
        inicio = self.version_id.contract_date_start
        if inicio and (inicio.year, inicio.month, inicio.day) >= (self.date_from.year, self.date_from.month, self.date_from.day):
            return inicio.strftime('%d/%m/%Y')
        return self.date_from.strftime('%d/%m/%Y')

    def fecha_al(self):
        self.ensure_one()
        fin = self.version_id.contract_date_end
        if fin and (fin.year, fin.month) <= (self.date_to.year, self.date_to.month):
            return fin.strftime('%d/%m/%Y')
        return self.date_to.strftime('%d/%m/%Y')
