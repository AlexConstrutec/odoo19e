from odoo import models, fields, api, exceptions

class HrCodigoEmployeeUser(models.Model):
    _name = 'hr.codigo.employee'
    _description = 'Código de empleado'

    identification_employee_id = fields.Char(string="DPI", store=True)
    codigo_empleado = fields.Integer(string="Código de empleado", store=True)
    primer_nombre = fields.Char(string="Primer nombre", store=True)
    segundo_nombre = fields.Char(string="Segundo nombre", store=True)
    tercer_nombre = fields.Char(string="Tercer nombre", store=True)
    primer_apellido = fields.Char(string="Primer apellido", store=True)
    segundo_apellido = fields.Char(string="Segundo apellido", store=True)
    apellido_casada = fields.Char(string="Apellido de casada", store=True)
    mobile_phone = fields.Char(string="Teléfono móvil", store=True)
    # work_phone = fields.Char(string="Teléfono de trabajo", store=True)
    work_email = fields.Char(string="Correo electrónico laboral", store=True)
    private_email = fields.Char(string="Correo electrónico privado", store=True)
    phone = fields.Char(string="Teléfono", store=True)
    km_home_work = fields.Integer(string="Distancia casa-trabajo", store=True)
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
    ], string='Nivel de certificado',  store=True)
    study_field = fields.Char(string='Profesion', store=True)
    study_school = fields.Char(string='Escuela', store=True)
    discapacidad = fields.Selection([
        ('1', 'Ninguna'),
        ('2', 'Discapacidad auditiva'),
        ('3', 'Discapacidad visual'),
        ('4', 'Discapacidad múltiple'),
        ('5', 'Discapacidad física o motora'),
        ('6', 'Discapacidad intelectual'),
        ('7', 'Otra'),
    ], string='Discapacidad',  store=True)
    nit = fields.Char(string="NIT", store=True)
    igss = fields.Char(string="IGSS", store=True)
    marital = fields.Selection([
        ('single', 'Single'),
        ('married', 'Married'),
        ('cohabitant', 'Legal Cohabitant'),
        ('widower', 'Widower'),
        ('divorced', 'Divorced')
    ], string='Marital Status', groups="hr.group_hr_user", store=True)
    spouse_complete_name = fields.Char(string="Nombre completo del cónyuge", store=True)
    spouse_birthdate = fields.Date(string="Fecha de nacimiento del cónyuge", store=True)
    children = fields.Integer(string="Cantidad de hijos", store=True)
    emergency_contact = fields.Char(string="Contacto de emergencia", store=True)
    emergency_phone = fields.Char(string="Teléfono de emergencia", store=True)
    gender = fields.Selection([
        ('male', 'Masculino'),
        ('female', 'Femenino'),
        ('other', 'Otro')
    ], string='Género', groups="hr.group_hr_user", store=True)
    birthday = fields.Date(string="Fecha de nacimiento", store=True)
    departamento_id = fields.Many2one('hr.departamento', string="Departamento", store=True)
    municipio_id = fields.Many2one('hr.municipio', string="Municipio", store=True)
    address_home_id = fields.Many2one('res.partner', string="Dirección de casa", store=True)
    bank_account_id = fields.Many2one('res.partner.bank', string="Cuenta bancaria", store=True)
    # resource_calendar_id = fields.Many2one('resource.calendar', string="Calendario", store=True)
    # x_employee_family = fields.One2many('hr.employee.family', 'x_employee_id', string='Carga Familiar', store=True)
    # employee_educational = fields.One2many('hr.employee.educational', 'employee_id', string='Educación', store=True)
    # employee_work_history = fields.One2many('hr.employee.work.history', 'employee_id', string='Datos Laborales', store=True)
    # employee_licencia = fields.One2many('hr.employee.licencia', 'employee_id', string='Licencias de Conducir', store=True)

    _sql_constraints = [
        ('identification_employee_id_unique', 'unique(identification_employee_id)', 'El DPI debe ser único.')
    ]