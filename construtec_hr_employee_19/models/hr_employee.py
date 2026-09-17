import datetime

from odoo import api, fields, models
from odoo.exceptions import UserError

from .hr_employee_selections import COMUNIDAD_LINGUISTICA, DISCAPACIDAD, NIVEL_ACADEMICO, PUEBLO_PERTENENCIA

# Campos de "datos personales" editables desde Community (construtec_account_payment_order_19,
# hr_employee.py) - ver `sync_personal_data_from_community()` más abajo. Lista blanca explícita:
# nunca se acepta un `write()` genérico desde afuera, solo estos campos, sean cuales sean los que
# venga en el payload - así una credencial de integración filtrada nunca puede escribir salario,
# banco, ni ningún otro campo de hr.employee que no sea este set acordado.
PERSONAL_DATA_FIELDS = (
    'primer_nombre', 'segundo_nombre', 'tercer_nombre', 'primer_apellido', 'segundo_apellido',
    'apellido_casada', 'discapacidad', 'nit', 'igss', 'pueblo_pertenencia', 'comunidad_linguistica',
    'marital', 'sex', 'birthday', 'children', 'identification_id', 'permit_no', 'certificate',
    'study_field',
)


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    codigo_empleado = fields.Integer(string='Código de empleado')
    primer_nombre = fields.Char(string='Primer nombre')
    segundo_nombre = fields.Char(string='Segundo nombre')
    tercer_nombre = fields.Char(string='Tercer nombre')
    primer_apellido = fields.Char(string='Primer apellido')
    segundo_apellido = fields.Char(string='Segundo apellido')
    apellido_casada = fields.Char(string='Apellido de casada')
    nit = fields.Char(string='NIT')
    igss = fields.Char(string='IGSS')
    codigo_banco = fields.Char(string='Código Banco', help='Código Interno usado para la carga de cuentas '
                                                             '(CSV Banco) — ver "Generar CSV Banco" en el lote de '
                                                             'nómina.')
    departamento_id = fields.Many2one('hr.departamento', string='Departamento')
    municipio_id = fields.Many2one('hr.municipio', string='Municipio')
    jornada_trabajo = fields.Selection([
        ('1', 'Diurna'),
        ('2', 'Mixta'),
        ('3', 'Nocturna'),
        ('4', 'No está sujeto a jornada'),
        ('5', 'Tiempo Parcial'),
    ], string='Jornada de trabajo', default='1')
    discapacidad = fields.Selection(DISCAPACIDAD, string='Discapacidad', default='1')
    pueblo_pertenencia = fields.Selection(
        PUEBLO_PERTENENCIA, string='Pueblo de pertenencia',
        help='Antes de esta pasada, el Informe del Empleador mandaba siempre el mismo valor fijo '
             'para todos los empleados - ver la nota en hr_employee_selections.py sobre los '
             'códigos numéricos de este catálogo, no verificados aún contra el oficial de MITRAB.')
    comunidad_linguistica = fields.Selection(
        COMUNIDAD_LINGUISTICA, string='Comunidad Lingüística',
        help='Mismo caso que Pueblo de pertenencia - ver la nota en hr_employee_selections.py.')
    certificate = fields.Selection(NIVEL_ACADEMICO, string='Nivel de certificado', default='other',
                                    groups='hr.group_hr_user', tracking=True)
    employee_family = fields.One2many('hr.employee.family', 'employee_id', string='Círculo Familiar')
    employee_educational = fields.One2many('hr.employee.educational', 'employee_id', string='Educación')
    employee_work_history = fields.One2many('hr.employee.work.history', 'employee_id', string='Datos Laborales')
    employee_licencia = fields.One2many('hr.employee.licencia', 'employee_id', string='Licencias de Conducir')
    imprimir_nombre_conyuge = fields.Boolean(string='Imprimir nombre de Cónyuge (IRTRA)')
    calle = fields.Char(string='Dirección', related='work_contact_id.street')
    edad = fields.Integer(string='Edad', compute='_compute_edad')
    mes_cumpleanios = fields.Char(string='Mes Cumpleaños', compute='_compute_mes_cumpleanios')
    historial_laboral = fields.One2many(
        'hr.employee.history.job.salary', compute='_compute_historial_laboral', string='Historial Laboral')

    @api.depends('birthday')
    def _compute_mes_cumpleanios(self):
        meses = {
            1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril', 5: 'Mayo', 6: 'Junio',
            7: 'Julio', 8: 'Agosto', 9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre',
        }
        for employee in self:
            employee.mes_cumpleanios = meses.get(employee.birthday.month, '') if employee.birthday else ''

    def _compute_edad(self):
        today = datetime.date.today()
        for employee in self:
            if employee.birthday:
                employee.edad = today.year - employee.birthday.year - (
                    (today.month, today.day) < (employee.birthday.month, employee.birthday.day))
            else:
                employee.edad = 0

    @api.depends('identification_id')
    def _compute_historial_laboral(self):
        for employee in self:
            employee.historial_laboral = self.env['hr.employee.history.job.salary'].search([
                ('identification_employee_id', '=', employee.identification_id),
            ])

    @api.onchange('identification_id')
    def _onchange_identification_id(self):
        if self.identification_id and self.company_id:
            duplicate = self.env['hr.employee'].search([
                ('identification_id', '=', self.identification_id),
                ('company_id', '=', self.company_id.id),
                ('id', '!=', self._origin.id),
                ('active', 'in', [True, False]),
            ])
            if duplicate:
                if not duplicate.active:
                    raise UserError(self.env._('El colaborador con este DPI está archivado en esta empresa.'))
                raise UserError(self.env._('Ya existe un empleado con este DPI en esta empresa.'))

        existing = self.env['hr.codigo.employee'].search(
            [('identification_employee_id', '=', self.identification_id)], limit=1)
        if existing:
            existing.apply_to_employee(self)

    @api.onchange('primer_nombre', 'segundo_nombre', 'tercer_nombre', 'primer_apellido', 'segundo_apellido',
                  'apellido_casada', 'name')
    def _onchange_name(self):
        partes = [self.primer_nombre, self.segundo_nombre, self.tercer_nombre,
                  self.primer_apellido, self.segundo_apellido, self.apellido_casada]
        nombre_completo = ' '.join(p for p in partes if p)
        tiene_nombres = any(partes)
        if not self.name and not tiene_nombres:
            return
        if self.name and not tiene_nombres:
            self.name = nombre_completo
            return {'warning': {
                'title': self.env._('Notificación'),
                'message': self.env._(
                    'Debe llenar los campos de nombres y apellidos (este campo se llenará automáticamente).'),
            }}
        if self.name != nombre_completo:
            self.name = nombre_completo

        existing = self.env['hr.codigo.employee'].search(
            [('identification_employee_id', '=', self.identification_id)], limit=1)
        if existing:
            existing.write({
                'primer_nombre': self.primer_nombre, 'segundo_nombre': self.segundo_nombre,
                'tercer_nombre': self.tercer_nombre, 'primer_apellido': self.primer_apellido,
                'segundo_apellido': self.segundo_apellido, 'apellido_casada': self.apellido_casada,
            })

    @api.onchange('mobile_phone', 'work_email', 'private_email', 'phone', 'km_home_work', 'certificate',
                  'study_field', 'study_school', 'discapacidad', 'nit', 'igss', 'marital', 'spouse_complete_name',
                  'spouse_birthdate', 'children', 'emergency_contact', 'emergency_phone', 'sex', 'birthday',
                  'departamento_id', 'municipio_id', 'work_contact_id')
    def _onchange_employee_data(self):
        existing = self.env['hr.codigo.employee'].search(
            [('identification_employee_id', '=', self.identification_id)], limit=1)
        if existing:
            existing.update_from_employee(self)

    @api.onchange('work_contact_id')
    def _onchange_work_contact_id(self):
        if self.work_contact_id:
            self.nit = self.work_contact_id.vat
            bank = self.work_contact_id.bank_ids[:1]
            if bank:
                self.bank_account_ids = [(4, bank.id)]
        else:
            self.nit = False

    @api.onchange('departamento_id')
    def _onchange_departamento_id(self):
        return {'domain': {'municipio_id': [('departamento_id', '=', self.departamento_id.id)]}} \
            if self.departamento_id else {'domain': {'municipio_id': []}}

    @api.onchange('country_id')
    def _onchange_nacionalidad(self):
        if not self.country_id:
            self.country_id = self.env.ref('base.gt', raise_if_not_found=False)

    def generar_codigo(self):
        Codigo = self.env['hr.codigo.employee']
        for employee in self:
            if not employee.identification_id:
                raise UserError(self.env._('Requiere de un DPI para generar el código.'))

            existing = Codigo.search([('identification_employee_id', '=', employee.identification_id)], limit=1)
            if existing:
                employee.codigo_empleado = existing.codigo_empleado
                employee.registration_number = str(existing.codigo_empleado)
                existing.apply_to_employee(employee)
                continue

            if employee.registration_number:
                codigo_empleado = int(employee.registration_number)
                if Codigo.search_count([('codigo_empleado', '=', codigo_empleado)]):
                    raise UserError(self.env._('Ya existe un código de empleado %s.', codigo_empleado))
            else:
                last = Codigo.search([], order='codigo_empleado desc', limit=1)
                codigo_empleado = (last.codigo_empleado + 1) if last else 7580
                employee.registration_number = str(codigo_empleado)

            employee.codigo_empleado = codigo_empleado
            new_codigo = Codigo.create({
                'identification_employee_id': employee.identification_id,
                'codigo_empleado': codigo_empleado,
            })
            new_codigo.update_from_employee(employee)

    def registrar_historial_puestos(self):
        self.ensure_one()
        return {
            'name': self.env._('Historial de puestos de trabajo'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.employee.history.job.salary',
            'view_mode': 'form',
            'domain': [('identification_employee_id', '=', self.identification_id)],
            'context': {'default_identification_employee_id': self.identification_id},
            'target': 'new',
        }

    def sync_personal_data_from_community(self, vals):
        """Recibe una actualización de "datos personales" empujada desde Community
        (construtec_account_payment_order_19, hr_employee.py::write()) - Community es la
        fuente para ESTOS campos (personas sin acceso a nómina cargan la info ahí), Enterprise
        sigue siendo la fuente para todo lo demás (estado laboral, salario, banco, etc.).

        Llamado vía XML-RPC por el mismo usuario de integración ya usado para Órdenes de
        Pago/Marcajes de Asistencia (`group_payment_order_sync_integration`) - ese usuario NO
        necesita permiso de escritura real sobre hr.employee para esto: el `sudo()` de abajo
        resuelve la escritura, el permiso que sí necesita es poder LEER hr.employee para que
        Odoo le deje invocar el método en absoluto (ver ir.model.access.csv).

        Lista blanca explícita (`PERSONAL_DATA_FIELDS`) - cualquier clave fuera de esa lista
        en `vals` se ignora en silencio, nunca se escribe. `nacionalidad_code`/`pais_origen_code`
        (código ISO alpha-2, ej. 'GT') y `municipio_nombre` (texto libre) llegan aparte y se
        resuelven aquí mismo, nunca como ids directos - son los únicos 3 campos de este set que
        son relaciones en vez de texto/selección plana."""
        self.ensure_one()
        vals_filtrados = {k: v for k, v in vals.items() if k in PERSONAL_DATA_FIELDS}

        nacionalidad_code = vals.get('nacionalidad_code')
        if nacionalidad_code:
            country = self.env['res.country'].search([('code', '=', nacionalidad_code.upper())], limit=1)
            if country:
                vals_filtrados['country_id'] = country.id

        pais_origen_code = vals.get('pais_origen_code')
        if pais_origen_code:
            country = self.env['res.country'].search([('code', '=', pais_origen_code.upper())], limit=1)
            if country:
                vals_filtrados['country_of_birth'] = country.id

        municipio_nombre = vals.get('municipio_nombre')
        if municipio_nombre:
            municipio = self.env['hr.municipio'].search([('name', '=ilike', municipio_nombre)], limit=1)
            if municipio:
                vals_filtrados['municipio_id'] = municipio.id
            # Sin match exacto: no se adivina (mismo criterio ya usado en este proyecto para
            # proveedores/materiales "parecidos" - solo autoresuelve con un único candidato
            # claro) - `municipio_id` queda como estaba, alguien de RR.HH. lo resuelve a mano.

        if vals_filtrados:
            self.sudo().write(vals_filtrados)
