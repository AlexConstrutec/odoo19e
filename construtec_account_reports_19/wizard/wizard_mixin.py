import base64
import io

from odoo import fields, models
from odoo.exceptions import ValidationError

MESES = [
    ('1', 'Enero'), ('2', 'Febrero'), ('3', 'Marzo'), ('4', 'Abril'),
    ('5', 'Mayo'), ('6', 'Junio'), ('7', 'Julio'), ('8', 'Agosto'),
    ('9', 'Septiembre'), ('10', 'Octubre'), ('11', 'Noviembre'), ('12', 'Diciembre'),
]


class FinancialReportWizardMixin(models.AbstractModel):
    _name = 'construtec.financial.report.wizard.mixin'
    _description = 'Mixin común para los wizards de reportes financieros'

    company_id = fields.Many2one('res.company', string='Compañía', default=lambda self: self.env.company)
    state = fields.Selection([('choose', 'Elegir'), ('get', 'Descargar')], default='choose')
    name = fields.Char(string='Archivo')
    data = fields.Binary(string='Archivo')

    def got_back(self):
        self.ensure_one()
        self.state = 'choose'
        return self._reopen()

    def _reopen(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def check_date(self):
        for wizard in self:
            if wizard.date_start and wizard.date_end and wizard.date_end < wizard.date_start:
                raise ValidationError(self.env._('La fecha final debe ser posterior o igual a la fecha inicial.'))

    @staticmethod
    def new_workbook():
        import xlsxwriter
        buffer = io.BytesIO()
        workbook = xlsxwriter.Workbook(buffer, {'in_memory': True})
        return buffer, workbook

    def finalize_workbook(self, buffer, workbook, filename):
        self.ensure_one()
        workbook.close()
        self.write({
            'data': base64.b64encode(buffer.getvalue()),
            'name': filename,
            'state': 'get',
        })
        return self._reopen()
