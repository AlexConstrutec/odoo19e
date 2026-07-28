from collections import defaultdict

from odoo import models, fields, api
from datetime import date, datetime


class Contract(models.Model):
    _inherit = 'hr.contract'

    wage = fields.Float(string='Salario Base', store=True)
    #isr = fields.Float(string='	ISR Asalariados', store=True) va a ser un concepto de anticipo
    #ayuvi = fields.Float(string='AYUVI', store=True) va en el modulo de prestamos
    tiempo_contrato = fields.Selection([('TC', 'Tiempo Completo'), ('TP', 'Tiempo Parcial')], string='Tiempo de Contrato', default='TC', store=True)
    #salario_base = fields.Float(string='Salario Base', store=True, help="Odoo 13 Perfil Salarial x_perfil.x_salario_base")
    bonificacion_fija = fields.Float(string='Bonificación Fija', store=True, help="Odoo 13 Perfil Salarial x_perfil.Bonificacion Fija")
    bonificacion_incentivo = fields.Float(string='Bonificación Incentivo', store=True, help="Odoo 13 Perfil Salarial x_perfil.x_bonificacion_incentivo")
    bonificacion_extra = fields.Float(string='Bonificación Extra', store=True, help="Odoo 13 Perfil Salarial x_perfil.x_bonificaciones_extra")
    #horas_extra_porcentaje = fields.Float(string='Horas Extra %', store=True, help="Odoo 13 Perfil Salarial x_perfil.x_horas_extra_p", default=100.0)
    horas_extra_valor = fields.Float(string='Horas Extra Valor', store=True, help="Odoo 13 Perfil Salarial x_perfil.x_valor_horas_extra")
    #horas_extra_bonificacion = fields.Float(string='Horas Extra Bonificación', store=True, help="Odoo 13 Perfil Salarial x_perfil.x_horas_extra_bonificacion")
    bonificacion_productividad = fields.Float(string='Bonificación Productividad', store=True)
    estado_contrato = fields.Many2one('hr.contract.status', string='Estado de contrato', store=True)
    frecuencia_pago = fields.Many2one('hr.contract.payment.frequency', string='Frecuencia de pago', store=True)
    empresa_facturar = fields.Many2one('hr.empresa.facturar', string='Empresa a facturar', store=True, index=True)

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if self.employee_id:
            self.name = self.employee_id.name

class HrContractStatus(models.Model):
    _name = 'hr.contract.status'
    _description = 'Estado de contrato'

    name = fields.Char(string='Nombre', required=True)
    active = fields.Boolean(string='Activo', default=True)

class HrContractPaymentFrequency(models.Model):
    _name = 'hr.contract.payment.frequency'
    _description = 'Frecuencia de pago de contrato'

    name = fields.Char(string='Nombre', required=True)
    active = fields.Boolean(string='Activo', default=True)

class HrEmpresaFacturar(models.Model):
    _name = 'hr.empresa.facturar'
    _description = 'Empresa a facturar'

    name = fields.Char(string='Nombre', required=True)
    active = fields.Boolean(string='Activo', default=True)
