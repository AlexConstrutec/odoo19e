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
             'el encabezado (ver AccountPaymentOrder.employee_partner_id): Contactos no tiene '
             'la regla multiempresa de hr.employee, así que el desplegable no choca con ella. '
             'El hr.employee real se resuelve en `employee_id` (compute).')
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
    justificacion_tipo_id = fields.Many2one(
        'account.payment.order.justification.type', string='Tipo de Gasto',
        help='Sugerido desde el Tipo de Gasto del encabezado al agregar la línea '
             '(ver _onchange_order_id()/default_get()), pero editable por línea - p. ej. si '
             'el jefe de técnicos necesita cambiarlo para un renglón en particular. Nunca se '
             'envía como id a la instalación Procesadora, solo el nombre.')
    cantidad = fields.Integer(string='Cantidad', default=1)
    costo_individual = fields.Float(string='Costo Individual')
    total = fields.Float(string='Total', compute='_compute_total', store=True)

    @api.onchange('order_id')
    def _onchange_order_id(self):
        """Sugiere justificacion_tipo_id desde el encabezado - a diferencia de default_get()
        (que depende de que Odoo pase `default_order_id` en el contexto, algo que NO ocurre
        de forma confiable al agregar una línea en un formulario todavía sin guardar, que es el
        caso normal), este onchange sí funciona con el encabezado en memoria aunque no esté
        guardado, porque Odoo simula el onchange de la línea nueva usando el estado actual del
        formulario padre."""
        for line in self:
            if line.order_id and not line.justificacion_tipo_id:
                line.justificacion_tipo_id = line.order_id.justificacion_tipo_id

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

    @api.model
    def default_get(self, fields_list):
        """Sugiere `justificacion_tipo_id` a partir del Tipo de Gasto del encabezado -
        editable después, es solo el valor sugerido al agregar la línea. `default_order_id`
        llega en el contexto porque así es como Odoo agrega una línea nueva desde el widget
        one2many del formulario."""
        res = super().default_get(fields_list)
        if 'justificacion_tipo_id' in fields_list and not res.get('justificacion_tipo_id'):
            order_id = res.get('order_id') or self.env.context.get('default_order_id')
            if order_id:
                order = self.env['account.payment.order'].browse(order_id)
                if order.justificacion_tipo_id:
                    res['justificacion_tipo_id'] = order.justificacion_tipo_id.id
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
