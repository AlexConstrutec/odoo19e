from odoo import api, fields, models
from odoo.exceptions import UserError


class SalaryAdvance(models.Model):
    _name = 'salary.advance'
    _description = 'Salary Advance'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Nombre', readonly=True, default='Adv/')
    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True)
    date = fields.Date(string='Fecha', required=True, default=fields.Date.today)
    reason = fields.Text(string='Descripcion')
    currency_id = fields.Many2one('res.currency', string='Moneda', required=True,
                                   default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one('res.company', string='Compania', required=True,
                                  default=lambda self: self.env.company)
    advance = fields.Float(string='Monto', required=True)
    exceed_condition = fields.Boolean(string='Excede el Máximo',
                                       help='El anticipo es mayor que el porcentaje máximo permitido de la estructura salarial')
    department = fields.Many2one('hr.department', string='Departmento', related='employee_id.department_id')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('approve', 'Aprobado'),
        ('cobrado', 'Cobrado'),
        ('reject', 'Rechazado'),
    ], string='Estado', default='draft')
    cheque = fields.Many2one('account.payment', string='Cheque')
    journal_id = fields.Many2one('account.journal', string='Diario', related='cheque.journal_id')
    version_id = fields.Many2one('hr.version', string='Contrato',
                                  default=lambda self: self.employee_id.version_id)
    version_is_current = fields.Boolean(string='Contrato Vigente', related='version_id.is_in_contract', readonly=True)
    tipo_anticipo = fields.Many2one('hr.tipo.anticipo', string='Tipo de Anticipo', required=True,
                                     domain="[('mostrar', '=', True)]")
    concepto = fields.Many2one('hr.concepto.anticipo', string='Concepto', required=True,
                                domain="[('mostrar', '=', True)]")
    dpi = fields.Char(string='DPI', related='employee_id.identification_id', store=True, readonly=True)

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        for advance in self:
            advance.version_id = advance.employee_id.version_id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == 'Adv/':
                vals['name'] = self.env['ir.sequence'].next_by_code('salary.advance.seq') or 'Adv/'
        return super().create(vals_list)

    def action_approve(self):
        self.write({'state': 'approve'})

    def action_reject(self):
        self.write({'state': 'reject'})

    def action_set_draft(self):
        self.filtered(lambda a: a.state != 'cobrado').write({'state': 'draft'})

    def action_set_cobrado(self):
        for advance in self:
            if advance.state != 'approve':
                raise UserError(self.env._('No se puede cobrar el anticipo, debe estar aprobado.'))
        self.write({'state': 'cobrado'})


class HrTipoAnticipo(models.Model):
    _name = 'hr.tipo.anticipo'
    _description = 'Tipo de anticipo'

    name = fields.Char(string='Nombre', required=True)
    mostrar = fields.Boolean(string='Mostrar en nómina', default=True)
    active = fields.Boolean(string='Activo', default=True)


class HrConceptoAnticipo(models.Model):
    _name = 'hr.concepto.anticipo'
    _description = 'Concepto de anticipo'

    name = fields.Char(string='Nombre', required=True)
    mostrar = fields.Boolean(string='Mostrar en nómina', default=True)
    active = fields.Boolean(string='Activo', default=True)


class HrPayrollStructure(models.Model):
    _inherit = 'hr.payroll.structure'

    max_percent = fields.Integer(string='% Máximo Anticipo Salarial')
    advance_date = fields.Integer(string='Anticipo Salarial-Después de días')
    company_id = fields.Many2one('res.company', string='Compañía', required=True,
                                  default=lambda self: self.env.company)


# class HrSalaryRule(models.Model):
#     _inherit = 'hr.salary.rule'
#
#     company_id = fields.Many2one('res.company', string='Compañía', copy=False, readonly=True,
#                                   default=lambda self: self.env.company)
