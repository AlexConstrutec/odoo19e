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
    cuenta_acreditar = fields.Char(
        string='Cuenta a Acreditar',
        help='Cuenta bancaria de ESTE técnico (no la del jefe que solicita) - se autocompleta '
             'desde su ficha de empleado, ya sincronizada desde Enterprise (ver '
             '`hr.employee.cuenta_bancaria_raw`). Se usa al dividir la Orden con "Depositar '
             'Directo a Técnicos" marcado - cada Orden generada necesita su propia cuenta, no '
             'la del jefe. Editable a mano si el dato no llegó sincronizado o hay que corregirlo.')
    banco = fields.Char(string='Banco')
    tipo_cuenta = fields.Selection(
        [('monetaria', 'Monetaria'), ('ahorro', 'Ahorro')], string='Tipo de Cuenta')
    cantidad = fields.Integer(string='Cantidad', default=1)
    costo_individual = fields.Float(string='Costo Individual')
    total = fields.Float(string='Total', compute='_compute_total', store=True)
    viaticos_sin_liquidar_count = fields.Integer(
        string='Viáticos sin Liquidar', compute='_compute_viaticos_sin_liquidar_count',
        help='Cantidad de OTRAS líneas de viáticos de este mismo empleado (`employee_partner_id`) '
             'en Órdenes de Pago tipo Anticipo Viáticos que todavía no están en `liquidado` ni '
             'Rechazadas/Canceladas - ayuda a detectar, al capturar una solicitud nueva, si un '
             'técnico ya tiene viáticos pendientes en otra solicitud, sea cual sea su estado '
             '(Borrador/Enviada/Aprobada/Aplicada - todas cuentan como "aún no liquidada"; solo '
             'Rechazada/Cancelada/Liquidada quedan fuera). No cuenta líneas de la propia Orden '
             'que se está capturando/editando. No stored a propósito (mismo criterio que '
             '`diferencia_conciliacion` en account_payment_order.py: es un indicador en vivo '
             'sobre datos de OTROS registros, no algo que tenga sentido cachear).')

    @api.depends('employee_partner_id')
    def _compute_viaticos_sin_liquidar_count(self):
        for line in self:
            if not line.employee_partner_id:
                line.viaticos_sin_liquidar_count = 0
                continue
            domain = [
                ('employee_partner_id', '=', line.employee_partner_id.id),
                ('order_id.tipo', '=', 'anticipo_viaticos'),
                ('order_id.state', 'not in', ('rechazado', 'cancelado', 'liquidado')),
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
                # Cuenta bancaria del TÉCNICO de esta línea, no de quien captura la Orden -
                # `hr.employee.cuenta_bancaria` (el campo público, ver hr_employee.py) solo
                # resuelve a un valor real cuando el empleado consultado es el vinculado al
                # usuario actual (protección de privacidad a propósito, para que un usuario
                # cualquiera no pueda leer la cuenta de otro empleado). Aquí el jefe SÍ necesita
                # ver la cuenta del técnico para saber a dónde depositarle - mismo criterio (y
                # mismo mecanismo, sudo() + campo _raw) que ya usa el encabezado para
                # teléfono/correo (ver `_onchange_partner_id` en account_payment_order.py).
                empleado = line.employee_id.sudo()
                line.cuenta_acreditar = empleado.cuenta_bancaria_raw or line.cuenta_acreditar
                line.banco = empleado.banco_nombre_raw or line.banco
                line.tipo_cuenta = empleado.tipo_cuenta_raw or line.tipo_cuenta

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
                    # Mismo criterio de sudo()+campo _raw que el onchange de arriba - necesario
                    # aquí porque un create() por API/script (ej. al dividir la Orden por
                    # técnico) no dispara el onchange, que solo corre en el formulario web.
                    empleado = employee.sudo()
                    vals.setdefault('cuenta_acreditar', empleado.cuenta_bancaria_raw or False)
                    vals.setdefault('banco', empleado.banco_nombre_raw or False)
                    vals.setdefault('tipo_cuenta', empleado.tipo_cuenta_raw or False)
        return super().create(vals_list)

    @api.depends('cantidad', 'costo_individual')
    def _compute_total(self):
        for line in self:
            line.total = line.cantidad * line.costo_individual
