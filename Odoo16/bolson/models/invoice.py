# -*- encoding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class AccountMove(models.Model):
    _inherit = 'account.move'

    bolson_id = fields.Many2one("bolson.bolson", string="Liquidacion", ondelete='restrict', store=True)
    no_liquidacion = fields.Integer(string="Orden Mix", store=True, related='bolson_id.no_liquidacion', readonly=False)

    @api.onchange('bolson_id')
    def _onchange_bolson_id(self):
        if self.bolson_id:
            self.no_liquidacion = self.bolson_id.no_liquidacion

    @api.onchange('no_liquidacion')
    def _onchange_no_liquidacion(self):
        if self.no_liquidacion:
            thBolson = self.env['bolson.bolson'].search([('no_liquidacion', '=', self.no_liquidacion)], limit=1)
            if thBolson:
                self.bolson_id = thBolson.id

    # def _compute_no_liquidacion(self):
    #     for rec in self:
    #         if rec.bolson_id:
    #             rec.no_liquidacion = rec.bolson_id.no_liquidacion
    @api.model_create_multi
    def create(self, vals_list):
        res = super(AccountMove, self).create(vals_list)
        if 'no_liquidacion' in vals_list:
            for rec in self:
                if rec.no_liquidacion:
                    thBolson = self.env['bolson.bolson'].search([('no_liquidacion', '=', rec.no_liquidacion)], limit=1)
                    if thBolson:
                        rec.bolson_id = thBolson.id
        return res

    def write(self, vals):
        res = super(AccountMove, self).write(vals)
        if 'no_liquidacion' in vals:
            for rec in self:
                if rec.no_liquidacion:
                    thBolson = self.env['bolson.bolson'].search([('no_liquidacion', '=', rec.no_liquidacion)], limit=1)
                    if thBolson:
                        rec.bolson_id = thBolson.id
        return res

