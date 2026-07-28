# -*- coding: utf-8 -*-
import datetime

from zeep import Client
import json

import logging
logger = logging.getLogger()
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class HrEmployee(models.Model):
    _inherit = "hr.employee"
    identification_id = fields.Char(string="DPI", store=True, required=True)
    codigo_empleado = fields.Integer(string="Código de empleado", store=True)
    # codigo_employee_id = fields.Many2one('hr.codigo.employee', string="Código de empleado", store=True)
    # codigo_empleado = fields.Integer(related='codigo_employee_id.codigo_empleado', string="Código de empleado", store=True)
    job_title = fields.Char(string='Puesto de Trabajo', store=True, readonly=False)
    # estos cmapos se agregaron en Información provada en el grupo de contacto
    nit = fields.Char(string="NIT", store=True)
    igss = fields.Char(string='IGSS', store=True)
    # este campo esta en configuración RRHH en el grupo de Nómina
    # requerido en la vista en la pestaña de confu
    # guración rr hh grupo de Estado
    # crear los 6 campos de nombres
    # Estos campos se agregaron en la vista de empleados
    primer_nombre = fields.Char(string="Primer nombre", store=True)
    segundo_nombre = fields.Char(string="Segundo nombre", store=True)
    tercer_nombre = fields.Char(string="Tercer nombre", store=True)
    primer_apellido = fields.Char(string="Primer apellido", store=True)
    segundo_apellido = fields.Char(string="Segundo apellido", store=True)
    apellido_casada = fields.Char(string="Apellido de casada", store=True)
    departamento_id = fields.Many2one('hr.departamento', string='Departamento', store=True)
    municipio_id = fields.Many2one('hr.municipio', string='Municipio', store=True)
    registration_number = fields.Char(string="Código", store=True, readonly=False)
    identification_id = fields.Char(string="DPI", store=True, required=True)
    historial_laboral = fields.One2many(
        'hr.employee.history.job.salary',
        compute='_compute_historial_laboral',
        string="Historial Laboral"
    )

    jornada_trabajo = fields.Selection([
        ('1', 'Diurna'),
        ('2', 'Mixta'),
        ('3', 'Nocturna'),
        ('4', 'No está sujeto a jornada'),
        ('5', 'Tiempo Parcial'),
    ], string="Jornada de trabajo", default='1', store=True)

    ocupacion_puesto_id = fields.Many2one('hr.ocupacion.puesto', string='Ocupación de puesto', store=True)
    discapacidad = fields.Selection( [
        ('1', 'Ninguna'),
        ('2', 'Discapacidad auditiva'),
        ('3', 'Discapacidad visual'),
        ('4', 'Discapacidad múltiple'),
        ('5', 'Discapacidad física o motora'),
        ('6', 'Discapacidad intelectual'),
        ('7', 'Otra'),
    ],string='Discapacidad', default='1', store=True)

    certificate = fields.Selection([
        ('other', 'Ninguno'),
        ('2', 'Primaria Incompleta'),
        ('3', 'Primaria Completa'),
        ('4', 'Básico Incompleto'),
        ('5', 'Básico Completo'),
        ('6', 'Diversificado Incompleto'),
        ('graduate', 'Diversificado Completo'),
        ('8', 'Estudiante Universitario'),
        ('9', 'Técnico Universitario'),
        ('bachelor', 'Licenciatura'),
        ('11', 'Postgrado'),
        ('master', 'Maestría'),
        ('doctor', 'Doctorado'),
    ], string='Nivel de certificado', default='other', groups="hr.group_hr_user", tracking=True)
    study_field = fields.Char("Profesión", groups="hr.group_hr_user", tracking=True)
    x_employee_family = fields.One2many('hr.employee.family', 'x_employee_id', string='Carga Familiar', store=True)
    employee_educational = fields.One2many('hr.employee.educational', 'employee_id', string='Educación', store=True)
    employee_work_history = fields.One2many('hr.employee.work.history', 'employee_id', string='Datos Laborales', store=True)
    employee_licencia = fields.One2many('hr.employee.licencia', 'employee_id', string='Licencias de Conducir', store=True)
    pritn_name_coabitant = fields.Boolean(string="Imprimir nombre de Cónyuge (IRTRA)", store=True)
    calle = fields.Char(string="Dirección",  related='address_home_id.street')
    departure_reason_id = fields.Many2one('hr.departure.reason', string='Motivo de salida', related='contract_id.departure_reason_id', store=True)
    departure_date = fields.Date(string='Fecha de salida', related='contract_id.date_end', store=True)
    edad = fields.Integer(string='Edad', compute="_get_edad")
    mes_cumpleanios = fields.Char(string='Mes Cumpleaños', compute="_get_Mes", store=True)
    _sql_constraints = ([
        ('unique_registration_number', 'UNIQUE(id, company_id)', 'No duplication of registration numbers is allowed')
    ])

    @api.depends('birthday')
    def _get_Mes(self):
        month_names = {
            1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
            5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
            9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
        }
        for employee in self:
            if employee.birthday:
                mes_nacimiento = int(employee.birthday.strftime('%m'))
                employee.mes_cumpleanios = month_names.get(mes_nacimiento, '')
            else:
                employee.mes_cumpleanios = ''

    def _get_edad(self):
        for employee in self:
            if employee.birthday:
                today = datetime.date.today()
                birth_date = employee.birthday
                age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
                employee.edad = age
            else:
                employee.edad = 0

    @api.depends('identification_id')
    def _compute_historial_laboral(self):
        for employee in self:
            employee.historial_laboral = self.env['hr.employee.history.job.salary'].search([
                ('identification_employee_id', '=', employee.identification_id)
            ])
    @api.onchange('identification_id')
    def _onchange_identification_id(self):
        if self.identification_id and self.company_id:
            duplicate_employee = self.env['hr.employee'].search([
                ('identification_id', '=', self.identification_id),
                ('company_id', '=', self.company_id.id),
                ('active', 'in', [True, False]),
            ])
            if duplicate_employee:
                if not duplicate_employee.active:
                    raise UserError("El colaborador con este DPI está archivado en esta empresa.")
                else:
                    raise UserError("Ya existe un empleado con este DPI en esta empresa.")

        existe_codigo = self.env['hr.codigo.employee'].search(
            [('identification_employee_id', '=', self.identification_id)])
        if existe_codigo:
            self.primer_nombre = existe_codigo.primer_nombre
            self.segundo_nombre = existe_codigo.segundo_nombre
            self.tercer_nombre = existe_codigo.tercer_nombre
            self.primer_apellido = existe_codigo.primer_apellido
            self.segundo_apellido = existe_codigo.segundo_apellido
            self.apellido_casada = existe_codigo.apellido_casada
            self.mobile_phone = existe_codigo.mobile_phone

            # self.work_phone = existe_codigo.work_phone
            self.work_email = existe_codigo.work_email
            self.private_email = existe_codigo.private_email
            self.phone = existe_codigo.phone
            self.km_home_work = existe_codigo.km_home_work
            self.certificate = existe_codigo.certificate
            self.study_field = existe_codigo.study_field
            self.study_school = existe_codigo.study_school
            self.discapacidad = existe_codigo.discapacidad
            self.nit = existe_codigo.nit
            self.igss = existe_codigo.igss
            self.marital = existe_codigo.marital
            self.children = existe_codigo.children
            self.emergency_contact = existe_codigo.emergency_contact
            self.emergency_phone = existe_codigo.emergency_phone
            self.gender = existe_codigo.gender
            self.birthday = existe_codigo.birthday
            self.departamento_id = existe_codigo.departamento_id.id if existe_codigo.departamento_id else False
            self.municipio_id = existe_codigo.municipio_id.id if existe_codigo.municipio_id else False
            self.address_home_id = existe_codigo.address_home_id.id if existe_codigo.address_home_id else False
            self.bank_account_id = existe_codigo.bank_account_id.id if existe_codigo.bank_account_id else False
            # self.resource_calendar_id = existe_codigo.resource_calendar_id.id if existe_codigo.resource_calendar_id else False
            # Asignar campos One2many utilizando la sintaxis adecuada
            # self.x_employee_family = [(6, 0, existe_codigo.x_employee_family.ids)]
            # self.employee_educational = [(6, 0, existe_codigo.employee_educational.ids)]
            # self.employee_work_history = [(6, 0, existe_codigo.employee_work_history.ids)]
            # self.employee_licencia = [(6, 0, existe_codigo.employee_licencia.ids)]
    def generar_codigo(self):
        for rec in self:
            last_codigo = self.env['hr.codigo.employee'].search([], order='codigo_empleado desc', limit=1)
            codigos = self.env['hr.codigo.employee'].search([])
            codigo_distinto = True
            existe_codigo = self.env['hr.codigo.employee'].search([('identification_employee_id', '=', rec.identification_id)])
            # Crea nuevo numero de codigo
            if last_codigo:
                new_codigo_num = last_codigo.codigo_empleado + 1
            else:
                new_codigo_num = 7580

            for codigo in codigos:
                if int(rec.registration_number) == codigo.codigo_empleado:
                    codigo_distinto = False
                    break

            if not rec.identification_id:
                raise UserError("Requiere de un DPI para generar el código")
            elif rec.registration_number and codigo_distinto and not existe_codigo:
                rec.codigo_empleado = str(rec.registration_number)
                codigo = self.env['hr.codigo.employee'].create({
                    'codigo_empleado': str(rec.registration_number),
                    'identification_employee_id': rec.identification_id,
                    'primer_nombre': rec.primer_nombre,
                    'segundo_nombre': rec.segundo_nombre,
                    'tercer_nombre': rec.tercer_nombre,
                    'primer_apellido': rec.primer_apellido,
                    'segundo_apellido': rec.segundo_apellido,
                    'apellido_casada': rec.apellido_casada,
                    'mobile_phone': rec.mobile_phone,
                    # 'work_phone': rec.work_phone,
                    'work_email': rec.work_email,
                    'private_email': rec.private_email,
                    'phone': rec.phone,
                    'km_home_work': rec.km_home_work,
                    'certificate': rec.certificate,
                    'study_field': rec.study_field,
                    'study_school': rec.study_school,
                    'discapacidad': rec.discapacidad,
                    'nit': rec.nit,
                    'igss': rec.igss,
                    'marital': rec.marital,
                    'spouse_complete_name': rec.spouse_complete_name,
                    'spouse_birthdate': rec.spouse_birthdate,
                    'children': rec.children,
                    'emergency_contact': rec.emergency_contact,
                    'emergency_phone': rec.emergency_phone,
                    'gender': rec.gender,
                    'birthday': rec.birthday,
                    'departamento_id': rec.departamento_id.id if rec.departamento_id else False,
                    'municipio_id': rec.municipio_id.id if rec.municipio_id else False,
                    'address_home_id': rec.address_home_id.id if rec.address_home_id else False,
                    'bank_account_id': rec.bank_account_id.id if rec.bank_account_id else False,
                    # 'resource_calendar_id': rec.resource_calendar_id.id if rec.resource_calendar_id else False,
                    # 'x_employee_family': [(6, 0, rec.x_employee_family.ids)] if rec.x_employee_family else False,
                    # 'employee_educational': [
                    #     (6, 0, rec.employee_educational.ids)] if rec.employee_educational else False,
                    # 'employee_work_history': [
                    #     (6, 0, rec.employee_work_history.ids)] if rec.employee_work_history else False,
                    # 'employee_licencia': [(6, 0, rec.employee_licencia.ids)] if rec.employee_licencia else False,
                })
            elif not existe_codigo and rec.codigo_empleado == 0:
                codigo = self.env['hr.codigo.employee'].create({
                    'codigo_empleado': new_codigo_num,
                    'identification_employee_id': rec.identification_id,
                    'primer_nombre': rec.primer_nombre,
                    'segundo_nombre': rec.segundo_nombre,
                    'tercer_nombre': rec.tercer_nombre,
                    'primer_apellido': rec.primer_apellido,
                    'segundo_apellido': rec.segundo_apellido,
                    'apellido_casada': rec.apellido_casada,
                    'mobile_phone': rec.mobile_phone,
                    # 'work_phone': rec.work_phone,
                    'work_email': rec.work_email,
                    'private_email': rec.private_email,
                    'phone': rec.phone,
                    'km_home_work': rec.km_home_work,
                    'certificate': rec.certificate,
                    'study_field': rec.study_field,
                    'study_school': rec.study_school,
                    'discapacidad': rec.discapacidad,
                    'nit': rec.nit,
                    'igss': rec.igss,
                    'marital': rec.marital,
                    'spouse_complete_name': rec.spouse_complete_name,
                    'spouse_birthdate': rec.spouse_birthdate,
                    'children': rec.children,
                    'emergency_contact': rec.emergency_contact,
                    'emergency_phone': rec.emergency_phone,
                    'gender': rec.gender,
                    'birthday': rec.birthday,
                    'departamento_id': rec.departamento_id.id if rec.departamento_id else False,
                    'municipio_id': rec.municipio_id.id if rec.municipio_id else False,
                    'address_home_id': rec.address_home_id.id if rec.address_home_id else False,
                    'bank_account_id': rec.bank_account_id.id if rec.bank_account_id else False,
                    # 'resource_calendar_id': rec.resource_calendar_id.id if rec.resource_calendar_id else False,
                    # 'x_employee_family': [(6, 0, rec.x_employee_family.ids)] if rec.x_employee_family else False,
                    # 'employee_educational': [
                    #     (6, 0, rec.employee_educational.ids)] if rec.employee_educational else False,
                    # 'employee_work_history': [
                    #     (6, 0, rec.employee_work_history.ids)] if rec.employee_work_history else False,
                    # 'employee_licencia': [(6, 0, rec.employee_licencia.ids)] if rec.employee_licencia else False,
                })
                rec.codigo_empleado = new_codigo_num
                rec.registration_number = str(new_codigo_num)
            elif existe_codigo:
                rec.name = (str(rec.primer_nombre) if rec.primer_nombre else "") + \
                          (" " + str(rec.segundo_nombre) if rec.segundo_nombre else "") + \
                          (" " + str(rec.tercer_nombre) if rec.tercer_nombre else "") + \
                          (" " + str(rec.primer_apellido) if rec.primer_apellido else "") + \
                          (" " + str(rec.segundo_apellido) if rec.segundo_apellido else "") + \
                          (" " + str(rec.apellido_casada) if rec.apellido_casada else "")
                rec.codigo_empleado = existe_codigo.codigo_empleado
                rec.registration_number = str(existe_codigo.codigo_empleado)
                rec.primer_nombre = existe_codigo.primer_nombre
                rec.segundo_nombre = existe_codigo.segundo_nombre
                rec.tercer_nombre = existe_codigo.tercer_nombre
                rec.primer_apellido = existe_codigo.primer_apellido
                rec.segundo_apellido = existe_codigo.segundo_apellido
                rec.apellido_casada = existe_codigo.apellido_casada
                rec.mobile_phone = existe_codigo.mobile_phone
                # rec.work_phone = existe_codigo.work_phone
                rec.work_email = existe_codigo.work_email
                rec.private_email = existe_codigo.private_email
                rec.phone = existe_codigo.phone
                rec.km_home_work = existe_codigo.km_home_work
                rec.certificate = existe_codigo.certificate
                rec.study_field = existe_codigo.study_field
                rec.study_school = existe_codigo.study_school
                rec.discapacidad = existe_codigo.discapacidad
                rec.nit = existe_codigo.nit
                rec.igss = existe_codigo.igss
                rec.marital = existe_codigo.marital
                rec.children = existe_codigo.children
                rec.emergency_contact = existe_codigo.emergency_contact
                rec.emergency_phone = existe_codigo.emergency_phone
                rec.gender = existe_codigo.gender
                rec.birthday = existe_codigo.birthday
                rec.departamento_id = existe_codigo.departamento_id.id if existe_codigo.departamento_id else False
                rec.municipio_id = existe_codigo.municipio_id.id if existe_codigo.municipio_id else False
                rec.address_home_id = existe_codigo.address_home_id.id if existe_codigo.address_home_id else False
                rec.bank_account_id = existe_codigo.bank_account_id.id if existe_codigo.bank_account_id else False
                # rec.resource_calendar_id = existe_codigo.resource_calendar_id.id if existe_codigo.resource_calendar_id else False

    def registrar_historial_puestos(self):
        self.ensure_one()
        return {
            'name': 'Historial de puestos de trabajo',
            'type': 'ir.actions.act_window',
            'res_model': 'hr.employee.history.job.salary',
            'view_mode': 'form',
            'domain': [('identification_employee_id', '=', self.identification_id)],
            'context': {
                'default_identification_employee_id': self.identification_id,
            },
            'target': 'new',
        }

    @api.onchange('country_id')
    def _onchange_nacionalidad(self):
        if not self.country_id:
            self.country_id = self.env['res.country'].browse(90)
    @api.onchange('primer_nombre', 'segundo_nombre', 'tercer_nombre', 'primer_apellido', 'segundo_apellido',
                  'apellido_casada', 'name')
    def _onchange_name(self):
        nombre_completo = (str(self.primer_nombre) if self.primer_nombre else "") + \
                          (" " + str(self.segundo_nombre) if self.segundo_nombre else "") + \
                          (" " + str(self.tercer_nombre) if self.tercer_nombre else "") + \
                          (" " + str(self.primer_apellido) if self.primer_apellido else "") + \
                          (" " + str(self.segundo_apellido) if self.segundo_apellido else "") + \
                          (" " + str(self.apellido_casada) if self.apellido_casada else "")
        if not self.name and not self.primer_nombre and not self.primer_apellido and not self.segundo_nombre and not self.segundo_apellido and not self.apellido_casada and not self.tercer_nombre:
            pass
        if self.name and not self.primer_nombre and not self.primer_apellido and not self.segundo_nombre and not self.segundo_apellido and not self.apellido_casada and not self.tercer_nombre:
            self.name = nombre_completo
            mensaje = "Debe de llenar los campos de nombres y apellidos (este campo se llenará automáticamente)"
            return {
                'warning': {
                    'title': "Notificación",
                    'message': mensaje,
                }
            }
        elif self.name == nombre_completo:
            pass
        else:
            self.name = nombre_completo
        existe_codigo = self.env['hr.codigo.employee'].search(
            [('identification_employee_id', '=', self.identification_id)])
        if existe_codigo:
            existe_codigo.primer_nombre = self.primer_nombre
            existe_codigo.segundo_nombre = self.segundo_nombre
            existe_codigo.tercer_nombre = self.tercer_nombre
            existe_codigo.primer_apellido = self.primer_apellido
            existe_codigo.segundo_apellido = self.segundo_apellido
            existe_codigo.apellido_casada = self.apellido_casada

    @api.onchange('mobile_phone',  'work_email', 'private_email', 'phone', 'km_home_work', 'certificate',
                  'study_field', 'study_school', 'discapacidad', 'nit', 'igss', 'marital', 'spouse_complete_name', 'spouse_birthdate',
                  'children', 'emergency_contact', 'emergency_phone', 'gender', 'birthday', 'departamento_id', 'municipio_id',
                  'address_home_id', 'bank_account_id')
    def _onchange_employee_data(self):
        existe_codigo = self.env['hr.codigo.employee'].search([('identification_employee_id', '=', self.identification_id)])
        if existe_codigo:
            fields_to_update = {
                'mobile_phone': self.mobile_phone,
                # 'work_phone': self.work_phone,
                'work_email': self.work_email,
                'private_email': self.private_email,
                'phone': self.phone,
                'km_home_work': self.km_home_work,
                'certificate': self.certificate,
                'study_field': self.study_field,
                'study_school': self.study_school,
                'discapacidad': self.discapacidad,
                'nit': self.nit,
                'igss': self.igss,
                'marital': self.marital,
                'spouse_complete_name': self.spouse_complete_name,
                'spouse_birthdate': self.spouse_birthdate,
                'children': self.children,
                'emergency_contact': self.emergency_contact,
                'emergency_phone': self.emergency_phone,
                'gender': self.gender,
                'birthday': self.birthday,
                'departamento_id': self.departamento_id.id if self.departamento_id else False,
                'municipio_id': self.municipio_id.id if self.municipio_id else False,
                'address_home_id': self.address_home_id.id if self.address_home_id else False,
                'bank_account_id': self.bank_account_id.id if self.bank_account_id else False,
                # 'x_employee_family': self.x_employee_family if self.x_employee_family else False,
                # 'employee_educational': self.employee_educational if self.employee_educational else False,
                # 'employee_work_history': self.employee_work_history if self.employee_work_history else False,
                # 'employee_licencia': self.employee_licencia if self.employee_licencia else False,
            }
            existe_codigo.write({key: value for key, value in fields_to_update.items() if value})

    @api.onchange('address_home_id')
    def _onchange_address_home_id(self):
        if self.address_home_id:
              self.nit = self.address_home_id.vat
              bank = self.address_home_id.bank_ids[:1]
              if bank:
                  self.bank_account_id = bank.id
        else:
            self.nit = False


    @api.onchange('job_id')
    def _onchange_job_id(self):
        if self.job_id:
            self.job_title = self.job_id.name

    @api.onchange('departamento_id')
    def _onchange_departamento_id(self):
        if self.departamento_id:
            return {
                'domain': {
                    'municipio_id': [('departamento_id', '=', self.departamento_id.id)]
                }
            }
        else:
            return {
                'domain': {
                    'municipio_id': []
                }
            }

    def EnviarMensaje(self, idchat, mensaje, urlimagen):
        try:
            json_str = '{"numero": "' + idchat + '", ' \
                                                 '"texto": "' + mensaje + '", ' \
                                                                          '"url": "' + str(urlimagen) + '"}'
            data = json.loads(json_str)
            #wsdl = 'http://mix.xelapan.com:55/Alertas.asmx?WSDL'
            wsdl = 'https://ws.xelapan.net/Alertas.asmx?WSDL'
            client = Client(wsdl=wsdl)
            client.service.EnviarMsj(str(data))

        except Exception as x:
            print('error al consultar datos')
            logger.exception(str(x))
        # @api.onchange('registration_number')
        # def _onchange_registration_number(self):
        #     for rec in self:
        #         existe_codigo = self.env['hr.codigo.employee'].search(
        #             [('identification_employee_id', '=', rec.identification_id)])
        #         if existe_codigo:
        #             rec.registration_number = str(existe_codigo.codigo_empleado)
        #         else:
        #             rec.registration_number = str(rec.codigo_empleado)
        #
        #             self.env.cr.commit()
        #             raise UserError("Favor de generar el código con el boton de generar código")

