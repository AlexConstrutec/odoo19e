from odoo import models, fields, api, exceptions
from odoo.exceptions import UserError


# class HrJobFactor(models.Model):
#     _name = "hr.job.factor"
#     _description = 'Factor'
#     name = fields.Char(string="Nombre", store=True, unique=True, required=True)
#     _sql_constraints = [
#         ('unique_name', 'unique(name)', 'El nombre del factor debe ser único.')
#     ]
# class HrJobFactorDescription(models.Model):
#     _name = "hr.job.factor.description"
#     _description = 'Descripción de Factor'
#     name = fields.Char(string="Descripcion", store=True, required=True)
#     grado = fields.Selection(
#         [('I', 'I'), ('II', 'II'), ('III', 'III'), ('IV', 'IV'), ('V', 'V'), ('VI', 'VI'), ('VII', 'VII')],
#         string="Grado", store=True, required=True)
#     punteo = fields.Integer(string="Punteo", store=True, required=True)
#     factor_id = fields.Many2one('hr.job.factor', string="Factor", store=True, required=True)
#     _sql_constraints = [
#         ('unique_factor_description', 'unique(name, factor_id)',
#          'La descripción del factor debe ser única por factor.')
#     ]
# class HrJobFactorPuesto(models.Model):
#     _name = "hr.job.factor.puesto"
#     _description = 'Factores en Puestos'
#     job_id = fields.Many2one('hr.job', string="Puesto", store=True, required=True)
#     factor_id = fields.Many2one('hr.job.factor', string="Factor", store=True, required=True)
#     factor_description = fields.Many2one('hr.job.factor.description', string="Descripción", store=True, domain="[('factor_id', '=', factor_id)]", required=True)
#     punteo = fields.Integer(string="Punteo", readonly=True, related="factor_description.punteo")
#     grado = fields.Selection(string="Grado", readonly=True, related="factor_description.grado")
#     publicar_en_web = fields.Boolean(string="Publicar en la web")
#
#     @api.onchange('factor_description')
#     def _onchange_factor_description(self):
#         if self.factor_description:
#             self.punteo = self.factor_description.punteo
#             self.grado = self.factor_description.grado
#         else:
#             self.punteo = 0
#             self.grado = ''
#
#     @api.depends('factor_description')
#     def _compute_related_fields(self):
#         for record in self:
#             if record.factor_description:
#                 record.punteo = record.factor_description.punteo
#                 record.grado = record.factor_description.grado
#             else:
#                 record.punteo = 0
#                 record.grado = ''

class HrJob(models.Model):
    _inherit = 'hr.job'

    requisitos = fields.Text(string='Requisitos')
    ofrecimientos = fields.Text(string='Ofrecimientos')
    funciones_especificas = fields.Html(string='Funciones Especificas')
    funcion_principal = fields.Text(string='Función Principal')
    # funcion_principal = fields.Text(string='Funcion Principal')
    # funciones_especificas = fields.One2many('hr.job.funciones', 'job_id', string='Funciones Especificas')
    # factor_puesto = fields.One2many('hr.job.factor.puesto', 'job_id', string="Factores", store=True)
    # rango_minimo = fields.Integer(string="Mínimo", store=True)
    # rango_maximo = fields.Integer(string="Máximo", store=True)
    # rango_actual = fields.Integer(string="Actual", store=True, compute="_compute_rango_actual")
    # puesto_reporta = fields.Many2one('hr.job', string="Puesto que reporta", store=True)
    # puestos_supervisa = fields.One2many('hr.job.supervisa', 'x_job_id', string="Puestos que supervisa", store=True)
    # responsabilidades = fields.One2many('x_respon', 'x_par', string="Responsabilidades", store=True)
    # comunicacion_interna = fields.One2many('x_interna', 'x_inter', string="Comunicación interna", store=True)
    # comunicacion_externa = fields.One2many('x_comunicacion', 'x_exter', string="Comunicación externa", store=True)

    # @api.depends('factor_puesto','competencia_puesto')
    # def _compute_rango_actual(self):
    #     for record in self:
    #         record.rango_actual = 0
    #         for factor in record.factor_puesto:
    #             record.rango_actual += factor.punteo
    #         for competencia in record.competencia_puesto:
    #             record.rango_actual += competencia.punteo

    #
    # @api.onchange('rango_minimo', 'rango_maximo')
    # def _check_minimo_maximo(self):
    #     if self.rango_minimo > self.rango_maximo:
    #         raise UserError("El rango mínimo no puede ser mayor al rango máximo.")

    # @api.onchange('factor_description')
    # def _onchange_factor_description(self):
    #     if self.factor_description:
    #         self.punteo = self.factor_description.punteo
    #         self.grado = self.factor_description.grado
    #     else:
    #         self.punteo = 0
    #         self.grado = ''
    #     self._update_related_fields()
    #
    # @api.depends('factor_description')
    # def _compute_related_fields(self):
    #     for record in self:
    #         if record.factor_description:
    #             record.punteo = record.factor_description.punteo
    #             record.grado = record.factor_description.grado
    #         else:
    #             record.punteo = 0
    #             record.xgrado = ''
    #     self._update_related_fields()

    # def _update_related_fields(self):
    #     self._compute_related_fields()
        # Actualizar otros campos relacionados si es necesario

# class HrJobFunciones(models.Model):
#     _name = 'hr.job.funciones'
#     _description = 'Funciones del puesto'
#
#     name = fields.Text(string='Funcion', required=True)
#     job_id = fields.Many2one('hr.job', string='Puesto', required=True, ondelete='cascade')





