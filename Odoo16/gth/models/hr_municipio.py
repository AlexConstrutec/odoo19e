from odoo import models, fields, api, exceptions


class HrMunicipioUser(models.Model):
    _name = 'hr.municipio'
    _description = 'Municipio de Nacimiento'

    name = fields.Char(string='Nombre', store=True)
    code = fields.Integer(string='Codigo', store=True)
    departamento_id = fields.Many2one('hr.departamento', string='Departamento', store=True)
    @api.model
    def create(self, vals_list):
        # for vals in vals_list:
        #     # Convertir el nombre entrante a mayúsculas
        #     new_name_upper = vals.get('name', '').upper()
        #
        #     # Comprobar si ya existe un registro con el mismo nombre (convertido a mayúsculas)
        #     existing_record = self.env['your.model.name'].search([('name', '=', new_name_upper)], limit=1)
        #     if existing_record:
        #         raise exceptions.ValidationError(f"El nombre '{vals.get('name')}' ya existe.")
        #
        #     # Guardar el nombre en mayúsculas en el diccionario vals
        #     vals['name'] = new_name_upper

        return super(HrMunicipioUser, self).create(vals_list)
