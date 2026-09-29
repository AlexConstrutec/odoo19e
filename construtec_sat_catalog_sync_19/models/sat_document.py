# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import fields, models

# Mismas listas que construtec_account_19/models/sat_document.py (Enterprise) - duplicadas a
# propósito (ese módulo no existe en Community, no se puede importar su código Python) - mismo
# criterio ya aceptado en este proyecto para catálogos chicos compartidos entre ediciones (ver
# PUEBLO_PERTENENCIA/COMUNIDAD_LINGUISTICA en construtec_account_payment_order_19). Si Enterprise
# agrega un tipo nuevo, hay que reflejarlo aquí también.
TIPO_DTE_SELECTION = [
    ('FACT', 'FACT: Factura'),
    ('FCAM', 'FCAM: Factura Cambiaria'),
    ('FESP', 'FESP: Factura Especial'),
    ('FPEQ', 'FPEQ: Factura Pequeño Contribuyente'),
    ('FCAP', 'FCAP: Factura Cambiaria Pequeño Contribuyente'),
    ('NABN', 'NABN: Nota de Abono'),
    ('NCRE', 'NCRE: Nota de Crédito'),
    ('NDEB', 'NDEB: Nota de Débito'),
    ('RECI', 'RECI: Recibo'),
    ('CIVA', 'CIVA: Constancia de IVA'),
    ('FAPE', 'FAPE: Factura de Pequeño Contribuyente Especial'),
    ('FEXP', 'FEXP: Factura Electrónica de Exportación'),
    ('RDON', 'RDON: Recibo por Donación'),
    ('RSP', 'RSP: Recibo por Servicios Profesionales'),
    ('NENV', 'NENV: Nota de Envío'),
    ('RECC', 'RECC: Recibo de Caja Chica'),
    ('REPA', 'REPA: Recibo de Pago'),
    ('CRET', 'CRET: Comprobante de Retención'),
]

TIPO_COMPRA_SELECTION = [('local', 'Compra Local'), ('importacion', 'Importación')]


