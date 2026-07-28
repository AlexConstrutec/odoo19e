import base64
import io

from odoo import fields, models
from odoo.exceptions import ValidationError


class NominaReportWizardMixin(models.AbstractModel):
    _name = 'construtec.nomina.report.wizard.mixin'
    _description = 'Mixin común para los wizards de reportes de nómina'

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
        """Crea un libro xlsxwriter en memoria (sin archivos temporales)."""
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

    def analytic_account(self, analytic_distribution):
        """Devuelve la primera cuenta analítica de un campo analytic_distribution (JSON {account_id: pct})."""
        if not analytic_distribution:
            return self.env['account.analytic.account']
        account_id = next(iter(analytic_distribution.keys()), None)
        return self.env['account.analytic.account'].browse(int(account_id)) if account_id else self.env['account.analytic.account']

    @staticmethod
    def selection_label(record, field_name):
        if not record:
            return ''
        selection = record._fields[field_name].selection
        if callable(selection):
            selection = selection(record)
        return dict(selection).get(record[field_name]) or ''
