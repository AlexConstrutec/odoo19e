from odoo import fields, models


class HrWorkEntry(models.Model):
    _inherit = 'hr.work.entry'

    descripcion = fields.Char(string='Descripción')
    frecuencia_pago = fields.Many2one('hr.contract.payment.frequency', string='Frecuencia de pago',
                                       related='version_id.frecuencia_pago')