#     x_area = fields.Many2one('x_area', field_description='Area', String='Area', store=True)
#     parent_id = fields.Many2one(
#         'hr.employee',
#         string="Jefe Directo",
#         domain="['|',('x_empresa_a_facturar', 'in', allowed_company_ids),('company_id', 'in', allowed_company_ids)]"
#     )
#
#     @api.model
#     @api.onchange('department_id')
#     def area(self):
#         if self.department_id:
#             self.x_area = False
#             registros_filtrados = self.env['x_area'].search(
#                 [('x_departamento.id', '=', self.department_id.id)])
#             if registros_filtrados:
#                 return {'domain': {'x_area': [('id', 'in', registros_filtrados.ids)]}}
#             else:
#                 return {'domain': {'x_area': [('id', '=', 0)]}}
#         else:
#             self.x_area = False
#
#     @api.model
#     def search(self, args, offset=0, limit=None, order=None, count=False):
#         current_user = self.env.user
#         allowed_company_ids = self.env.context.get('allowed_company_ids', False)
#         if current_user and current_user.has_group('__export__.res_groups_102_218f9d91'):  # GTH acceso a todos los empleados desde todas las empresas asignadas 47
#             # Si el usuario pertenece al grupo deseado, se muestran todos los empleados de sus empresas asignadas
#             args.append(('company_id', 'in', current_user.company_ids.ids))
#             return super(HrEmployee, self).search(args, offset=offset, limit=limit, order=order, count=count)
#         elif current_user and current_user.has_group('__export__.res_groups_103_7311d420'):  # Nominas acceso a los demas empleados seleccionando la empresa 47
#             # Si el usuario no pertenece al grupo, se filtra por los empleados asociados a él
#             args.append(('company_id', 'in', allowed_company_ids))
#             return super(HrEmployee, self).search(args, offset=offset, limit=limit, order=order, count=count)
#         elif current_user and current_user.has_group('__export__.res_groups_101_1c577e17'):  # Mantenimiento 47
#             # Si el usuario no pertenece al grupo, se filtra por los empleados por empresa a facturar
#             args.append(('x_empresa_a_facturar.id', 'in', allowed_company_ids))
#             return super(HrEmployee, self).search(args, offset=offset, limit=limit, order=order, count=count)
#         else: # acceso solo a informacion personal
#             args.append(('user_id.id', '=', current_user.id))
#             args.append(('company_id', 'in', allowed_company_ids))
#             return super(HrEmployee, self).search(args, offset=offset, limit=limit, order=order, count=count)