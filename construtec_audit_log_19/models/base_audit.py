import logging

from odoo import api, models

from .audit_log_rule import OWN_MODELS

_logger = logging.getLogger(__name__)

# Campos técnicos que nunca aportan nada útil a una auditoría de negocio.
_ALWAYS_SKIP_FIELDS = {'write_date', 'write_uid', 'create_date', 'create_uid', '__last_update'}
# Red de seguridad: aunque no se haya excluido explícitamente en la regla, un campo cuyo
# nombre sugiere un secreto nunca se guarda en texto plano en la bitácora.
_SENSITIVE_NAME_MARKERS = ('password', 'token', 'secret', 'api_key', 'apikey')


class Base(models.AbstractModel):
    """Hook de auditoría genérico - se mezcla en TODOS los modelos del sistema (ese es el
    propósito de `_inherit = 'base'`, mismo mecanismo que usan varios módulos núcleo de Odoo
    para agregar comportamiento transversal, ej. odoo/addons/whatsapp/models/models.py,
    odoo/addons/sms/models/models.py). Es la única forma de lograr "elegir qué modelo auditar
    desde un panel de configuración, sin tocar código" - decisión confirmada con el usuario,
    entendiendo que agrega un chequeo (rápido, cacheado) a TODA escritura del sistema, no solo
    a los modelos auditados.

    El chequeo real (`_construtec_audit_rule()`) es un solo lookup en un dict cacheado en
    memoria (`AuditLogRule._get_active_rules_map()`) - para cualquier modelo sin regla activa,
    esto es una búsqueda de dict que falla y un `return False` inmediato, sin ninguna consulta
    a la base de datos ni overhead relevante."""
    _inherit = 'base'

    def _construtec_audit_rule(self):
        if not self._name or self._name in OWN_MODELS or self._transient:
            return False
        if self.env.context.get('construtec_audit_log_disable'):
            return False
        return self.env['construtec.audit.log.rule'].sudo()._get_active_rules_map().get(self._name)

    def _construtec_audit_format_value(self, field_name, value):
        field = self._fields.get(field_name)
        if field is None:
            return str(value) if value else ''
        try:
            if field.type == 'many2one':
                return value.display_name if value else ''
            if field.type in ('many2many', 'one2many'):
                return ', '.join(value.mapped('display_name')) if value else ''
            if field.type == 'selection':
                selection = field.selection
                if callable(selection):
                    selection = selection(self)
                selection_map = dict(selection) if selection else {}
                return selection_map.get(value, value) or ''
        except Exception:  # nunca dejar que un formateo raro rompa la auditoría misma
            return str(value) if value else ''
        return str(value) if value not in (False, None) else ''

    def _construtec_audit_loggable_fields(self, rule):
        excluded = rule.get('excluded_fields') or frozenset()
        result = []
        for fname, field in self._fields.items():
            if fname in _ALWAYS_SKIP_FIELDS or fname in excluded:
                continue
            if field.type == 'binary' or not field.store:
                continue
            if any(marker in fname.lower() for marker in _SENSITIVE_NAME_MARKERS):
                continue
            result.append(fname)
        return result

    def _construtec_audit_snapshot(self, fields_to_check):
        return {fname: self[fname] for fname in fields_to_check}

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        rule = records._construtec_audit_rule() if records else False
        if rule and rule.get('log_create'):
            try:
                records._construtec_audit_log_create(rule)
            except Exception:
                _logger.exception('Auditoría: fallo registrando creación en %s', records._name)
        return records

    def _construtec_audit_log_create(self, rule):
        AuditLog = self.env['construtec.audit.log'].sudo()
        fields_to_check = (
            self._construtec_audit_loggable_fields(rule) if rule.get('capture_field_values')
            else [])
        for record in self:
            lines = []
            if fields_to_check:
                for fname in fields_to_check:
                    value = record[fname]
                    if not value and value != 0:
                        continue
                    lines.append((0, 0, {
                        'field_name': fname,
                        'field_description': self._fields[fname].string,
                        'new_value': record._construtec_audit_format_value(fname, value),
                    }))
            AuditLog.create({
                'rule_id': rule['rule_id'],
                'res_model': self._name,
                'res_id': record.id,
                'res_name': record.display_name,
                'method': 'create',
                'user_id': self.env.uid,
                'line_ids': lines,
            })

    def write(self, vals):
        rule = self._construtec_audit_rule()
        before_map = {}
        fields_to_check = []
        if rule and rule.get('log_write'):
            loggable = self._construtec_audit_loggable_fields(rule)
            fields_to_check = [f for f in vals.keys() if f in loggable]
            if fields_to_check:
                for record in self:
                    try:
                        before_map[record.id] = record._construtec_audit_snapshot(fields_to_check)
                    except Exception:
                        _logger.exception(
                            'Auditoría: fallo leyendo estado previo en %s', self._name)
        res = super().write(vals)
        if before_map:
            try:
                self._construtec_audit_log_write(rule, before_map, fields_to_check)
            except Exception:
                _logger.exception('Auditoría: fallo registrando modificación en %s', self._name)
        return res

    def _construtec_audit_log_write(self, rule, before_map, fields_to_check):
        AuditLog = self.env['construtec.audit.log'].sudo()
        capture = rule.get('capture_field_values')
        for record in self:
            before = before_map.get(record.id)
            if before is None:
                continue
            lines = []
            for fname in fields_to_check:
                after_value = record[fname]
                if before[fname] == after_value:
                    continue
                lines.append((0, 0, {
                    'field_name': fname,
                    'field_description': self._fields[fname].string,
                    'old_value': (
                        record._construtec_audit_format_value(fname, before[fname])
                        if capture else ''),
                    'new_value': (
                        record._construtec_audit_format_value(fname, after_value)
                        if capture else ''),
                }))
            if not lines:
                continue
            AuditLog.create({
                'rule_id': rule['rule_id'],
                'res_model': self._name,
                'res_id': record.id,
                'res_name': record.display_name,
                'method': 'write',
                'user_id': self.env.uid,
                'line_ids': lines,
            })

    def unlink(self):
        rule = self._construtec_audit_rule()
        snapshots = {}
        if rule and rule.get('log_unlink'):
            fields_to_check = (
                self._construtec_audit_loggable_fields(rule) if rule.get('capture_field_values')
                else [])
            for record in self:
                try:
                    snapshots[record.id] = {
                        'name': record.display_name,
                        'values': record._construtec_audit_snapshot(fields_to_check),
                    }
                except Exception:
                    _logger.exception(
                        'Auditoría: fallo leyendo estado previo a eliminar en %s', self._name)
        res = super().unlink()
        if snapshots:
            try:
                self._construtec_audit_log_unlink(rule, snapshots)
            except Exception:
                _logger.exception('Auditoría: fallo registrando eliminación en %s', self._name)
        return res

    def _construtec_audit_log_unlink(self, rule, snapshots):
        AuditLog = self.env['construtec.audit.log'].sudo()
        capture = rule.get('capture_field_values')
        for res_id, snap in snapshots.items():
            lines = []
            if capture:
                for fname, value in snap['values'].items():
                    lines.append((0, 0, {
                        'field_name': fname,
                        'field_description': self._fields[fname].string,
                        'old_value': self._construtec_audit_format_value(fname, value),
                    }))
            AuditLog.create({
                'rule_id': rule['rule_id'],
                'res_model': self._name,
                'res_id': res_id,
                'res_name': snap['name'],
                'method': 'unlink',
                'user_id': self.env.uid,
                'line_ids': lines,
            })
