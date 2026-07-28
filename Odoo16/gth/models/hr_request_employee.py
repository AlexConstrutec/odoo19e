from bs4 import BeautifulSoup

from odoo import models, fields, api


class HrRequestEmployee(models.Model):
    _name = "hr.request.employee"
    _description = "Solicitud de Talento"
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']
    tipo_plaza = fields.Selection(
        [('ampliacion', 'Ampliacion de Apoyo'),
         ('programado', 'Apoyo Programado'),
         ('emergente', 'Apoyo Emergente'),
         ('contrato', 'Contrato Definido'),
         ('reemplazo', 'Reemplazo de Plaza'),
         ('nuevo', 'Nueva Plaza'),
         ], string='Tipo de plaza', required=True, store=True,  readonly=True, index=True)
    name = fields.Char(string='Nombre', required=True, store=True, index=True, default=lambda self: ('Nueva Requisición de Personal'))
    state = fields.Selection(
        [('por_aprobar', 'Por Aprobar'), ('aprobado', 'Aprobado'), ('rechazado', 'Rechazado'), ('en_proceso', 'En Proceso'), ('cubierto', 'Cubierto')],
        string='Estado',
        readonly=True,
        store=True,
        index=True,
        track_visibility='onchange', default='por_aprobar')
    puesto_id = fields.Many2one('hr.job', string='Puesto', store=True, required=True, domain=lambda self: [('company_id', '=', self.env.company.id)])
    reemplazos_id = fields.Many2one('hr.employee', string='Reemplazo', store=True)
    responsable_id = fields.Many2one('hr.employee', string='Responsable',  store=True, required=True)
    departamento_id = fields.Many2one('hr.department', string='Departamento',  store=True, required=True, domain=lambda self: [('company_id', '=', self.env.company.id)])
    # area_id = fields.Many2one('x_area', string='Area',  store=True, required=True, domain=lambda self: [('x_company_id', '=', self.env.company.id), ('x_departmento', '=', self.departamento_id.id)])
    fecha_inicio = fields.Date(string='Fecha de inicio',  store=True, invisible=True)
    fecha_fin = fields.Date(string='Fecha de fin', store=True, invisible=True)
    jornada = fields.Many2one('request.jornada', string='Jornada', store=True, required=True)
    experiencias = fields.Many2one('request.experiencia', string='Experiencia', store=True, required=True)
    genero = fields.Selection([('masculino', 'Masculino'), ('femenino', 'Femenino'), ('indistinto', 'Indistinto')], string='Genero', store=True, required=True)
    tipo_vehiculo = fields.Selection([('automovil', 'Automóvil'), ('moto', 'Moto'), ('bicicleta', 'Bicicleta')],
                                        string='Tipo de vehiculo', store=True)
    licencia = fields.Many2one('request.licencia', string='Licencia', store=True)
    sueldo_ids = fields.One2many('hr.request.employee.salary', 'request_employee_id', string='Salario', store=True)
    sueldo = fields.Float(string='Sueldo', readonly=True, store=True, compute="_compute_sueldo")
    aplica_horas_extras = fields.Boolean(string='Aplica horas extras', store=True)
    # Campo calculado para controlar visibilidad y atributos de solo lectura
    fecha_inicio_visibility = fields.Boolean(compute="_compute_fecha_inicio_visibility", default=False)
    fecha_inicio_readonly = fields.Boolean(compute="_compute_fecha_inicio_readonly", default=False)
    requisitos = fields.Text(string='Requisitos', store=True, compute="_compute_requisitos", default='- Conocimientos técnicos\n- Conocimientos de la empresa\n- Conocimientos de la industria\n- Conocimientos de la competencia')
    ofrecimientos = fields.Text(string='Ofrecemos', store=True,
                                default='- Salario atractivo\n- Prestaciones de ley\n- Oportunidad de crecimiento')
    funcion_principal = fields.Text(string='Función principal', readonly=True)
    funciones_especificas = fields.Text(string='Funciones Especificas', readonly=True)
    motivo_rechazo = fields.Text(string='Motivo de rechazo', store=True)
    numero_solicitud = fields.Char(string='Número de solicitud', store=True, readonly=True, compute="_compute_numero_solicitud")



    @api.depends('departamento_id')
    def _compute_numero_solicitud(self):
        last_codigo = self.env['hr.request.employee'].search([], order='id desc', limit=1)

        for record in self:
            if record.id:
                record.numero_solicitud = record.departamento_id.name + str(record.id)
            else:
                if record.departamento_id:
                    record.numero_solicitud = record.departamento_id.name + str(last_codigo.id + 1)

    @api.depends('genero', 'tipo_vehiculo', 'licencia', 'jornada', 'experiencias')
    def _compute_requisitos(self):
        for res in self:
            requisitos = ''
            if res.genero:
                requisitos += '- Genero: ' + res.genero + '\n'
            if res.tipo_vehiculo:
                requisitos += '- Tipo de vehiculo: ' + res.tipo_vehiculo + '\n'
            if res.licencia:
                requisitos += '- Licencia: ' + res.licencia.name + '\n'
            if res.jornada:
                requisitos += '- Jornada: ' + res.jornada.name + '\n'
            if res.experiencias:
                requisitos += '- Experiencia: ' + res.experiencias.name + '\n'
            res.requisitos = requisitos

    @api.depends('sueldo_ids')
    def _compute_sueldo(self):
        for request in self:
            request.sueldo = sum([(p.monto or 0.0) for p in request.sueldo_ids])

    @api.onchange('sueldo_ids')
    def _onchange_sueldo_ids(self):
        for request in self:
            request.sueldo = sum([(p.monto or 0.0) for p in request.sueldo_ids])
    # Edvin 8 1 2024 estoy creando de forma aumoatica el salario minimo y bonificacion incentivo
    @api.model
    def default_get(self, fields):
        defaults = super(HrRequestEmployee, self).default_get(fields)
        default_sueldo_ids = []
        # Agregar dos valores por defecto a sueldo_ids
        default_sueldo_ids.append((0, 0, {'name': 'minimo', 'monto': 3077.56}))  # Cambia 'monto' al valor deseado
        default_sueldo_ids.append((0, 0, {'name': 'bonif_in', 'monto': 250}))  # Cambia 'monto' al valor deseado
        defaults['sueldo_ids'] = default_sueldo_ids
        return defaults

    @api.depends('puesto_id')
    def _compute_funciones(self):
        for res in self:
            if res.puesto_id:
                # funciones_texto = BeautifulSoup(res.puesto_id.funciones, 'html.parser').get_text()
                # res.funcion_principal = funciones_texto
                res.funcion_principal = res.puesto_id.funcion_principal
                res.funciones_especificas = '\n'.join(line.name for line in res.puesto_id.funciones_especificas)
            else:
                res.funcion_principal = ''
                res.funciones_especificas = ''

    @api.onchange('puesto_id')
    def _onchange_puesto_id(self):
        for res in self:
            if res.puesto_id:
                # funciones_texto = BeautifulSoup(res.puesto_id.funciones, 'html.parser').get_text()
                # res.funcion_principal = funciones_texto
                res.funcion_principal = res.puesto_id.funcion_principal
                res.funciones_especificas = '\n'.join(line.name for line in res.puesto_id.funciones_especificas)
                return {'domain': {'reemplazos_id': [('job_id', '=', res.puesto_id.id)]}}
            else:
                res.funcion_principal = ''
                res.funciones_especificas = ''
