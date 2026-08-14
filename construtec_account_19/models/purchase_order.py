from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    sat_document_id = fields.Many2one(
        'construtec.sat.document', string='Documento SAT', readonly=True, copy=False,
        help='Documento SAT (DTE) desde el que se generó esta Orden de Compra, si vino '
             'importado vía la bandeja de documentos SAT en vez de crearse manualmente.')

    def action_view_sat_document(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'construtec.sat.document',
            'view_mode': 'form',
            'res_id': self.sat_document_id.id,
            'target': 'current',
        }

    def unlink(self):
        documentos_sat = self.sat_document_id
        res = super().unlink()
        documentos_sat._sat_revertir_a_pendiente()
        return res
