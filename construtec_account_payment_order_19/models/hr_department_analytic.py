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

    @api.depends('department_id')
    def _compute_analytic_distribution(self):
        """Al elegir (o cambiar) el departamento, la versión toma la distribución del departamento. Es
        editable después. Depende solo de `department_id` y no de la distribución del departamento: si
        esta cambia más tarde, las distribuciones propias de cada empleado no se pisan. Un departamento
        sin distribución conserva la que el empleado ya tenía."""
        for version in self:
            distribucion = version.department_id.sudo().analytic_distribution
            if distribucion:
                version.analytic_distribution = dict(distribucion)
            elif not version.analytic_distribution:
                version.analytic_distribution = False


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
