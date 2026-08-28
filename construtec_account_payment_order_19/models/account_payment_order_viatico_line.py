from odoo import api, fields, models

from .account_payment_order import _resolve_employee_for_partner


class AccountPaymentOrderViaticoLine(models.Model):
    _name = 'account.payment.order.viatico.line'
    _description = 'Línea de Viáticos de una Orden de Pago'

    order_id = fields.Many2one('account.payment.order', string='Orden de Pago',
                                required=True, ondelete='cascade')
    employee_partner_id = fields.Many2one(
        'res.partner', string='Empleado', domain="[('employee', '=', True)]",
        help='Contacto (no hr.employee directo) destino de este renglón - mismo criterio que '
             'el encabezado (ver AccountPaymentOrder.partner_id): Contactos no tiene la regla '
             'multiempresa de hr.employee, así que el desplegable no choca con ella. El '
             'hr.employee real se resuelve en `employee_id` (compute).')
    employee_id = fields.Many2one(
        'hr.employee', string='Empleado (resuelto)', compute='_compute_employee_id', store=True,
        readonly=True,
        help='hr.employee real detrás de `employee_partner_id`, para la compañía de la Orden '
             'de Pago padre - ver AccountPaymentOrder._resolve_employee_for_partner(). Llena '
             'técnico/departamento/puesto automáticamente; viaja hacia la instalación '
             'Procesadora tanto como texto (`tecnico_name`) como `employee_enterprise_ref` (el '
             'id ORIGINAL de este empleado en Enterprise, válido en ambos lados - ver el '
             'encabezado). `employee_partner_id` no es `required=True` a nivel de campo '
             '(rompería la recepción de líneas sincronizadas de un empleado todavía no '
             'vinculado a un `enterprise_ref` conocido); se exige en cambio en '
             '`action_submit()`, que las líneas locales siempre pasan y las sincronizadas no.')
    tecnico_name = fields.Char(
        string='Técnico',
        help='Nombre en texto plano de `employee_id`, autocompletado - lo que realmente viaja '
             'hacia la instalación Procesadora. No se muestra en la vista: el usuario solo '
             'elige `employee_id`.')
    departamento = fields.Char(string='Departamento')
    puesto = fields.Char(string='Puesto')
    cantidad = fields.Integer(string='Cantidad', default=1)
    costo_individual = fields.Float(string='Costo Individual')
    total = fields.Float(string='Total', compute='_compute_total', store=True)
    viaticos_sin_liquidar_count = fields.Integer(
        string='Viáticos sin Liquidar', compute='_compute_viaticos_sin_liquidar_count',
        help='Cantidad de OTRAS líneas de viáticos de este mismo empleado (`employee_partner_id`) '
             'en Órdenes de Pago tipo Anticipo Viáticos que todavía no tienen su Liquidación '
             'conciliada (`order_id.esta_liquidado = False`) y no están Rechazadas/Canceladas - '
             'ayuda a detectar, al capturar una solicitud nueva, si un técnico ya tiene viáticos '
             'pendientes en otra solicitud, sea cual sea su estado (Borrador/Enviada/Aprobada/'
             'Aplicada - todas cuentan como "aún no liquidada"; solo Rechazada/Cancelada quedan '
             'fuera, por estar muertas). No cuenta líneas de la propia Orden que se está '
             'capturando/editando. No stored a propósito (mismo criterio que '
             '`diferencia_conciliacion`/`anticipos_disponibles_ids` en account_payment_order.py: '
             'es un indicador en vivo sobre datos de OTROS registros, no algo que tenga sentido '
             'cachear).')

    @api.depends('employee_partner_id')
    def _compute_viaticos_sin_liquidar_count(self):
        for line in self:
            if not line.employee_partner_id:
                line.viaticos_sin_liquidar_count = 0
                continue
            domain = [
                ('employee_partner_id', '=', line.employee_partner_id.id),
                ('order_id.tipo', '=', 'anticipo_viaticos'),
                ('order_id.state', 'not in', ('rechazado', 'cancelado')),
                ('order_id.esta_liquidado', '=', False),
            ]
            # order_id.id puede ser un NewId (formulario todavía sin guardar) - un NewId no es
            # un valor válido para un domain de search_count, y de todas formas una Orden nueva
            # sin guardar no existe todavía en la base para que search_count() la encuentre, así
            # que excluirla es innecesaria en ese caso. Solo se excluye por id real cuando existe.
            if isinstance(line.order_id.id, int):
                domain.append(('order_id', '!=', line.order_id.id))
            line.viaticos_sin_liquidar_count = self.search_count(domain)

    @api.depends('employee_partner_id', 'order_id.company_id')
    def _compute_employee_id(self):
        for line in self:
            line.employee_id = _resolve_employee_for_partner(
                line.employee_partner_id, line.order_id.company_id)

    @api.onchange('employee_partner_id')
    def _onchange_employee_partner_id(self):
        for line in self:
            if line.employee_id:
                line.tecnico_name = line.employee_id.name
                # puesto/departamento: del CONTACTO, no resueltos en vivo - ver header/res_partner.py.
                line.puesto = line.employee_partner_id.function or line.puesto
                line.departamento = line.employee_partner_id.employee_department_id.name or line.departamento

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            ref = vals.pop('employee_enterprise_ref', None)
            if ref and not vals.get('employee_partner_id'):
                # Mismo mecanismo que el encabezado - ver
                # AccountPaymentOrder._resolve_employee_enterprise_ref().
                employee = self.env['hr.employee'].browse(int(ref)).exists()
                if employee:
                    vals['employee_partner_id'] = employee.work_contact_id.id
            partner_id = vals.get('employee_partner_id')
            if partner_id:
                partner = self.env['res.partner'].browse(partner_id)
                # puesto/departamento: del CONTACTO, no resueltos en vivo - ver res_partner.py.
                vals.setdefault('puesto', partner.function or False)
                vals.setdefault('departamento', partner.employee_department_id.name or False)
                # tecnico_name sí necesita el hr.employee real (su nombre puede diferir del
                # nombre del contacto) - employee_id todavía no existe (el registro no se ha
                # insertado), se resuelve aquí con el mismo criterio que el compute, usando la
                # compañía de la Orden de Pago padre (ya real: Odoo fija order_id antes de
                # crear la línea).
                order = self.env['account.payment.order'].browse(vals.get('order_id'))
                employee = _resolve_employee_for_partner(partner, order.company_id)
                if employee:
                    vals.setdefault('tecnico_name', employee.name)
        return super().create(vals_list)

    @api.depends('cantidad', 'costo_individual')
    def _compute_total(self):
        for line in self:
            line.total = line.cantidad * line.costo_individual
