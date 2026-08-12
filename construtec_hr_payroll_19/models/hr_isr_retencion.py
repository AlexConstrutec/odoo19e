from datetime import datetime

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from .hr_loan import _siguiente_quincena


class HrIsrRetencion(models.Model):
    _name = 'hr.isr.retencion'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Retención ISR (ajuste anual repartido en quincenas)'

    @api.model
    def default_get(self, field_list):
        result = super().default_get(field_list)
        user_id = result.get('user_id') or self.env.context.get('user_id', self.env.user.id)
        result['employee_id'] = self.env['hr.employee'].search([('user_id', '=', user_id)], limit=1).id
        return result

    name = fields.Char(string='Retención ISR', default='/', readonly=True)
    date = fields.Date(string='Fecha', default=fields.Date.today, readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True)
    department_id = fields.Many2one('hr.department', related='employee_id.department_id', readonly=True,
                                     string='Departmento')
    monto_total = fields.Float(string='Monto Total ISR', required=True)
    cuotas = fields.Integer(string='Cant. Cuotas', default=24)
    fecha_inicio = fields.Date(string='Fecha inicio descuentos', required=True, default=fields.Date.today)
    isr_lines = fields.One2many('hr.isr.retencion.line', 'isr_id', string='Cuotas', index=True)
    company_id = fields.Many2one('res.company', string='Compania', readonly=True,
                                  default=lambda self: self.env.company.id)
    currency_id = fields.Many2one('res.currency', string='Moneda', required=True,
                                   default=lambda self: self.env.company.currency_id)
    job_position = fields.Many2one('hr.job', related='employee_id.job_id', readonly=True, string='Puesto')
    total_amount = fields.Float(string='Monto Total', store=True, readonly=True, compute='_compute_isr_amount')
    balance_amount = fields.Float(string='Saldo', store=True, compute='_compute_isr_amount')
    total_paid_amount = fields.Float(string='Monto Pagado', store=True, compute='_compute_isr_amount')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('waiting_approval_1', 'Confirmado'),
        ('approve', 'Aprobado'),
        ('refuse', 'Rechazado'),
        ('cancel', 'Cancelado'),
    ], string='Estado', default='draft', tracking=True, copy=False)
    dpi = fields.Char(string='DPI', related='employee_id.identification_id', store=True, readonly=True)
    version_id = fields.Many2one('hr.version', string='Contrato',
                                  default=lambda self: self.employee_id.version_id)
    version_is_current = fields.Boolean(string='Contrato Vigente', related='version_id.is_in_contract', readonly=True)
    motivo = fields.Text(string='Motivo', help='Ej. Ajuste anual de ISR 2026')

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        for isr in self:
            isr.version_id = isr.employee_id.version_id

    @api.depends('isr_lines.amount', 'isr_lines.paid')
    def _compute_isr_amount(self):
        for isr in self:
            total_paid = sum(isr.isr_lines.filtered('paid').mapped('amount'))
            isr.total_amount = isr.monto_total
            isr.total_paid_amount = total_paid
            isr.balance_amount = isr.monto_total - total_paid

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.isr.retencion.seq') or '/'
        return super().create(vals_list)

    def compute_installment(self):
        for isr in self:
            isr.isr_lines.unlink()
            date_start = datetime.strptime(str(isr.fecha_inicio), '%Y-%m-%d')
            if date_start.day not in (1, 16):
                raise UserError(self.env._(
                    'La fecha de inicio debe ser el 1 o el 16 del mes (el descuento de ISR siempre es quincenal).'))
            if not isr.cuotas:
                raise UserError(self.env._('Defina la cantidad de cuotas.'))
            amount = isr.monto_total / isr.cuotas
            lines = []
            for _i in range(isr.cuotas):
                lines.append({
                    'date': date_start,
                    'amount': amount,
                    'employee_id': isr.employee_id.id,
                    'version_id': isr.version_id.id,
                    'isr_id': isr.id,
                })
                date_start = _siguiente_quincena(date_start)
            self.env['hr.isr.retencion.line'].create(lines)

    def action_refuse(self):
        self.write({'state': 'refuse'})

    def action_submit(self):
        self.write({'state': 'waiting_approval_1'})

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def action_approve(self):
        for isr in self:
            if not isr.isr_lines:
                raise ValidationError(self.env._('Calcule las cuotas antes de aprobar.'))
            if not isr.version_id:
                raise ValidationError(self.env._('El empleado no tiene un contrato asignado.'))
        self.write({'state': 'approve'})

    def unlink(self):
        for isr in self:
            if isr.state in ('approve', 'cancel'):
                raise UserError(self.env._(
                    'No puede eliminar una retención de ISR que esté en estado aprobado o cancelado.'))
        return super().unlink()

    def write(self, vals):
        res = super().write(vals)
        for isr in self:
            if isr.isr_lines and round(sum(isr.isr_lines.mapped('amount')), 2) != round(isr.monto_total, 2):
                raise ValidationError(
                    self.env._('La sumatoria de todas las cuotas programadas debe ser igual al monto total de ISR.'))
        return res


class HrIsrRetencionLine(models.Model):
    _name = 'hr.isr.retencion.line'
    _description = 'Cuota de Retención ISR'

    date = fields.Date(string='Fecha Descuento', required=True)
    employee_id = fields.Many2one('hr.employee', string='Empleado')
    version_id = fields.Many2one('hr.version', string='Contrato',
                                  default=lambda self: self.employee_id.version_id)
    version_is_current = fields.Boolean(string='Contrato Vigente', related='version_id.is_in_contract', readonly=True)
    amount = fields.Float(string='Monto', required=True)
    paid = fields.Boolean(string='Pagado')
    isr_id = fields.Many2one('hr.isr.retencion', string='Retención ISR')
    state = fields.Selection(related='isr_id.state', string='Estado', store=True)

    def unlink(self):
        for line in self:
            if line.paid and line.isr_id.state == 'approve':
                raise UserError(self.env._('No se puede eliminar una cuota que ya ha sido pagada.'))
        return super().unlink()