#-----------------------------------------------------------------------------------
    # Crear las experiencias antes
    @api.depends('tipo_plaza')
    def _compute_fecha_inicio_visibility(self):
        for request in self:
            if request.tipo_plaza in ['ampliacion', 'programado', 'emergente']:
                request.fecha_inicio_visibility = False
            else:
                request.fecha_inicio_visibility = True

    @api.onchange('tipo_plaza')
    def _compute_fecha_inicio_visibility(self):
        for request in self:
            if request.tipo_plaza in ['ampliacion', 'programado', 'emergente']:
                request.fecha_inicio_visibility = False
            else:
                request.fecha_inicio_visibility = True
    #
    # @api.onchange('tipo_plaza')
    # def _onchang_experiencias(self):
    #     for request in self:
    #         if request.tipo_plaza in ['ampliacion', 'programado', 'emergente']:
    #             request.experiencias = False
    #             return {'domain': {'experiencias': [('id', 'in', [1, 2])]}}
    #         else:
    #             request.experiencias = False
    #             return {'domain': {'experiencias': [('id', 'in', [1, 2, 3, 4, 5, 6])]}}
    #
    # @api.depends('tipo_plaza')
    # def _compute_jornada_visibility(self):
    #     for request in self:
    #         if request.tipo_plaza in ['ampliacion', 'programado', 'emergente', 'reemplazo']:
    #             request.jornada = False
    #         else:
    #             request.jornada = False
    #
    # @api.onchange('tipo_plaza')
    # def _onchange_tipo_plaza(self):
    #     for request in self:
    #         if request.tipo_plaza in ['ampliacion', 'programado', 'emergente', 'reemplazo']:
    #             request.jornada = False
    #             return {'domain': {'jornada': [('id', 'in', [1, 2, 3, 4])]}}
    #         else:
    #             request.jornada = False
    #             return {'domain': {'jornada': [('id', 'in', [1])]}}
