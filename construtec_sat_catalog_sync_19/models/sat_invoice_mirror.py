# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import fields, models


class ConstructecSatInvoiceMirror(models.Model):
    _name = 'construtec.sat.invoice.mirror'
    _description = (
        'Documentos SAT de proveedor (construtec.sat.document, direction=recibida o '
        'tipo_dte=FESP) en Enterprise, pendientes o ya convertidos a factura real - copia de '
        'solo lectura para que un jefe de técnicos en Community pueda vincular una Orden de '
        'Pago tipo Pago Directo a un Documento SAT real, en vez de capturar proveedor/monto a '
        'mano. Mismo patrón que construtec.materials.catalog.mirror (este mismo módulo): mismo '
        '`_name` en Enterprise y Community, poblado en Community por un pull propio '
        '(res_company.py::_sync_vendor_invoices_from_enterprise(), mismo toggle/cron/botón ya '
        'usado para el Catálogo de Materiales).\n\n'
        '`origin_id` es el id REAL del construtec.sat.document en Enterprise (nunca del '
        'account.move, que puede no existir todavía si el documento sigue Pendiente) - es la '
        'clave universal que existe sin importar el estado. `move_origin_id` es el id del '
        'account.move REAL, solo presente si `state=convertido_factura`. Un jefe de técnicos '
        'puede pedir el pago de un documento todavía Pendiente - el Contador lo convierte a '
        'factura real al Aprobar la Solicitud (ver account_payment_order_sat_document.py, '
        'Enterprise) - ver construtec_account_payment_order_19 para el consumidor de ambos ids.'
    )
    _order = 'fecha desc'

    origin_id = fields.Integer(
        string='ID del Documento SAT en Enterprise', required=True, index=True,
        help='El id real de construtec.sat.document en Enterprise - clave de actualización '
             '(upsert) y, más importante, la clave que Enterprise usa para reclamar el '
             'documento (aún pendiente) o resolver el vínculo real (convertido_factura) al '
             'recibir una Orden de Pago sincronizada desde Community.')
    move_origin_id = fields.Integer(
        string='ID de la Factura (Enterprise)',
        help='El id real del account.move en Enterprise, solo si este documento ya se convirtió '
             'a factura (state=convertido_factura). Vacío mientras sigue Pendiente - no hay '
             'ningún account.move todavía.')
    state = fields.Selection([
        ('pendiente', 'Pendiente (aún no es factura)'),
        ('convertido_factura', 'Convertido a Factura'),
    ], string='Estado del Documento SAT', required=True, default='pendiente')
    numero_autorizacion = fields.Char(
        string='No. Autorización SAT',
        help='De construtec.sat.document.numero_autorizacion (Enterprise) - solo informativo '
             'aquí, nunca se usa como clave.')
    partner_name = fields.Char(
        string='Proveedor',
        help='Texto plano, no un res.partner real - mismo criterio que el resto de los mirrors '
             'de este módulo (un id de contacto de Enterprise no significa nada en Community).')
    partner_vat = fields.Char(string='NIT del Proveedor')
    fecha = fields.Date(string='Fecha del Documento')
    currency_name = fields.Char(string='Moneda')
    monto_total = fields.Float(string='Monto Total')
    amount_residual = fields.Float(
        string='Saldo Pendiente',
        help='Para un documento convertido_factura, account.move.amount_residual en Enterprise '
             'al momento de la última sincronización - mecanismo nativo de Odoo, sin ningún '
             'cálculo propio (nunca la autoridad final, esa vive en Enterprise). Para un '
             'documento todavía Pendiente, es simplemente `monto_total` (nada se ha pagado '
             'porque todavía no existe ninguna factura real) - ver '
             '_check_factura_mirror_disponible() en construtec_account_payment_order_19.')
    payment_state = fields.Selection([
        ('not_paid', 'No Pagada'),
        ('in_payment', 'En Proceso de Pago'),
        ('paid', 'Pagada'),
        ('partial', 'Pagada Parcialmente'),
        ('reversed', 'Revertida'),
        ('invoicing_legacy', 'Facturación Heredada'),
    ], string='Estado de Pago',
        help='Para un documento Pendiente, siempre `not_paid` (informativo - nada se ha pagado '
             'porque todavía no existe ninguna factura real).')
    linked_order_name = fields.Char(
        string='Vinculada a la Orden',
        help='El `name` (nunca un id) de la account.payment.order que YA tiene este documento '
             '(pendiente, vía construtec.sat.document.payment_order_id) o esta factura '
             '(convertida, vía account.move.payment_order_id) reclamada en Enterprise - permite '
             'avisar en Community "ya está vinculada a OP/0005" sin cruzar ids entre bases. '
             'Vacío si ninguna Orden la tiene tomada todavía.')
    company_id = fields.Many2one(
        'res.company', string='Compañía',
        help='En Enterprise, la compañía real del documento. En Community cae en la compañía '
             'activa de quien sincroniza si Enterprise no la manda - mismo criterio que el resto '
             'de los mirrors de este módulo.')
    received_date = fields.Datetime(
        string='Última Recepción', default=fields.Datetime.now, readonly=True)

    _origin_id_uniq = models.Constraint(
        'unique(origin_id)',
        'Ya existe una entrada de factura para ese id de origen en Enterprise.',
    )
