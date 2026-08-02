from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    regimen_iva = fields.Selection([
        ('GEN', 'GEN: Régimen General de IVA'),
        ('EXE', 'EXE: Pequeño Contribuyente Exento'),
        ('PEQ', 'PEQ: Pequeño Contribuyente'),
        ('PEE', 'PEE: Pequeño Contribuyente Electrónico Especial'),
        ('AGR', 'AGR: Régimen Agropecuario'),
        ('AGE', 'AGE: Régimen Agroexportador'),
        ('ECA', 'ECA: Exportador de Café'),
        ('EXI', 'EXI: Exento de IVA'),
    ], string='Régimen de IVA', default='GEN',
        help="""Selecciona el régimen de IVA de la empresa ante la SAT (no implica ningún \
proveedor de facturación electrónica en particular; esa integración se agrega por separado):
GEN - Régimen General de IVA - Aplica a contribuyentes con actividades comerciales, industriales o de servicios. Deben declarar y pagar el IVA mensualmente, usando el método de débito y crédito fiscal.
EXE - Pequeño Contribuyente Exento - Aplica a entidades gubernamentales, asociaciones sin fines de lucro y actividades exentas según la ley. No generan ni pagan IVA, pero deben cumplir requisitos específicos ante la SAT.
PEQ - Pequeño Contribuyente - Para personas individuales o jurídicas con ingresos anuales hasta el límite establecido por la SAT. Pagan un porcentaje fijo sobre sus ventas brutas y presentan declaraciones trimestrales.
PEE - Pequeño Contribuyente Electrónico Especial - Similar al régimen de Pequeño Contribuyente, pero adaptado a operaciones electrónicas, permitiendo declaraciones y facturación digital.
AGR - Régimen Agropecuario - Diseñado para actividades agropecuarias con beneficios fiscales específicos, permitiendo créditos y declaraciones adaptadas a la producción agroindustrial.
AGE - Régimen Agroexportador - Igual al régimen agropecuario, pero para contribuyentes que operan electrónicamente, facilitando los procesos de declaración y control fiscal.
ECA - Exportador de Café - Para empresas exportadoras. Permite solicitar devoluciones de crédito fiscal por exportaciones y gozar de ciertos beneficios fiscales.
EXI - Exento de IVA - Aplica a sectores o actividades exentas de impuestos según legislación especial, como servicios diplomáticos y ciertas exportaciones de bienes o servicios específicos.
""")
    nombre_legal = fields.Char(
        string='Nombre Legal',
        help='Razón social tal como está registrada ante la SAT, para usarse en reportes '
             'y (más adelante) en la facturación electrónica.')
    codigo_establecimiento = fields.Char(
        string='Código de Establecimiento',
        help='Código de establecimiento asignado por la SAT.')
