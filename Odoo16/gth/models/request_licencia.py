from odoo import models, fields, api

class License(models.Model):
    _name = 'request.licencia'
    _description = 'Licencia'
    name = fields.Char('Nombre', required=True)
    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'El campo "Experiencia" debe ser único.'),
    ]