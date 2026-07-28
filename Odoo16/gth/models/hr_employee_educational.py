from odoo import models, fields, api, exceptions


class HrEmployeeEducationalUser(models.Model):
    _name = 'hr.employee.educational'
    _description = 'Circulo Familiar'

    employee_id = fields.Many2one('hr.employee', string='Empleado', store=True)
    establecimiento = fields.Char(string='Establecimiento', store=True)
    año = fields.Integer(string='Año', store=True)
    fecha_inicio = fields.Date(string='Fecha de Inicio', store=True)
    fecha_fin = fields.Date(string='Fecha de Fin', store=True)
    nivel_academico = fields.Selection([
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
    ], string='Nivel Académico', store=True)
    titulo = fields.Char(string='Título', store=True)