#Crear las licencias antes
    @api.depends('tipo_vehiculo')
    def _compute_licencia_visibility(self):
        for request in self:
            if request.tipo_vehiculo in ['automovil', 'moto']:
                request.licencia = False
            else:
                request.licencia = False

    @api.onchange('tipo_vehiculo')
    def _onchange_tipo_vehiculo(self):
        for request in self:
            if request.tipo_vehiculo in ['automovil']:
                request.licencia = False
                return {'domain': {'licencia': [('id', 'in', [1, 2, 3])]}}
            elif request.tipo_vehiculo in ['moto']:
                request.licencia = False
                request.licencia = 4
                return {'domain': {'licencia': [('id', 'in', [4])]}}
            else:
                request.licencia = False
                request.licencia = 5
                return {'domain': {'licencia': [('id', 'in', [5])]}}

    @api.depends('state')
    def _compute_fecha_inicio_readonly(self):
        for request in self:
            if request.state != 'por_aprobar':
                request.fecha_inicio_readonly = True
            else:
                request.fecha_inicio_readonly = False

    @api.depends('puesto_id')
    def _compute_name(self):
        for request in self:
            if request.puesto_id:
                request.name = "Solicitud: " + str(request.puesto_id.name)

    @api.onchange('puesto_id')
    def _onchange_puesto_id(self):
        for request in self:
            if request.puesto_id:
                request.name = "Solicitud: " + str(request.puesto_id.name)


    @api.model
    def default_get(self, fields):
        defaults = super(HrRequestEmployee, self).default_get(fields)
        default_sueldo_ids = []
        # Agregar dos valores por defecto a sueldo_ids
        default_sueldo_ids.append((0, 0, {'name': 'minimo', 'monto': 3077.56}))  # Cambia 'monto' al valor deseado
        default_sueldo_ids.append((0, 0, {'name': 'bonif_in', 'monto': 250}))  # Cambia 'monto' al valor deseado
        defaults['sueldo_ids'] = default_sueldo_ids
        return defaults

    def aprobar(self):
        for request in self:
            if request.state == 'por_aprobar':
                puesto = self.env['hr.job'].search([('id', '=', request.puesto_id.id)])
                puesto.write({
                    'website_published': True,
                    'requisitos': request.requisitos,
                    'ofrecimientos': request.ofrecimientos,
                })
                request.state = 'aprobado'
#  27 12 2023 cambios Edvin
    def rechazar(self):
        for request in self:
            if request.state == 'por_aprobar':
                # llamar accion action_wizard_rechazo
                return {
                    'name': 'Motivo de rechazo',
                    'type': 'ir.actions.act_window',
                    'res_model': 'wizard.motivo.rechazo',
                    'view_mode': 'form',
                    'target': 'new',
                }

    def en_proceso(self):
        for request in self:
            if request.state == 'aprobado':
                request.state = 'en_proceso'
    def cubierto(self):
        for request in self:
            if request.state == 'en_proceso':
                request.state = 'cubierto'
    def reiniciar(self):
        for request in self:
            if request.state == 'rechazado':
                request.state = 'por_aprobar'



