from odoo import models, fields, api

class Experiencia(models.Model):
    _name = 'request.experiencia'
    _description = 'Experiencia'
    name = fields.Char('Nombre', required=True)
    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'El campo "Experiencia" debe ser único.'),
    ]