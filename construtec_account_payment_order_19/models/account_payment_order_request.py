from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from ..tools.enterprise_sync_api import EnterpriseSyncError, create_sync_record

APPROVER_GROUP_XMLID = 'construtec_account_payment_order_19.group_payment_order_approver'
APPROVER_MEDIO_GROUP_XMLID = 'construtec_account_payment_order_19.group_payment_order_approver_medio'
APPROVER_ALTO_GROUP_XMLID = 'construtec_account_payment_order_19.group_payment_order_approver_alto'


class AccountPaymentOrderRequest(models.Model):
    _name = 'account.payment.order.request'
    _description = 'Solicitud de Pago'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(string='Referencia', default='/', readonly=True, copy=False)
    external_ref = fields.Char(
        string='Referencia de Origen', readonly=True, copy=False,
        help='Referencia (nombre/secuencia) que tenía esta Solicitud en la instalación donde '
             'se creó originalmente, si llegó por sincronización.')
    company_id = fields.Many2one('res.company', string='Compañía', required=True,
                                  default=lambda self: self.env.company)
    origin = fields.Selection([
        ('local', 'Local'),
        ('synced', 'Sincronizada'),
    ], string='Origen', default='local', required=True, readonly=True, copy=False)

    justificacion_tipo_id = fields.Many2one(
        'account.payment.order.justification.type', string='Tipo de Gasto', required=True,
        default=lambda self: self.env.ref(
            'construtec_account_payment_order_19.justification_type_viaticos', raise_if_not_found=False),
        help='Catálogo (no un Selection fijo) para poder agregar tipos nuevos sin tocar código '
             '- p. ej. "Materiales" en una fase futura (migración de construtec_materials_19). '
             'Nunca se envía como id a la instalación Procesadora, solo el nombre - ver '
             '_prepare_sync_vals()/create().')
    es_viaticos = fields.Boolean(
        compute='_compute_es_viaticos',
        help='Auxiliar para mostrar/ocultar la pestaña "Viáticos" - comparar contra un id no es '
             'seguro en una vista (`invisible=`), así que se resuelve aquí en Python.')
    es_procesador = fields.Boolean(
        compute='_compute_es_procesador',
        help='Auxiliar para mostrar/ocultar Aprobar/Rechazar/Crear Anticipo según el rol de la '
             'compañía - una vista no puede navegar `company_id.payment_order_role` directo en '
             '`invisible=`, así que se resuelve aquí. Decisión explícita del usuario: la '
             'aprobación ahora ocurre solo en la instalación Procesadora (Enterprise); una '
             'instalación Solicitante (Community) nunca debe ver estos botones.')

    requested_by_id = fields.Many2one('res.users', string='Solicitado por',
                                       default=lambda self: self.env.user, readonly=True, copy=False)
    requested_by_name = fields.Char(string='Nombre', default=lambda self: self.env.user.name)
    employee_id = fields.Many2one(
        'hr.employee', string='Empleado Solicitante', readonly=True,
        default=lambda self: self.env['hr.employee'].search(
            [('user_id', '=', self.env.user.id)], limit=1),
        help='Empleado vinculado al usuario que solicita (sincronizado desde Enterprise - ver '
             'res.company._sync_employees_from_enterprise). Se fija automáticamente al crear y '
             'no se puede modificar después (ver write()) para evitar suplantación - llena '
             'departamento/puesto/cuenta bancaria como texto plano, y además viaja como '
             '`employee_enterprise_ref` (el id ORIGINAL de este empleado en Enterprise, ver '
             '`enterprise_employee_ref` en hr_employee.py) para que la instalación Procesadora '
             'pueda resolver un `employee_id` real allá - a diferencia de otros ids en este '
             'módulo, este SÍ es válido en ambas bases porque es literalmente de dónde vino.')
    puesto = fields.Char(string='Puesto')
    departamento = fields.Char(string='Departamento')
    analytic_account_id = fields.Many2one(
        'account.analytic.account', string='Cuenta Analítica',
        help='Sincronizada desde Enterprise. Solo llena el campo de texto "Proyecto" '
             'automáticamente; no se envía ningún id a la instalación Procesadora.')
    proyecto = fields.Char(string='Proyecto')
    telefono = fields.Char(string='Teléfono')
    correo = fields.Char(string='Correo', default=lambda self: self.env.user.email)

    request_date = fields.Date(string='Fecha de Solicitud', default=fields.Date.context_today)
    cuenta_acreditar = fields.Char(
        string='Cuenta a Acreditar', readonly=True,
        help='Se autocompleta desde la cuenta bancaria del empleado solicitante en Enterprise - '
             'no editable, para evitar que una solicitud acredite a una cuenta distinta a la del '
             'empleado real.')
    tipo_cuenta = fields.Selection([
        ('monetaria', 'Monetaria'),
        ('ahorro', 'Ahorro'),
    ], string='Tipo de Cuenta')
    banco = fields.Char(string='Banco', readonly=True)
    periodo_del = fields.Date(string='Del')
    periodo_al = fields.Date(string='Al')
    observaciones = fields.Text(string='Observaciones / Instrucciones')

    viaticos_line_ids = fields.One2many(
        'account.payment.order.request.line', 'request_id', string='Líneas de Viáticos')
    anticipo_previo = fields.Float(string='Anticipo')
    subtotal = fields.Float(string='Subtotal', compute='_compute_totales', store=True)
    total_acreditar = fields.Float(string='Total a Acreditar', compute='_compute_totales', store=True)

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('submitted', 'Enviada'),
        ('approved', 'Aprobada'),
        ('rejected', 'Rechazada'),
        ('cancel', 'Cancelada'),
    ], default='draft', required=True, tracking=True, copy=False)
    submit_date = fields.Datetime(string='Fecha de Envío', readonly=True, copy=False)
    approved_by_id = fields.Many2one('res.users', string='Aprobado por', readonly=True, copy=False)
    approve_date = fields.Datetime(string='Fecha de Aprobación', readonly=True, copy=False)
    rejected_by_id = fields.Many2one('res.users', string='Rechazado por', readonly=True, copy=False)
    reject_date = fields.Datetime(string='Fecha de Rechazo', readonly=True, copy=False)
    reject_reason = fields.Text(string='Motivo de Rechazo')

    sync_state = fields.Selection([
        ('not_synced', 'No Sincronizada'),
        ('synced', 'Sincronizada'),
        ('error', 'Error de Sincronización'),
    ], string='Sincronización', default='not_synced', copy=False, tracking=True)
    sync_error = fields.Text(string='Detalle del Error de Sincronización', readonly=True, copy=False)
    sync_date = fields.Datetime(string='Fecha de Sincronización', readonly=True, copy=False)

    payment_order_id = fields.Many2one('account.payment.order', string='Orden de Pago',
                                        readonly=True, copy=False)

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        for rec in self:
            if rec.employee_id:
                # job_title/department_id viven en hr.version y requieren el grupo "Employees
                # Officer" para leerse directo - sudo() aqui porque cualquier solicitante debe
                # poder ver estos datos no sensibles de SU PROPIO empleado vinculado.
                employee = rec.employee_id.sudo()
                rec.puesto = employee.job_title or rec.puesto
                rec.departamento = employee.department_id.name or rec.departamento
                # cuenta_bancaria/banco_nombre/telefono_personal solo resuelven a un valor real
                # cuando employee_id es el empleado vinculado al usuario actual - hr_employee.py.
                rec.cuenta_acreditar = rec.employee_id.cuenta_bancaria or rec.cuenta_acreditar
                rec.banco = rec.employee_id.banco_nombre or rec.banco
                # Teléfono: trabajo (work_phone) -> celular de trabajo (mobile_phone) ->
                # personal (private_phone), campos nativos de hr.employee. sudo() porque
                # private_phone requiere hr.group_hr_user para leerse directo.
                rec.telefono = (employee.work_phone or employee.mobile_phone
                                 or employee.private_phone or rec.telefono)
                # Correo: de trabajo -> personal, mismo criterio que teléfono.
                rec.correo = employee.work_email or employee.private_email or rec.correo

    @api.depends('justificacion_tipo_id')
    def _compute_es_viaticos(self):
        viaticos_type = self.env.ref(
            'construtec_account_payment_order_19.justification_type_viaticos', raise_if_not_found=False)
        for rec in self:
            rec.es_viaticos = bool(viaticos_type) and rec.justificacion_tipo_id == viaticos_type

    @api.depends('company_id.payment_order_role')
    def _compute_es_procesador(self):
        for rec in self:
            rec.es_procesador = rec.company_id.payment_order_role == 'procesador'

    @api.onchange('analytic_account_id')
    def _onchange_analytic_account_id(self):
        for rec in self:
            if rec.analytic_account_id:
                rec.proyecto = rec.analytic_account_id.name

    @api.depends('viaticos_line_ids.total', 'anticipo_previo')
    def _compute_totales(self):
        for rec in self:
            subtotal = sum(rec.viaticos_line_ids.mapped('total'))
            rec.subtotal = subtotal
            rec.total_acreditar = subtotal - rec.anticipo_previo

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'account.payment.order.request.sequence') or '/'
            self._resolve_justificacion_tipo_name(vals)
            self._resolve_employee_enterprise_ref(vals)
            self._resolve_company_enterprise_ref(vals)
            self._fill_derived_vals_from_employee(vals)
            self._fill_derived_vals_from_analytic_account(vals)
        return super().create(vals_list)

    def _resolve_employee_enterprise_ref(self, vals):
        """Resuelve `employee_enterprise_ref` (el id ORIGINAL de este empleado en Enterprise,
        enviado por _prepare_sync_vals()) hacia un `employee_id` real de ESTA base - a
        diferencia de justificacion_tipo/analytic_account (que se resuelven por NOMBRE, ya que
        no hay ninguna referencia cruzada previa), aquí sí hay un id genuinamente válido en
        ambos lados porque es literalmente el id del empleado tal como existe en Enterprise. Si
        el empleado se resuelve, también se usa su compañía real para `company_id` - más preciso
        que el respaldo de `_resolve_company_enterprise_ref()`."""
        ref = vals.pop('employee_enterprise_ref', None)
        if ref and not vals.get('employee_id'):
            employee = self.env['hr.employee'].browse(int(ref)).exists()
            if employee:
                vals['employee_id'] = employee.id
                vals.setdefault('company_id', employee.company_id.id)

    def _resolve_company_enterprise_ref(self, vals):
        """Respaldo de compañía (`res.company.payment_order_default_company_id`, configurado en
        la instalación Solicitante) para cuando el empleado no se pudo resolver arriba - ej. la
        Solicitud llegó de un usuario todavía no sincronizado. No-op si `company_id` ya quedó
        resuelto por el empleado."""
        ref = vals.pop('company_enterprise_ref', None)
        if ref and not vals.get('company_id'):
            company = self.env['res.company'].browse(int(ref)).exists()
            if company:
                vals['company_id'] = company.id

    def _resolve_justificacion_tipo_name(self, vals):
        """Resuelve `justificacion_tipo_name` (texto plano, lo único que viaja desde la
        instalación Solicitante - ver _prepare_sync_vals()) hacia un `justificacion_tipo_id`
        real de ESTA base, buscando/creando por nombre. No-op si ya viene un id (creación
        local normal, vía formulario)."""
        name = vals.pop('justificacion_tipo_name', None)
        if name and not vals.get('justificacion_tipo_id'):
            justification_type = self.env['account.payment.order.justification.type']._find_or_create_by_name(name)
            vals['justificacion_tipo_id'] = justification_type.id

    def _fill_derived_vals_from_employee(self, vals):
        """Same autocompletado que _onchange_employee_id, pero para create() por API/script
        (el onchange solo corre en el formulario web)."""
        employee_id = vals.get('employee_id')
        if not employee_id:
            employee_id = self.default_get(['employee_id']).get('employee_id')
        if not employee_id:
            return
        employee = self.env['hr.employee'].browse(employee_id)
        vals.setdefault('employee_id', employee.id)
        # job_title/department_id requieren sudo() - ver _onchange_employee_id.
        vals.setdefault('puesto', employee.sudo().job_title or False)
        vals.setdefault('departamento', employee.sudo().department_id.name or False)
        vals.setdefault('cuenta_acreditar', employee.cuenta_bancaria or False)
        vals.setdefault('banco', employee.banco_nombre or False)
        vals.setdefault('telefono', employee.sudo().work_phone or employee.sudo().mobile_phone
                        or employee.sudo().private_phone or False)
        vals.setdefault('correo', employee.sudo().work_email or employee.sudo().private_email or False)

    def _fill_derived_vals_from_analytic_account(self, vals):
        analytic_account_id = vals.get('analytic_account_id')
        if not analytic_account_id:
            return
        analytic_account = self.env['account.analytic.account'].browse(analytic_account_id)
        vals.setdefault('proyecto', analytic_account.name)

    def write(self, vals):
        if 'employee_id' in vals and not self.env.user.has_group(APPROVER_GROUP_XMLID):
            for rec in self:
                if rec.employee_id and vals['employee_id'] != rec.employee_id.id:
                    raise UserError(self.env._(
                        'No se puede cambiar el empleado de una Solicitud de Pago ya creada '
                        '- cree una nueva solicitud en su lugar.'))
        return super().write(vals)

    def unlink(self):
        for rec in self:
            if rec.state not in ('draft', 'cancel', 'rejected'):
                raise UserError(self.env._(
                    'No puede eliminar una Solicitud de Pago que no esté en borrador, '
                    'cancelada o rechazada.'))
        return super().unlink()

    def _check_is_approver(self):
        if not self.env.user.has_group(APPROVER_GROUP_XMLID):
            raise AccessError(self.env._(
                'Solo un usuario autorizado puede aprobar o rechazar Solicitudes de Pago.'))

    def _check_is_approver_for_amount(self):
        """Gate por monto para action_approve(): Nivel Alto (Gerente de Área) siempre puede
        aprobar (implica Nivel Medio); Nivel Medio (Jefe de Área) solo si el Total a Acreditar
        es menor al umbral configurado en la compañía. Se revisa registro por registro porque
        el monto varía por Solicitud."""
        self.ensure_one()
        threshold = self.company_id.payment_order_approval_threshold or 0.0
        if self.total_acreditar >= threshold:
            if not self.env.user.has_group(APPROVER_ALTO_GROUP_XMLID):
                raise AccessError(self.env._(
                    'La Solicitud %(name)s (Q%(monto).2f) es mayor o igual al umbral de '
                    'Q%(umbral).2f - solo un Aprobador Nivel Alto (Gerente de Área) puede '
                    'aprobarla.', name=self.name, monto=self.total_acreditar, umbral=threshold))
        elif not self.env.user.has_group(APPROVER_MEDIO_GROUP_XMLID):
            raise AccessError(self.env._(
                'Solo un Aprobador Nivel Medio (Jefe de Área) o superior puede aprobar '
                'Solicitudes de Pago.'))

    def action_submit(self):
        for rec in self:
            if rec.es_viaticos and not rec.viaticos_line_ids:
                raise UserError(self.env._(
                    'Agregue al menos una línea de viáticos antes de enviar la solicitud.'))
            if rec.viaticos_line_ids.filtered(lambda line: not line.employee_id):
                raise UserError(self.env._(
                    'Todas las líneas de viáticos deben tener un empleado seleccionado antes '
                    'de enviar la solicitud.'))
            if not (rec.cuenta_acreditar and rec.tipo_cuenta and rec.banco
                    and rec.periodo_del and rec.periodo_al):
                raise UserError(self.env._(
                    'Complete cuenta a acreditar, tipo de cuenta, banco y el período antes de '
                    'enviar la solicitud.'))
            rec.write({'state': 'submitted', 'submit_date': fields.Datetime.now()})
        # La sincronización ahora ocurre al enviar, no al aprobar - la aprobación (Nivel Medio/
        # Alto) pasó a ocurrir en la instalación Procesadora (Enterprise), donde están los
        # usuarios administrativos reales. En una instalación Procesadora esto es un no-op
        # (_sync_to_enterprise() solo actúa si payment_order_role == 'solicitante').
        self._sync_to_enterprise()

    def action_approve(self):
        for rec in self:
            rec._check_is_approver_for_amount()
            rec.write({
                'state': 'approved',
                'approved_by_id': self.env.user.id,
                'approve_date': fields.Datetime.now(),
            })

    def action_reject(self):
        self._check_is_approver()
        for rec in self:
            rec.write({
                'state': 'rejected',
                'rejected_by_id': self.env.user.id,
                'reject_date': fields.Datetime.now(),
            })

    def action_reset_to_draft(self):
        for rec in self:
            rec.write({
                'state': 'draft',
                'approved_by_id': False,
                'rejected_by_id': False,
                'reject_reason': False,
            })

    def action_cancel(self):
        for rec in self:
            rec.state = 'cancel'

    def _prepare_sync_vals(self):
        """Snapshot plano (sin ids) para crear el registro correspondiente en la instalación
        Procesadora - incluso siendo el mismo modelo en ambos lados, un id de res.company/
        res.users de esta base no significa nada en la otra.

        Excepción deliberada: `employee_enterprise_ref`/`company_enterprise_ref` SÍ son ids,
        pero válidos en ambos lados porque son literalmente los ids que Enterprise usa para ese
        empleado/compañía (el empleado se sincronizó DESDE ahí - ver
        `enterprise_employee_ref` en hr_employee.py). No es lo mismo que enviar un id local de
        esta base (que no significaría nada allá)."""
        self.ensure_one()
        return {
            'external_ref': self.name,
            'origin': 'synced',
            'justificacion_tipo_name': self.justificacion_tipo_id.name or '',
            'requested_by_name': self.requested_by_name or '',
            'employee_enterprise_ref': self.employee_id.enterprise_employee_ref or False,
            'company_enterprise_ref':
                self.company_id.payment_order_default_company_id.enterprise_company_ref or False,
            'puesto': self.puesto or '',
            'departamento': self.departamento or '',
            'proyecto': self.proyecto or '',
            'telefono': self.telefono or '',
            'correo': self.correo or '',
            'request_date': self.request_date and self.request_date.isoformat() or False,
            'cuenta_acreditar': self.cuenta_acreditar or '',
            'tipo_cuenta': self.tipo_cuenta,
            'banco': self.banco or '',
            'periodo_del': self.periodo_del and self.periodo_del.isoformat() or False,
            'periodo_al': self.periodo_al and self.periodo_al.isoformat() or False,
            'observaciones': self.observaciones or '',
            'anticipo_previo': self.anticipo_previo,
            # 'submitted', no 'approved': la aprobación ahora ocurre en la instalación
            # Procesadora (Enterprise), donde están los usuarios Nivel Medio/Alto reales - ver
            # action_submit()/action_approve() más abajo.
            'state': 'submitted',
            'submit_date': fields.Datetime.to_string(fields.Datetime.now()),
            'viaticos_line_ids': [
                (0, 0, {
                    'tecnico_name': line.tecnico_name or '',
                    'employee_enterprise_ref': line.employee_id.enterprise_employee_ref or False,
                    'departamento': line.departamento or '',
                    'puesto': line.puesto or '',
                    'justificacion_tipo_name': line.justificacion_tipo_id.name or '',
                    'cantidad': line.cantidad,
                    'costo_individual': line.costo_individual,
                })
                for line in self.viaticos_line_ids
            ],
        }

    def _sync_to_enterprise(self):
        """Empuja esta Solicitud (recién enviada, `state='submitted'`) hacia la instalación
        Procesadora configurada - se llama desde action_submit(), no action_approve(): la
        aprobación ocurre en Enterprise, no aquí (decisión explícita del usuario).

        Nunca lanza: los fallos quedan registrados en el propio registro (sync_state='error')
        para el cron de reintento, sin bloquear action_submit()."""
        for rec in self:
            company = rec.company_id
            if company.payment_order_role != 'solicitante' or not company.payment_order_sync_enabled:
                continue
            try:
                remote_id = create_sync_record(
                    company.payment_order_sync_url,
                    company.payment_order_sync_db,
                    company.payment_order_sync_login,
                    company.payment_order_sync_api_key,
                    rec._prepare_sync_vals(),
                )
            except EnterpriseSyncError as exc:
                rec.write({'sync_state': 'error', 'sync_error': str(exc)})
                company._payment_order_sync_log(
                    False, self.env._('Error al sincronizar %(name)s: %(error)s', name=rec.name, error=exc))
            else:
                rec.write({
                    'sync_state': 'synced',
                    'sync_error': False,
                    'sync_date': fields.Datetime.now(),
                })
                company._payment_order_sync_log(
                    True, self.env._(
                        'Solicitud %(name)s sincronizada (id remoto %(remote_id)s).',
                        name=rec.name, remote_id=remote_id))

    def action_retry_sync(self):
        self._sync_to_enterprise()

    @api.model
    def _cron_retry_sync(self):
        pending = self.search([
            ('sync_state', '=', 'error'),
            ('company_id.payment_order_role', '=', 'solicitante'),
            ('company_id.payment_order_sync_enabled', '=', True),
        ])
        pending._sync_to_enterprise()

    def action_view_payment_order(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment.order',
            'view_mode': 'form',
            'res_id': self.payment_order_id.id,
            'target': 'current',
        }

    def action_crear_anticipo(self):
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(self.env._('Solo se puede crear el Anticipo desde una solicitud aprobada.'))
        if self.payment_order_id:
            raise UserError(self.env._('Esta solicitud ya tiene una Orden de Pago asociada.'))
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Crear Anticipo'),
            'res_model': 'account.payment.order.request.crear.anticipo.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_request_id': self.id, 'default_monto': self.total_acreditar},
        }


