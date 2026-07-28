from odoo import api, fields, models
from odoo.exceptions import UserError


class HrQualification(models.Model):
    _name = 'hr.qualification'
    _description = 'Calificaciones'

    name = fields.Char(string='Numero', readonly=True, index=True)
    active = fields.Boolean(string='Activo', default=True)
    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True)
    version_id = fields.Many2one('hr.version', string='Contrato', related='employee_id.version_id')
    company_id = fields.Many2one('res.company', string='Compañía', related='employee_id.company_id')
    department_id = fields.Many2one('hr.department', string='Departamento', related='employee_id.department_id')
    fecha_evaluacion = fields.Date(string='Fecha de Evaluación', required=True)
    bonificacion = fields.Float(string='Bonificación', readonly=True,
                                 related='version_id.bonificacion_productividad')
    total = fields.Float(string='Total', store=True, readonly=True, compute='_compute_total')
    calificacion = fields.Float(string='Calificación')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('done', 'Realizado'),
    ], string='Estado', default='draft')

    @api.depends('calificacion', 'bonificacion')
    def _compute_total(self):
        for record in self:
            record.total = record.bonificacion * record.calificacion

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'name' not in vals:
                sequence = self.env['ir.sequence'].next_by_code('hr.qualification.seq')
                if not sequence:
                    raise UserError(self.env._('No se ha configurado la secuencia hr.qualification.seq'))
                vals['name'] = sequence
        return super().create(vals_list)

    def approve(self):
        self.write({'state': 'done'})

    def set_draft(self):
        self.write({'state': 'draft'})
