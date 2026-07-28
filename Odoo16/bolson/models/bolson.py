# -*- encoding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

import logging

class BolsonBolson(models.Model):
    _name = 'bolson.bolson'
    _description = 'Bolson de facturas y cheques'
    _order = 'fecha desc'

    fecha = fields.Date(string="Fecha", required=True)
    name = fields.Char(string="Liquidacion", required=True, compute='_compute_th_name', store=True, readonly=False)
    facturas = fields.One2many("account.move", "bolson_id", string="Facturas", store=True, domain=[('payment_id', '=', False)])
    cheques = fields.One2many("account.payment", "bolson_id", string="Cheques", store=True, domain=[('reconciled_invoice_ids', '=', False),('reconciled_bill_ids', '=', False)])
    company_id = fields.Many2one("res.company", string="Company", required=True, default=lambda self: self.env.company.id)
    diario = fields.Many2one("account.journal", string="Diario", required=True)
    asiento = fields.Many2one("account.move", string="Asiento")
    usuario_id = fields.Many2one("res.users", string="Usuario", default=lambda self: self.env.user.id)
    cuenta_desajuste = fields.Many2one("account.account", string="Cuenta de desajuste")
    no_liquidacion = fields.Integer(string="Orden Mix", store=True)

    # _sql_constraints = [
    #     ('no_liquidacion_unique', 'unique(no_liquidacion)', 'El número de liquidación debe ser único.')
    # ]
    _sql_constraints = [
        ('no_liquidacion_unique',
         'UNIQUE(no_liquidacion) WHERE no_liquidacion != 0',
         'El número de liquidación debe ser único, excepto si es cero.')
    ]
    @api.depends('no_liquidacion')
    def _compute_th_name(self):
        for rec in self:
            if rec.no_liquidacion:
                rec.name = "Liquidación "+ str(rec.no_liquidacion)

    @api.onchange('no_liquidacion')
    def _onchange_no_liquidacion(self):
        if self.no_liquidacion:
            thBolson = self.env['bolson.bolson'].search([('no_liquidacion', '=', self.no_liquidacion)], limit=1)
            if thBolson:
                raise UserError('El número de liquidación ya existe')
            else:
                self.name = "Liquidación "+ str(self.no_liquidacion)
                for factura in self.facturas:
                    factura.no_liquidacion = self.no_liquidacion

    def conciliar(self):
        for rec in self:
            lineas = []

            total = 0
            for f in rec.facturas:
                if f.state == 'posted':
                    logging.warn(f.name)
                    logging.warn(f.amount_total)
                    for l in f.line_ids:
                        if l.account_id.reconcile:
                            if not l.reconciled:
                                total += (l.credit - l.debit)
                                lineas.append(l)
                                logging.warn(l.credit - l.debit)
                            else:
                                aux = 1
                                aaa = c.name
                                raise UserError('La factura %s ya esta conciliada' % (f.name))

            for c in rec.cheques:
                if c.state == 'posted':
                    logging.warn(c.name)
                    logging.warn(c.amount)
                    for l in c.line_ids:
                        if l.account_id.reconcile and l.account_id.account_type not in ['asset_cash']:
                            #if not l.reconciled and not l.reconciled_invoice_ids and not l.reconciled_bill_ids:
                            if not c.reconciled_invoice_ids and not c.reconciled_bill_ids:
                                total -= (l.debit - l.credit)
                                lineas.append(l)
                                logging.warn(l.debit - l.credit)
                            else:
                                aux = 1
                                aaa = c.name
                                raise UserError('El cheque %s ya esta conciliado' % (c.name))

            if round(total) != 0 and not rec.cuenta_desajuste:
                raise UserError('El total de las facturas no es igual al total de los cheques y los extractos')

            pares = []
            nuevas_lineas = []
            for linea in lineas:
                nuevas_lineas.append((0, 0, {
                    'name': linea.name,
                    'debit': linea.credit,
                    'credit': linea.debit,
                    'account_id': linea.account_id.id,
                    'partner_id': linea.partner_id.id,
                    'journal_id': rec.diario.id,
                    'date_maturity': rec.fecha,
                }))

            if total != 0:
                nuevas_lineas.append((0, 0, {
                    'name': 'Diferencial en ' + rec.name,
                    'debit': -1 * total if total < 0 else 0,
                    'credit': total if total > 0 else 0,
                    'account_id': rec.cuenta_desajuste.id,
                    'date_maturity': rec.fecha,
                }))

            move = self.env['account.move'].create({
                'line_ids': nuevas_lineas,
                'ref': rec.name,
                'date': rec.fecha,
                'journal_id': rec.diario.id,
            })
            #publicar asiento
            move.action_post()
            indice = 0
            invertidas = move.line_ids[::+1]
            for linea in lineas:
                par = linea | invertidas[indice]
                par.reconcile()
                indice += 1


            self.write({'asiento': move.id})

        return True

    def cancelar(self):
        for rec in self:
            for l in rec.asiento.line_ids:
                if l.reconciled:
                    l.remove_move_reconcile()
            rec.asiento.button_cancel()
            rec.asiento.unlink()

        return True

    @api.model_create_multi
    def create(self, vals_list):
        res = super(BolsonBolson, self).create(vals_list)
        if 'no_liquidacion' in vals_list:
            if vals_list['no_liquidacion']:
                thFacturas = self.env['account.move'].search([('no_liquidacion', '=', vals_list['no_liquidacion'])])
                if thFacturas:
                    self.facturas = thFacturas.ids

        return res

    def write(self, vals):
        if 'no_liquidacion' in vals:
            if vals['no_liquidacion']:
                thFacturas = self.env['account.move'].search([('no_liquidacion', '=', vals['no_liquidacion'])])
                if thFacturas:
                    self.facturas = thFacturas.ids
        res = super(BolsonBolson, self).write(vals)
        return res

    # def agregar_factura(self):
    #     return {
    #         'name': _('Agregar Facturas'),
    #         'type': 'ir.actions.act_window',
    #         'res_model': 'factura.selection.wizard',
    #         'view_mode': 'form',
    #         'target': 'new',
    #         'context': {'active_id': self.id},
    #     }
    #
    # def agregar_pago(self):
    #     return {
    #         'name': _('Agregar Cheques'),
    #         'type': 'ir.actions.act_window',
    #         'res_model': 'pago.selection.wizard',
    #         'view_mode': 'form',
    #         'target': 'new',
    #         'context': {'active_id': self.id},
    #     }