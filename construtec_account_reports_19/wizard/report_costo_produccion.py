from odoo import models


class WizardCostoProduccion(models.TransientModel):
    _name = 'wizard.costo.produccion'
    _description = 'Wizard Costo de Producción'
    _inherit = ['construtec.financial.report.wizard.mixin', 'construtec.costo.reporte.mixin']

    def _group_name_filter(self):
        return 'producc'

    def print_xls_costo_produccion(self):
        return self._print_costo('Costo de Producción', 'Costo_de_Produccion.xlsx')
