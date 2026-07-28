from odoo import models, fields, api
from odoo.exceptions import UserError

class HrQualification(models.Model):
    _name = 'hr.qualification'
    _description = 'Calificaciones'

    name = fields.Char(string='Numero', store=True, readonly=True, index=True)
    active = fields.Boolean(string='Activo', default=True)
    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True)
    contract_id = fields.Many2one('hr.contract', string='Contrato', required=True, related='employee_id.contract_id')
    company_id = fields.Many2one('res.company', string='Compañía', related='employee_id.company_id')
    department_id = fields.Many2one('hr.department', string='Departamento', related='employee_id.department_id')
    fecha_evaluacion = fields.Date(string='Fecha de Evaluación', required=True, store=True)
    bonificacion = fields.Float(string='Bonificación', store=True, readonly=True, related='contract_id.bonificacion_productividad')
    total = fields.Float(string='Total', store=True, readonly=True, compute='_compute_total')
    calificacion = fields.Float(string='Calificación', store=True)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('done', 'Realizado'),
    ], string='Estado', default='draft', store=True)

    @api.depends('calificacion', 'bonificacion')
    def _compute_total(self):
        for record in self:
            record.total = record.bonificacion * record.calificacion

    @api.model
    def create(self, vals):
        # generar nombre de la calificación con la secuencia hr.qualification.seq
        if not self.env['ir.sequence'].next_by_code('hr.qualification.seq'):
            raise UserError('No se ha configurado la secuencia hr.qualification.seq')
        vals['name'] = self.env['ir.sequence'].next_by_code('hr.qualification.seq') or ' '
        res_id = super(HrQualification, self).create(vals)
        return res_id

    def write(self, vals):
        res = super(HrQualification, self).write(vals)
        return res

    def approve(self):
        for record in self:
            record.state = 'done'

    def set_draft(self):
        for record in self:
            record.state = 'draft'
