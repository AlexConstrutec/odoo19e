# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Distribución analítica del Departamento, heredada por el empleado (2026-11-17).

Vive en el módulo compartido para existir igual en Enterprise y en Community. En Enterprise la versión
del empleado (`hr.version`) ya trae `analytic_distribution` por `hr_payroll_account`; en Community no
(no hay nómina), así que aquí se declara con el mismo mixin y el mismo grupo para que ambos lados
queden iguales."""
from odoo import api, fields, models


class HrDepartment(models.Model):
    _name = 'hr.department'
    _inherit = ['hr.department', 'analytic.mixin']


class HrVersion(models.Model):
    _name = 'hr.version'
    _inherit = ['hr.version', 'analytic.mixin']

    analytic_distribution = fields.Json(groups='hr.group_hr_user', tracking=False)
    analytic_precision = fields.Integer(groups='hr.group_hr_user', tracking=False)
    distribution_analytic_account_ids = fields.Many2many(groups='hr.group_hr_user', tracking=False)

    @api.model_create_multi
    def create(self, vals_list):
        """Una versión nueva con departamento y sin distribución propia toma la del departamento."""
        for vals in vals_list:
            if vals.get('department_id') and not vals.get('analytic_distribution'):
                distribucion = self.env['hr.department'].sudo().browse(
                    vals['department_id']).analytic_distribution
                if distribucion:
                    vals['analytic_distribution'] = dict(distribucion)
        return super().create(vals_list)

    def write(self, vals):
        """Al CAMBIAR el departamento, la versión toma la distribución del departamento nuevo (después
        es editable). Solo cuando el departamento realmente cambia: la sincronización de empleados
        reescribe el mismo departamento cada vez y no debe pisar la distribución propia del empleado.
        Un departamento sin distribución conserva la que el empleado ya tenía. Si cambia luego la
        distribución del departamento, las de los empleados no se tocan."""
        cambia = 'department_id' in vals and 'analytic_distribution' not in vals
        anteriores = {v.id: v.department_id.id for v in self} if cambia else {}
        res = super().write(vals)
        if cambia:
            for version in self:
                if version.department_id.id != anteriores[version.id]:
                    distribucion = version.department_id.sudo().analytic_distribution
                    if distribucion:
                        version.analytic_distribution = dict(distribucion)
        return res


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    muestra_distribucion_analitica = fields.Boolean(
        compute='_compute_muestra_distribucion_analitica',
        help='En Enterprise la ficha ya muestra la distribución en la pestaña de nómina '
             '(`hr_payroll_account`); este campo evita mostrarla dos veces. En Community no hay '
             'nómina y se muestra en la pestaña Trabajo.')

    def _compute_muestra_distribucion_analitica(self):
        sin_nomina = 'hr.payslip' not in self.env
        for employee in self:
            employee.muestra_distribucion_analitica = sin_nomina
