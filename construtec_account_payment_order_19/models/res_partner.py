from odoo import api, fields, models

from .account_payment_order import _resolve_employee_for_partner


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # No se crea un campo nuevo para el puesto - `function` ("Job Position") ya existe de serie
    # en res.partner (base) y está disponible tanto en Community como en Enterprise. Se
    # redeclara aquí con compute+store para que se autocomplete desde el hr.employee vinculado;
    # `readonly=False` (mismo patrón que `crm.lead.function`, ver `..\odoo\addons\crm\models\
    # crm_lead.py`) para que un usuario todavía pueda corregirlo a mano si hiciera falta - solo
    # se recalcula cuando cambia una dependencia real (el hr.employee vinculado), nunca pisa un
    # valor manual de un contacto que NO es empleado (employee_ids vacío nunca dispara el compute).
    function = fields.Char(compute='_compute_employee_job_info', compute_sudo=True, store=True,
                            readonly=False)
    employee_department_id = fields.Many2one(
        'hr.department', string='Departamento (Empleado)', compute='_compute_employee_job_info',
        compute_sudo=True, store=True,
        help='Heredado automáticamente del hr.employee vinculado (ver '
             '_resolve_employee_for_partner en account_payment_order.py) - se guarda '
             'aquí, en el Contacto, para que exista incluso donde no se pueda resolver un '
             'hr.employee en vivo (ej. Community, que solo tiene un espejo limitado). Si este '
             'contacto es empleado en más de una compañía, se usa el mismo criterio de '
             'desempate: el hr.employee de la compañía ACTUAL (self.env.company), o si no hay '
             'match, el primero activo - un solo valor por contacto, no uno por compañía '
             '(decisión explícita del usuario: la mayoría de contactos solo tiene un empleo). '
             'No hay un campo nativo de "departamento" en res.partner para reusar - a '
             'diferencia de `function`, este sí es un campo nuevo de este módulo.')

    @api.depends('employee_ids.department_id', 'employee_ids.job_title', 'employee_ids.company_id')
    def _compute_employee_job_info(self):
        """Mismo patrón que `crm.lead._compute_function()` (Odoo core, `..\\odoo\\addons\\crm\\
        models\\crm_lead.py`) para un compute+store+readonly=False: solo pisa `function` si el
        contacto todavía no tenía nada, o si el empleado sí trae un puesto - nunca borra un
        valor puesto a mano en un contacto que dejó de tener empleado. Un contacto que nunca
        tuvo hr.employee vinculado (`employee_ids` vacío, la inmensa mayoría) nunca entra por
        aquí con un `employee` real, así que su `function` jamás se toca."""
        for partner in self:
            employee = _resolve_employee_for_partner(partner, self.env.company)
            partner.employee_department_id = employee.department_id
            if not partner.function or employee.job_title:
                partner.function = employee.job_title or partner.function
