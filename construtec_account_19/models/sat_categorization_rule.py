from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .sat_document_import import _strip_accents_upper

# Campos de impuestos específicos del encabezado (ver sat_document.py) que una
# regla puede usar como condición adicional, además de las palabras clave -
# pensado sobre todo para combustibles: "si la descripción dice 'diesel' Y el
# documento trae monto_petroleo != 0" evita que una línea que solo MENCIONA la
# palabra "diesel" en otro contexto (ej. un genset alquilado) dispare la regla
# por accidente. Ninguno es obligatorio - una regla puede ser solo palabras
# clave, sin condición de monto.
_CAMPOS_CONDICION = [
    ('monto_petroleo', 'Impuesto Petróleo (IDP)'),
    ('monto_turismo_hospedaje', 'Impuesto Turismo Hospedaje'),
    ('monto_turismo_pasajes', 'Impuesto Turismo Pasajes'),
    ('monto_timbre_prensa', 'Timbre de Prensa'),
    ('monto_bomberos', 'Impuesto Bomberos'),
    ('monto_tasa_municipal', 'Tasa Municipal'),
    ('monto_bebidas_alcoholicas', 'Impuesto Bebidas Alcohólicas'),
    ('monto_tabaco', 'Impuesto Tabaco'),
    ('monto_cemento', 'Impuesto Cemento'),
    ('monto_bebidas_no_alcoholicas', 'Impuesto Bebidas No Alcohólicas'),
    ('monto_tarifa_portuaria', 'Tarifa Portuaria'),
]


class ConstructecSatCategorizationRule(models.Model):
    _name = 'construtec.sat.categorization.rule'
    _description = 'Regla de Categorización de Documentos SAT (cuenta/impuestos sugeridos por palabra clave)'
    _order = 'sequence, id'

    name = fields.Char(string='Nombre', required=True, help='Solo descriptivo, ej. "Combustible Diésel".')
    sequence = fields.Integer(
        string='Secuencia', default=10,
        help='Si varias reglas coinciden con la misma línea, gana la de menor secuencia.')
    active = fields.Boolean(string='Activa', default=True)
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True, default=lambda self: self.env.company.id)
    direction = fields.Selection([
        ('recibida', 'Recibida'),
        ('emitida', 'Emitida'),
    ], string='Dirección', help='Vacío = aplica a ambas direcciones.')
    partner_ids = fields.Many2many(
        'res.partner', string='Contactos',
        help='Vacío = aplica a cualquier contacto. Si se especifican, la regla solo aplica cuando '
             'el documento es de uno de estos - útil para acotar una regla a los proveedores de '
             'los que de verdad se esperan ese tipo de facturas (ej. solo las gasolineras conocidas '
             'para una regla de combustible), en vez de que cualquier "diesel" mencionado en una '
             'descripción la dispare.')
    palabras_clave = fields.Char(
        string='Palabras Clave', required=True,
        help='Separadas por coma. La regla aplica si la descripción de la línea contiene AL MENOS '
             'UNA de estas palabras (sin distinguir mayúsculas/minúsculas ni acentos). Ej.: '
             '"diesel, gasoil" o "cemento, block, varilla".')
    campo_condicion = fields.Selection(
        _CAMPOS_CONDICION, string='Condición Adicional (opcional)',
        help='Si se elige, la regla solo aplica cuando el documento trae este monto distinto de '
             'cero, ADEMÁS de la palabra clave - ej. exigir monto_petroleo != 0 para evitar que '
             '"diesel" dispare la regla fuera de una compra de combustible real.')
    account_id = fields.Many2one(
        'account.account', string='Cuenta Contable a Sugerir',
        help='Se asigna a la línea solo si todavía no tiene una cuenta contable propia.')
    tax_ids = fields.Many2many(
        'account.tax', string='Impuestos a Sugerir',
        help='Se asignan a la línea solo si todavía no tiene impuestos propios - ej. IDP + IVA '
             'juntos para una regla de combustible.')

    @api.constrains('account_id', 'tax_ids')
    def _check_account_or_tax(self):
        for rule in self:
            if not rule.account_id and not rule.tax_ids:
                raise ValidationError(self.env._(
                    'La regla "%s" no sugiere ninguna Cuenta Contable ni Impuesto - no serviría de nada.',
                    rule.name,
                ))

    @api.model
    def _sat_find_matching_rule(self, document, descripcion):
        """Primera regla (por secuencia) que coincide con esta línea - ver
        _sat_apply_to_line() para cómo se usa. `document` se necesita para el
        company_id/direction/partner_id y para poder evaluar campo_condicion (un
        campo del propio encabezado, no de la línea - la SAT reporta estos
        impuestos específicos a nivel de documento, no desglosados por línea)."""
        if not descripcion:
            return self.browse()
        descripcion_normalizada = _strip_accents_upper(descripcion)

        reglas = self.search([
            ('company_id', '=', document.company_id.id),
            ('direction', 'in', [document.direction, False]),
            '|', ('partner_ids', '=', False), ('partner_ids', 'in', document.partner_id.ids),
        ])
        for regla in reglas:
            palabras = [
                _strip_accents_upper(palabra.strip())
                for palabra in (regla.palabras_clave or '').split(',') if palabra.strip()
            ]
            if not any(palabra in descripcion_normalizada for palabra in palabras):
                continue
            if regla.campo_condicion and not document[regla.campo_condicion]:
                continue
            return regla
        return self.browse()

    @api.model
    def _sat_apply_to_line(self, document, line):
        """Aplica la primera regla que coincida a una línea recién creada -
        llamado desde create_from_dte() en sat_document.py, igual que el
        catálogo de productos (_sat_register_from_line). Nunca pisa un
        account_id/tax_ids que la línea ya traiga (no debería traer ninguno
        recién creada desde el DTE, pero por si acaso) - es una SUGERENCIA
        editable antes de convertir, no una asignación definitiva."""
        regla = self._sat_find_matching_rule(document, line.descripcion)
        if not regla:
            return
        vals = {}
        if regla.account_id and not line.account_id:
            vals['account_id'] = regla.account_id.id
        if regla.tax_ids and not line.tax_ids:
            vals['tax_ids'] = [(6, 0, regla.tax_ids.ids)]
        if vals:
            line.write(vals)
