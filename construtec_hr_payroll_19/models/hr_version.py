from odoo import fields, models


# class HrContractStatus(models.Model):
#     _name = 'hr.contract.status'
#     _description = 'Estado de contrato'
#
#     name = fields.Char(string='Nombre', required=True)
#     active = fields.Boolean(string='Activo', default=True)
#
#
# class HrContractPaymentFrequency(models.Model):
#     _name = 'hr.contract.payment.frequency'
#     _description = 'Frecuencia de pago de contrato'
#
#     name = fields.Char(string='Nombre', required=True)
#     active = fields.Boolean(string='Activo', default=True)
#
#
# class HrEmpresaFacturar(models.Model):
#     _name = 'hr.empresa.facturar'
#     _description = 'Empresa a facturar'
#
#     name = fields.Char(string='Nombre', required=True)
#     active = fields.Boolean(string='Activo', default=True)


class HrVersion(models.Model):
    _inherit = 'hr.version'

    # tiempo_contrato = fields.Selection(
    #     [('TC', 'Tiempo Completo'), ('TP', 'Tiempo Parcial')],
    #     string='Tiempo de Contrato', default='TC')
    x_bonificacion_fija = fields.Float(string='Bonificación Fija')
    x_bonificacion_incentivo = fields.Float(string='Bonificación Incentivo')
    x_bonificacion_extra = fields.Float(string='Bonificación Extra')
    #x_horas_extra_valor = fields.Float(string='Horas Extra Valor')
    x_bonificacion_productividad = fields.Float(string='Bonificación Productividad')
    #estado_contrato = fields.Many2one('hr.contract.status', string='Estado de contrato')
    #frecuencia_pago = fields.Many2one('hr.contract.payment.frequency', string='Frecuencia de pago')
    #empresa_facturar = fields.Many2one('hr.empresa.facturar', string='Empresa a facturar', index=True)
