from odoo import api, fields, models

SYNC_TRIGGER_FIELDS = {
    'contract_date_start', 'contract_date_end', 'date_version', 'wage',
    'x_bonificacion_incentivo', 'x_bonificacion_fija', 'x_bonificacion_productividad',
    'registrar_fecha_inspeccion', 'job_id', 'company_id',
}


class HrVersion(models.Model):
    _inherit = 'hr.version'

    registrar_fecha_inspeccion = fields.Boolean(
        string='Registrar fecha ante GT RECIT',
        help='Marque esta casilla si desea registrar la fecha de inspección ante GT RECIT')

    def _sync_employment_history(self):
        """Mantiene al día el snapshot de hr.employee.history.job.salary para cada versión con empleado."""
        History = self.env['hr.employee.history.job.salary']
        for version in self.filtered('employee_id'):
            vals = {
                'date_start': version.date_start,
                'date_end': version.date_end,
                'company': version.company_id.name,
                'job': version.job_id.name,
                'employee': version.employee_id.name,
                'salary': (version.wage or 0.0) + version.x_bonificacion_incentivo
                + version.x_bonificacion_fija + version.x_bonificacion_productividad,
                'identification_employee_id': version.employee_id.identification_id,
                'version_id': version.id,
                'contrato_registrado': version.registrar_fecha_inspeccion,
            }
            history = History.search([('version_id', '=', version.id)], limit=1)
            if history:
                history.write(vals)
            else:
                History.create(vals)

    @api.model_create_multi
    def create(self, vals_list):
        versions = super().create(vals_list)
        versions._sync_employment_history()
        return versions

    def write(self, vals):
        res = super().write(vals)
        if SYNC_TRIGGER_FIELDS & vals.keys():
            self._sync_employment_history()
        return res
