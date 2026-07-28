from odoo import models, fields, api

class FacturaSelectionWizard(models.TransientModel):
    _name = 'factura.selection.wizard'
    _description = 'Wizard para seleccionar facturas'

    factura_ids = fields.Many2many('account.move', string='Facturas',
        domain=[('bolson_id', '=', False), ('move_type', '=', 'out_invoice'), ('state', '=', 'posted')])

    def action_add_facturas(self):
        bolson_id = self.env.context.get('active_id')
        if bolson_id:
            bolson = self.env['bolson.bolson'].browse(bolson_id)
            for factura in self.factura_ids:
                factura.bolson_id = bolson_id  # Actualiza el bolson_id en las facturas seleccionadas
            return {'type': 'ir.actions.act_window_close'}

class ChequesSelectionWizard(models.TransientModel):
    _name = 'pago.selection.wizard'
    _description = 'Wizard para seleccionar pagos'

    pagos_ids = fields.Many2many('account.payment', string='Pagos',
        domain=[('state', '=', 'posted')])

    def action_add_pagos(self):
        bolson_id = self.env.context.get('active_id')
        if bolson_id:
            bolson = self.env['bolson.bolson'].browse(bolson_id)
            for pago in self.pagos_ids:
                pago.bolson_id = bolson_id  # Actualiza el bolson_id en las facturas seleccionadas
            return {'type': 'ir.actions.act_window_close'}