class ConstructecSatDocumentMirror(models.Model):
    """Réplica de solo lectura de `construtec.sat.document` (Enterprise, `construtec_account_19`)
    - mismo `_name`, mismos campos (salvo los que no tienen sentido cruzando bases: adjuntos,
    cuentas contables/analíticas, líneas de detalle, y cualquier id de `account.move`/
    `purchase.order`/`sale.order` - nunca un id de esos cruza a Community, decisión explícita del
    usuario). Pedido explícito del usuario (2026-09-29): "el modelo Documento SAT de Enterprise,
    replícalo tal cual en Community... que se llame igual, que tenga los mismos campos".

    Poblado por `res.company._sync_sat_documents_from_enterprise()` - trae solo documentos
    `direction='recibida'` o `tipo_dte='FESP'` (documentos de compra, mismo criterio que
    `_sat_es_compra()` en Enterprise) que se hayan creado o modificado en los últimos N días
    (`materials_catalog_sync_interval_*`/parámetro `since_days`, no toda la historia en cada
    corrida) - upsert por `origin_id` (el id real en Enterprise), así que corridas sucesivas van
    completando el histórico sin duplicar nada, mientras cada corrida individual se queda rápida.

    Deliberadamente NO reemplaza a `construtec.sat.invoice.mirror` (el modelo ya usado por
    `construtec_account_payment_order_19` para el picker de Pago Directo) - este modelo es una
    referencia informativa más completa/fiel, no está conectado (todavía) a ningún flujo de
    Solicitud de Pago."""
    _name = 'construtec.sat.document'
    _description = (
        'Documento SAT de proveedor en Enterprise (construtec.sat.document, direction=recibida '
        'o tipo_dte=FESP) - copia de solo lectura en Community, misma estructura, poblada por '
        'res.company._sync_sat_documents_from_enterprise() sobre los documentos creados o '
        'modificados en los últimos días (ventana configurable, no todo el histórico cada vez).'
    )
    _order = 'fecha_certificacion desc'

    origin_id = fields.Integer(
        string='ID en Enterprise', required=True, index=True,
        help='El id real de este Documento SAT en Enterprise - clave de actualización (upsert).')
    direction = fields.Selection([
        ('recibida', 'Recibida'),
        ('emitida', 'Emitida'),
    ], string='Dirección', required=True)
    numero_autorizacion = fields.Char(string='No. Autorización SAT', required=True, index=True)
    tipo_dte = fields.Selection(TIPO_DTE_SELECTION, string='Tipo DTE', required=True)
    tipo_compra = fields.Selection(TIPO_COMPRA_SELECTION, string='Tipo de Compra')
    numero_autorizacion_referencia = fields.Char(string='No. Autorización Documento de Referencia')
    motivo_ajuste_nota = fields.Char(string='Motivo de Ajuste')
    serie = fields.Char(string='Serie')
    numero_documento = fields.Char(string='Número de Documento')
    fecha_certificacion = fields.Datetime(string='Fecha de Certificación', required=True)
    fecha_vencimiento = fields.Date(string='Fecha de Vencimiento')
    nit_emisor = fields.Char(string='NIT Emisor')
    nombre_emisor = fields.Char(string='Nombre Emisor')
    nit_receptor = fields.Char(string='NIT Receptor')
    nombre_receptor = fields.Char(string='Nombre Receptor')
    partner_name = fields.Char(
        string='Proveedor',
        help='Texto plano, no un res.partner real - mismo criterio que el resto de los mirrors '
             'de este módulo. Ya resuelto "por NIT" en Enterprise (partner_id), no confundir con '
             'nombre_emisor/nombre_receptor (los campos crudos del DTE).')
    nit_contacto = fields.Char(string='NIT del Contacto')
    currency_name = fields.Char(string='Moneda')
    moneda_codigo = fields.Char(string='Código Moneda DTE')
    monto_total = fields.Float(string='Monto Total')
    monto_iva = fields.Float(string='Monto IVA')
    monto_petroleo = fields.Float(string='Impuesto Petróleo')
    monto_turismo_hospedaje = fields.Float(string='Impuesto Turismo Hospedaje')
    monto_turismo_pasajes = fields.Float(string='Impuesto Turismo Pasajes')
    monto_timbre_prensa = fields.Float(string='Timbre de Prensa')
    monto_bomberos = fields.Float(string='Impuesto Bomberos')
    monto_tasa_municipal = fields.Float(string='Tasa Municipal')
    monto_bebidas_alcoholicas = fields.Float(string='Impuesto Bebidas Alcohólicas')
    monto_tabaco = fields.Float(string='Impuesto Tabaco')
    monto_cemento = fields.Float(string='Impuesto Cemento')
    monto_bebidas_no_alcoholicas = fields.Float(string='Impuesto Bebidas No Alcohólicas')
    monto_tarifa_portuaria = fields.Float(string='Tarifa Portuaria')
    monto_retencion_isr_fesp = fields.Float(string='Retención ISR (Factura Especial)')
    monto_retencion_iva_fesp = fields.Float(string='Retención IVA (Factura Especial)')
    monto_neto_pagado_fesp = fields.Float(string='Neto Pagado al Vendedor (Factura Especial)')
    codigo_establecimiento = fields.Char(string='Código Establecimiento')
    nombre_establecimiento = fields.Char(string='Nombre Establecimiento')
    nombre_comercial_emisor = fields.Char(string='Nombre Comercial Emisor')
    direccion_emisor = fields.Char(string='Dirección Emisor')
    nit_certificador = fields.Char(string='NIT Certificador')
    nombre_certificador = fields.Char(string='Nombre Certificador')
    clasificacion_emisor = fields.Char(string='Clasificación Emisor')
    exportacion = fields.Char(string='Exportación')
    estado_sat = fields.Char(string='Estado en SAT')
    anulado = fields.Boolean(string='Anulado')
    fecha_anulacion = fields.Datetime(string='Fecha de Anulación')
    state = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('convertido_factura', 'Convertido a Factura'),
        ('convertido_orden_compra', 'Convertido a Orden de Compra'),
        ('convertido_pedido_venta', 'Convertido a Pedido de Venta'),
    ], string='Estado')
    move_amount_residual = fields.Float(
        string='Saldo Pendiente de la Factura',
        help='Para un documento convertido_factura, el saldo pendiente real en Enterprise '
             '(account.move.amount_residual, vía el campo related ya existente en '
             'construtec.sat.document allá). Para uno todavía Pendiente, es simplemente '
             'monto_total (nada se ha pagado, no existe ninguna factura real todavía).')
    move_payment_state = fields.Selection([
        ('not_paid', 'No Pagada'),
        ('in_payment', 'En Proceso de Pago'),
        ('paid', 'Pagada'),
        ('partial', 'Pagada Parcialmente'),
        ('reversed', 'Revertida'),
        ('invoicing_legacy', 'Facturación Heredada'),
    ], string='Estado de Pago de la Factura')
    enterprise_write_date = fields.Datetime(
        string='Última Modificación en Enterprise',
        help='write_date real del documento en Enterprise al momento de esta sincronización - '
             'informativo, y también lo que decide si un documento entra en la ventana de los '
             'últimos N días la próxima vez que se sincronice.')
    company_id = fields.Many2one(
        'res.company', string='Compañía',
        help='En Enterprise, la compañía real del documento. En Community cae en la compañía '
             'activa de quien sincroniza si Enterprise no la manda.')
    received_date = fields.Datetime(
        string='Última Recepción', default=fields.Datetime.now, readonly=True)

    _origin_id_uniq = models.Constraint(
        'unique(origin_id)',
        'Ya existe un Documento SAT importado con ese id de origen en Enterprise.',
    )
