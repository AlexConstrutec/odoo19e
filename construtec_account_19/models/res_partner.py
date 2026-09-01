from odoo import models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def write(self, vals):
        res = super().write(vals)
        if vals.get('materiales_catalogo_visible'):
            # Curar un proveedor (marcarlo como True) debe alimentar de inmediato el Catálogo de
            # Materiales con TODO lo que ya existía de él en construtec.sat.product.catalog, no
            # solo con facturas nuevas a partir de ahora - si no, el usuario tendría que esperar a
            # que llegue una factura nueva de ese proveedor para ver algo aparecer.
            entradas = self.env['construtec.sat.product.catalog'].search([
                ('partner_id', 'in', self.ids),
            ])
            for entrada in entradas:
                entrada._sat_sync_to_community()
        return res
