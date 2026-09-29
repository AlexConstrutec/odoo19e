# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import fields, models


class ConstructecSatInvoiceMirror(models.Model):
    _name = 'construtec.sat.invoice.mirror'
    _description = (
        'Facturas de proveedor (account.move, move_type in in_invoice/in_refund, state=posted) '
        'ya contabilizadas en Enterprise - copia de solo lectura para que un jefe de técnicos en '
        'Community pueda vincular una Orden de Pago tipo Pago Directo a una factura REAL, en vez '
        'de capturar proveedor/monto a mano. Mismo patrón que construtec.materials.catalog.mirror '
        '(este mismo módulo): mismo `_name` en Enterprise y Community, poblado en Community por '
        'un pull propio (res_company.py::_sync_vendor_invoices_from_enterprise(), mismo toggle/'
        'cron/botón ya usado para el Catálogo de Materiales). `origin_id` es el id REAL del '
        'account.move en Enterprise - la clave que account.payment.order usa para resolver el '
        'vínculo real (payment_order_id) del lado Enterprise al recibir una Orden sincronizada, '
        'ver construtec_account_payment_order_19.'
    )
    _order = 'fecha desc'

    origin_id = fields.Integer(
        string='ID en Enterprise', required=True, index=True,
        help='El id real del account.move en Enterprise - clave de actualización (upsert) y, '
             'más importante, la clave que Enterprise usa para resolver el vínculo real al '
             'recibir una Orden de Pago sincronizada desde Community.')
    numero_autorizacion = fields.Char(
        string='No. Autorización SAT',
        help='De construtec.sat.document.numero_autorizacion (Enterprise), vía '
             'account.move.sat_document_id - solo informativo aquí, nunca se usa como clave.')
    partner_name = fields.Char(
        string='Proveedor',
        help='Texto plano, no un res.partner real - mismo criterio que el resto de los mirrors '
             'de este módulo (un id de contacto de Enterprise no significa nada en Community).')
    partner_vat = fields.Char(string='NIT del Proveedor')
    fecha = fields.Date(string='Fecha de la Factura')
    currency_name = fields.Char(string='Moneda')
    monto_total = fields.Float(string='Monto Total')
    amount_residual = fields.Float(
        string='Saldo Pendiente',
        help='account.move.amount_residual en Enterprise al momento de la última sincronización '
             '- mecanismo nativo de Odoo, sin ningún cálculo propio. Es solo la última foto '
             'conocida, nunca la autoridad final (esa vive en Enterprise, en el account.move '
             'real) - ver _check_factura_disponible() en construtec_account_payment_order_19.')
    payment_state = fields.Selection([
        ('not_paid', 'No Pagada'),
        ('in_payment', 'En Proceso de Pago'),
        ('paid', 'Pagada'),
        ('partial', 'Pagada Parcialmente'),
        ('reversed', 'Revertida'),
        ('invoicing_legacy', 'Facturación Heredada'),
    ], string='Estado de Pago')
    linked_order_name = fields.Char(
        string='Vinculada a la Orden',
        help='El `name` (nunca un id) de la account.payment.order que YA tiene esta factura '
             'vinculada en Enterprise, si alguna - permite avisar en Community "ya está '
             'vinculada a OP/0005" sin cruzar ids entre bases. Vacío si ninguna Orden la tiene '
             'tomada todavía.')
    company_id = fields.Many2one(
        'res.company', string='Compañía',
        help='En Enterprise, la compañía real de la factura. En Community cae en la compañía '
             'activa de quien sincroniza si Enterprise no la manda - mismo criterio que el resto '
             'de los mirrors de este módulo.')
    received_date = fields.Datetime(
        string='Última Recepción', default=fields.Datetime.now, readonly=True)

    _origin_id_uniq = models.Constraint(
        'unique(origin_id)',
        'Ya existe una entrada de factura para ese id de origen en Enterprise.',
    )
