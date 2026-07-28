from odoo import fields, models

from .hr_employee_selections import DISCAPACIDAD, NIVEL_ACADEMICO

# Campos que se copian tal cual entre hr.employee y hr.codigo.employee (mismo nombre en ambos lados).
IDENTITY_FIELDS = [
    'primer_nombre', 'segundo_nombre', 'tercer_nombre', 'primer_apellido', 'segundo_apellido', 'apellido_casada',
    'mobile_phone', 'work_email', 'private_email', 'phone', 'km_home_work', 'certificate', 'study_field',
    'study_school', 'discapacidad', 'nit', 'igss', 'marital', 'spouse_complete_name', 'spouse_birthdate',
    'children', 'emergency_contact', 'emergency_phone', 'birthday', 'departamento_id', 'municipio_id',
    'work_contact_id',
]
# Campos cuyo nombre difiere entre hr.employee y hr.codigo.employee: {campo en hr.codigo.employee: campo en hr.employee}
RENAMED_FIELDS = {
    'gender': 'sex',
}


class HrCodigoEmployee(models.Model):
    _name = 'hr.codigo.employee'
    _description = 'Código histórico de empleado'

    identification_employee_id = fields.Char(string='DPI', index=True)
    codigo_empleado = fields.Integer(string='Código de empleado')
    primer_nombre = fields.Char(string='Primer nombre')
    segundo_nombre = fields.Char(string='Segundo nombre')
    tercer_nombre = fields.Char(string='Tercer nombre')
    primer_apellido = fields.Char(string='Primer apellido')
    segundo_apellido = fields.Char(string='Segundo apellido')
    apellido_casada = fields.Char(string='Apellido de casada')
    mobile_phone = fields.Char(string='Teléfono móvil')
    work_email = fields.Char(string='Correo electrónico laboral')
    private_email = fields.Char(string='Correo electrónico privado')
    phone = fields.Char(string='Teléfono')
    km_home_work = fields.Integer(string='Distancia casa-trabajo (km)')
    certificate = fields.Selection(NIVEL_ACADEMICO, string='Nivel de certificado')
    study_field = fields.Char(string='Profesión')
    study_school = fields.Char(string='Escuela')
    discapacidad = fields.Selection(DISCAPACIDAD, string='Discapacidad')
    nit = fields.Char(string='NIT')
    igss = fields.Char(string='IGSS')
    marital = fields.Selection([
        ('single', 'Soltero/a'),
        ('married', 'Casado/a'),
        ('cohabitant', 'Unido/a de hecho'),
        ('widower', 'Viudo/a'),
        ('divorced', 'Divorciado/a'),
    ], string='Estado civil')
    spouse_complete_name = fields.Char(string='Nombre completo del cónyuge')
    spouse_birthdate = fields.Date(string='Fecha de nacimiento del cónyuge')
    children = fields.Integer(string='Cantidad de hijos')
    emergency_contact = fields.Char(string='Contacto de emergencia')
    emergency_phone = fields.Char(string='Teléfono de emergencia')
    gender = fields.Selection([
        ('male', 'Masculino'),
        ('female', 'Femenino'),
        ('other', 'Otro'),
    ], string='Género')
    birthday = fields.Date(string='Fecha de nacimiento')
    departamento_id = fields.Many2one('hr.departamento', string='Departamento')
    municipio_id = fields.Many2one('hr.municipio', string='Municipio')
    work_contact_id = fields.Many2one('res.partner', string='Contacto')
    bank_account_id = fields.Many2one('res.partner.bank', string='Cuenta bancaria')

    _sql_constraints = [
        ('identification_employee_id_unique', 'unique(identification_employee_id)', 'El DPI debe ser único.'),
    ]

    def _employee_field_map(self):
        """Mapa {campo hr.codigo.employee: campo hr.employee} para sincronizar datos entre ambos modelos."""
        mapping = {name: name for name in IDENTITY_FIELDS}
        mapping.update(RENAMED_FIELDS)
        return mapping

    def apply_to_employee(self, employee):
        """Copia los datos guardados de un DPI ya conocido hacia una nueva ficha de empleado (reingreso)."""
        self.ensure_one()
        vals = {emp_field: self[codigo_field] for codigo_field, emp_field in self._employee_field_map().items()}
        if self.bank_account_id:
            vals['bank_account_ids'] = [(4, self.bank_account_id.id)]
        employee.write({k: v.id if hasattr(v, 'id') else v for k, v in vals.items() if v or v == 0})

    def update_from_employee(self, employee):
        """Guarda/actualiza el snapshot de un empleado por su DPI, para reutilizarlo en un reingreso futuro."""
        self.ensure_one()
        vals = {codigo_field: employee[emp_field] for codigo_field, emp_field in self._employee_field_map().items()}
        vals = {k: (v.id if hasattr(v, 'id') else v) for k, v in vals.items()}
        if employee.bank_account_ids:
            vals['bank_account_id'] = employee.bank_account_ids[:1].id
        self.write(vals)
