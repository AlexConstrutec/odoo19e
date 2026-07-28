from odoo import models, fields, api

class Jornada(models.Model):
    _name = 'request.jornada'
    _description = 'Jornada'
    name = fields.Char('Nombre', required=True)
    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'El campo "Experiencia" debe ser único.'),
    ]