from odoo import api, fields, models

from .account_payment_order_request import _resolve_employee_for_partner


class ResPartner(models.Model):
    _inherit = 'res.partner'

    employee_department_id = fields.Many2one(
        'hr.department', string='Departamento (Empleado)', compute='_compute_employee_job_info',
        compute_sudo=True, store=True,
        help='Heredado automáticamente del hr.employee vinculado (ver '
             '_resolve_employee_for_partner en account_payment_order_request.py) - se guarda '
             'aquí, en el Contacto, para que exista incluso donde no se pueda resolver un '
             'hr.employee en vivo (ej. Community, que solo tiene un espejo limitado). Si este '
             'contacto es empleado en más de una compañía, se usa el mismo criterio de '
             'desempate: el hr.employee de la compañía ACTUAL (self.env.company), o si no hay '
             'match, el primero activo - un solo valor por contacto, no uno por compañía '
             '(decisión explícita del usuario: la mayoría de contactos solo tiene un empleo).')
    employee_job_title = fields.Char(
        string='Puesto (Empleado)', compute='_compute_employee_job_info', compute_sudo=True,
        store=True, help='Ver employee_department_id - mismo criterio.')

    @api.depends('employee_ids.department_id', 'employee_ids.job_title', 'employee_ids.company_id')
    def _compute_employee_job_info(self):
        for partner in self:
            employee = _resolve_employee_for_partner(partner, self.env.company)
            partner.employee_department_id = employee.department_id
            partner.employee_job_title = employee.job_title