class AccountPaymentOrderRequestLine(models.Model):
    _name = 'account.payment.order.request.line'
    _description = 'Línea de Solicitud de Pago (Viáticos)'

    request_id = fields.Many2one('account.payment.order.request', string='Solicitud',
                                  required=True, ondelete='cascade')
    employee_id = fields.Many2one(
        'hr.employee', string='Empleado',
        help='Empleado destino de este renglón (sincronizado desde Enterprise). Llena '
             'técnico/departamento/puesto automáticamente; viaja hacia la instalación '
             'Procesadora tanto como texto (`tecnico_name`) como `employee_enterprise_ref` (el '
             'id ORIGINAL de este empleado en Enterprise, válido en ambos lados - ver el '
             'encabezado). No es `required=True` a nivel de campo (rompería la recepción de '
             'líneas sincronizadas de un empleado todavía no vinculado a un `enterprise_ref` '
             'conocido); se exige en cambio en `action_submit()`, que las líneas locales '
             'siempre pasan y las sincronizadas no.')
    tecnico_name = fields.Char(
        string='Técnico',
        help='Nombre en texto plano de `employee_id`, autocompletado - lo que realmente viaja '
             'hacia la instalación Procesadora. No se muestra en la vista: el usuario solo '
             'elige `employee_id`.')
    departamento = fields.Char(string='Departamento')
    puesto = fields.Char(string='Puesto')
    justificacion_tipo_id = fields.Many2one(
        'account.payment.order.justification.type', string='Tipo de Gasto',
        help='Sugerido desde el Tipo de Gasto del encabezado al agregar la línea '
             '(ver _onchange_request_id()/default_get()), pero editable por línea - p. ej. si '
             'el jefe de técnicos necesita cambiarlo para un renglón en particular. Nunca se '
             'envía como id a la instalación Procesadora, solo el nombre.')
    cantidad = fields.Integer(string='Cantidad', default=1)
    costo_individual = fields.Float(string='Costo Individual')
    total = fields.Float(string='Total', compute='_compute_total', store=True)

    @api.onchange('request_id')
    def _onchange_request_id(self):
        """Sugiere justificacion_tipo_id desde el encabezado - a diferencia de default_get()
        (que depende de que Odoo pase `default_request_id` en el contexto, algo que NO ocurre
        de forma confiable al agregar una línea en un formulario todavía sin guardar, que es el
        caso normal), este onchange sí funciona con el encabezado en memoria aunque no esté
        guardado, porque Odoo simula el onchange de la línea nueva usando el estado actual del
        formulario padre. Confirmado como el bug real reportado por el usuario: el default_get
        nunca se disparaba porque el encabezado nunca tenía un id real en ese momento."""
        for line in self:
            if line.request_id and not line.justificacion_tipo_id:
                line.justificacion_tipo_id = line.request_id.justificacion_tipo_id

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        for line in self:
            if line.employee_id:
                employee = line.employee_id.sudo()  # job_title/department_id - ver header
                line.tecnico_name = line.employee_id.name
                line.puesto = employee.job_title or line.puesto
                line.departamento = employee.department_id.name or line.departamento

    @api.model
    def default_get(self, fields_list):
        """Sugiere `justificacion_tipo_id` a partir del Tipo de Gasto del encabezado -
        editable después, es solo el valor sugerido al agregar la línea. `default_request_id`
        llega en el contexto porque así es como Odoo agrega una línea nueva desde el widget
        one2many del formulario."""
        res = super().default_get(fields_list)
        if 'justificacion_tipo_id' in fields_list and not res.get('justificacion_tipo_id'):
            request_id = res.get('request_id') or self.env.context.get('default_request_id')
            if request_id:
                request = self.env['account.payment.order.request'].browse(request_id)
                if request.justificacion_tipo_id:
                    res['justificacion_tipo_id'] = request.justificacion_tipo_id.id
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            name = vals.pop('justificacion_tipo_name', None)
            if name and not vals.get('justificacion_tipo_id'):
                justification_type = self.env[
                    'account.payment.order.justification.type']._find_or_create_by_name(name)
                vals['justificacion_tipo_id'] = justification_type.id
            ref = vals.pop('employee_enterprise_ref', None)
            if ref and not vals.get('employee_id'):
                # Mismo mecanismo que el encabezado - ver
                # AccountPaymentOrderRequest._resolve_employee_enterprise_ref().
                employee = self.env['hr.employee'].browse(int(ref)).exists()
                if employee:
                    vals['employee_id'] = employee.id
            employee_id = vals.get('employee_id')
            if employee_id:
                employee = self.env['hr.employee'].browse(employee_id)
                vals.setdefault('tecnico_name', employee.name)
                vals.setdefault('puesto', employee.sudo().job_title or False)
                vals.setdefault('departamento', employee.sudo().department_id.name or False)
        return super().create(vals_list)

    @api.depends('cantidad', 'costo_individual')
    def _compute_total(self):
        for line in self:
            line.total = line.cantidad * line.costo_individual
