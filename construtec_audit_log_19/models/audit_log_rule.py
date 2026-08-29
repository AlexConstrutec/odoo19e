from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, tools
from odoo.exceptions import ValidationError

# Modelos propios de este módulo - nunca auditables (evita loop infinito: auditar la
# creación de un log generaría otro log, etc.)
OWN_MODELS = {
    'construtec.audit.log',
    'construtec.audit.log.line',
    'construtec.audit.log.rule',
}


class AuditLogRule(models.Model):
    _name = 'construtec.audit.log.rule'
    _description = 'Regla de Auditoría'
    _rec_name = 'model_id'

    model_id = fields.Many2one(
        'ir.model', string='Modelo', required=True, ondelete='cascade',
        domain=[('transient', '=', False)],
        help='Modelo de Odoo a auditar. No se pueden elegir modelos transitorios (asistentes) '
             'ni los propios modelos de este módulo de auditoría.')
    model_name = fields.Char(
        related='model_id.model', store=True, readonly=True, string='Modelo técnico')
    active = fields.Boolean(default=True, string='Activa')
    log_create = fields.Boolean(string='Auditar creación', default=True)
    log_write = fields.Boolean(string='Auditar modificación', default=True)
    log_unlink = fields.Boolean(string='Auditar eliminación', default=True)
    capture_field_values = fields.Boolean(
        string='Guardar valores de campos', default=True,
        help='Si está activo, cada creación/modificación/eliminación guarda el valor anterior y '
             'nuevo de cada campo (más útil para investigar qué pasó, más almacenamiento). Si '
             'está apagado, solo se registra que el registro fue creado/modificado/eliminado, '
             'sin detalle de campos. Los campos binarios y los que parecen contraseñas/tokens '
             'nunca se guardan, tenga esta opción el valor que tenga.')
    excluded_field_ids = fields.Many2many(
        'ir.model.fields', string='Campos excluidos',
        domain="[('model_id', '=', model_id)]",
        help='Campos de este modelo que nunca se registran, aunque "Guardar valores de campos" '
             'esté activo - útil para campos ruidosos o irrelevantes para auditoría.')
    retention_number = fields.Integer(
        string='Eliminar bitácora después de', default=0,
        help='0 = conservar indefinidamente. Junto con la unidad, define cada cuánto se '
             'autoeliminan (vía tarea planificada diaria) los registros de auditoría de ESTE '
             'modelo que ya superaron esa antigüedad.')
    retention_unit = fields.Selection(
        [('days', 'Días'), ('months', 'Meses'), ('years', 'Años')],
        string='Unidad', default='months')
    log_count = fields.Integer(compute='_compute_log_count', string='Registros en la bitácora')

    _sql_constraints = [
        ('model_uniq', 'unique(model_id)',
         'Ya existe una regla de auditoría para este modelo.'),
    ]

    @api.constrains('model_id')
    def _check_model_not_audit_log_itself(self):
        for rule in self:
            if rule.model_id.model in OWN_MODELS:
                raise ValidationError(self.env._(
                    'No se pueden auditar los propios modelos de este módulo de auditoría.'))

    def _compute_log_count(self):
        AuditLog = self.env['construtec.audit.log']
        for rule in self:
            rule.log_count = AuditLog.search_count(
                [('res_model', '=', rule.model_name)]) if rule.model_name else 0

    def action_view_logs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Bitácora de %s', self.model_id.name),
            'res_model': 'construtec.audit.log',
            'view_mode': 'list,form',
            'domain': [('res_model', '=', self.model_name)],
        }

    @api.model
    @tools.ormcache()
    def _get_active_rules_map(self):
        """Cache en memoria: {modelo_tecnico: config} - lo consulta el hook de auditoría en
        CADA create/write/unlink de CUALQUIER modelo del sistema, por eso vive cacheado (una
        consulta SQL por proceso hasta que se invalide, no una por operación). Se invalida en
        create/write/unlink de esta misma regla - ver _invalidate_rules_cache()."""
        rules = self.sudo().search([('active', '=', True)])
        return {
            rule.model_name: {
                'rule_id': rule.id,
                'log_create': rule.log_create,
                'log_write': rule.log_write,
                'log_unlink': rule.log_unlink,
                'capture_field_values': rule.capture_field_values,
                'excluded_fields': frozenset(rule.excluded_field_ids.mapped('name')),
            }
            for rule in rules
        }

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self.env.registry.clear_all_caches()
        return records

    def write(self, vals):
        res = super().write(vals)
        self.env.registry.clear_all_caches()
        return res

    def unlink(self):
        res = super().unlink()
        self.env.registry.clear_all_caches()
        return res

    @api.model
    def _cron_cleanup_logs(self):
        """Tarea planificada (ir.cron, diaria) - por cada regla con retención configurada,
        elimina los registros de bitácora de ESE modelo más viejos que la antigüedad permitida.
        Un solo cron global para todas las reglas (no uno por modelo) - misma limitación ya
        aceptada en otros crons de este workspace (ej. sync de empleados en
        construtec_account_payment_order_19): simple y suficiente para el volumen real."""
        AuditLog = self.env['construtec.audit.log'].sudo()
        for rule in self.sudo().search([('retention_number', '>', 0)]):
            cutoff = fields.Datetime.now() - relativedelta(
                **{rule.retention_unit: rule.retention_number})
            logs = AuditLog.search([
                ('res_model', '=', rule.model_name),
                ('create_date', '<', cutoff),
            ])
            if logs:
                logs.unlink()
