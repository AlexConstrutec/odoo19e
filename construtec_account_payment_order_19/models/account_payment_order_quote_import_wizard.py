import base64
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..tools.quote_extraction_api import (
    QuoteExtractionError, extract_quote_from_image, extract_quote_from_pdf, extract_quote_from_text,
)

_logger = logging.getLogger(__name__)

_IMAGE_MIME_BY_EXT = {
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.webp': 'image/webp',
}


def _extraer_texto_docx(docx_bytes):
    """Extrae texto de un .docx - párrafos Y tablas (una cotización casi siempre viene en
    tabla: material/cantidad/precio), concatenados en un solo texto para pasarlo a la IA como
    texto plano. Import perezoso (mismo patrón que pdfminer.six en
    construtec_account_19/models/sat_retention_import.py) - así este módulo sigue cargando en
    cualquier entorno que todavía no tenga python-docx instalado; solo revienta si alguien
    realmente sube un .docx sin la librería presente."""
    import io
    from docx import Document

    doc = Document(io.BytesIO(docx_bytes))
    partes = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            celdas = [c.text.strip() for c in row.cells]
            if any(celdas):
                partes.append(' | '.join(celdas))
    return '\n'.join(partes)


class AccountPaymentOrderQuoteImportWizard(models.TransientModel):
    _name = 'account.payment.order.quote.import.wizard'
    _description = 'Cargar Cotización de Proveedor con IA'

    order_id = fields.Many2one(
        'account.payment.order', string='Orden de Pago', required=True,
        default=lambda self: self.env.context.get('default_order_id'))
    state = fields.Selection([
        ('upload', 'Cargar Archivo'),
        ('review', 'Revisar Datos'),
    ], default='upload', required=True)
    quote_file = fields.Binary(string='Archivo de Cotización')
    quote_filename = fields.Char(string='Nombre de Archivo')
    proveedor_extraido = fields.Char(string='Proveedor Sugerido (IA)', readonly=True)
    fecha_extraida = fields.Date(
        string='Fecha de la Cotización (IA)', readonly=True,
        help='Solo informativa - no reemplaza la Fecha de la Orden (que ya tiene su propio '
             'valor por defecto). Cópiala a mano en el encabezado si aplica.')
    line_ids = fields.One2many(
        'account.payment.order.quote.import.wizard.line', 'wizard_id', string='Líneas Extraídas')

    def action_extraer(self):
        """Envía el archivo a la IA y pasa a la pantalla de revisión. Deliberadamente todo en
        una sola transacción (decisión explícita del usuario) - si la extracción falla, no se
        guarda ni el adjunto ni ninguna línea; el jefe de técnicos simplemente vuelve a subir el
        mismo archivo, que ya tiene en su computadora/teléfono."""
        self.ensure_one()
        if not self.quote_file:
            raise UserError(self.env._('Selecciona un archivo primero.'))
        api_key = self.order_id.company_id.anthropic_api_key
        if not api_key:
            raise UserError(self.env._(
                'No se configuró la Anthropic API Key. Ajustes > Facturación > '
                '"IA para Cotizaciones (Anthropic)".'))

        filename = (self.quote_filename or '').lower()
        file_bytes = base64.b64decode(self.quote_file)

        try:
            if filename.endswith('.pdf'):
                result = extract_quote_from_pdf(api_key, file_bytes)
            elif filename.endswith('.docx'):
                texto = _extraer_texto_docx(file_bytes)
                result = extract_quote_from_text(api_key, texto)
            else:
                ext = next((e for e in _IMAGE_MIME_BY_EXT if filename.endswith(e)), None)
                if not ext:
                    raise UserError(self.env._(
                        'Formato no soportado. Use PDF, imagen (PNG/JPG/WEBP) o Word (.docx).'))
                result = extract_quote_from_image(api_key, file_bytes, _IMAGE_MIME_BY_EXT[ext])
        except QuoteExtractionError as exc:
            raise UserError(str(exc)) from exc
        except ImportError as exc:
            raise UserError(self.env._(
                'Falta instalar la librería python-docx en el servidor: %(error)s',
                error=str(exc))) from exc

        self.order_id.message_post(body=self.env._(
            'Cotización procesada por IA (%(filename)s): %(count)s línea(s) detectada(s), '
            'proveedor sugerido: %(proveedor)s, fecha: %(fecha)s.',
            filename=self.quote_filename, count=len(result['lineas']),
            proveedor=result['proveedor'] or '(no detectado)',
            fecha=result['fecha'] or '(no detectada)'))
        self.env['ir.attachment'].create({
            'name': self.quote_filename,
            'datas': self.quote_file,
            'res_model': 'account.payment.order',
            'res_id': self.order_id.id,
        })
        self.proveedor_extraido = result['proveedor']
        self.fecha_extraida = result['fecha']
        self.line_ids = [(5, 0, 0)] + [
            (0, 0, {
                'description': linea['descripcion'],
                'qty': linea['cantidad'] or 1,
                'uom_name': linea['unidad'],
                'estimated_price': linea['precio_unitario'],
            })
            for linea in result['lineas']
        ]
        self.state = 'review'
        return self._reload_action()

    def action_volver(self):
        self.ensure_one()
        self.line_ids = [(5, 0, 0)]
        self.proveedor_extraido = False
        self.fecha_extraida = False
        self.state = 'upload'
        return self._reload_action()

    def action_aplicar(self):
        self.ensure_one()
        if self.order_id.state != 'borrador':
            raise UserError(self.env._(
                'La Orden ya no está en Borrador - no se pueden agregar líneas.'))
        seleccionadas = self.line_ids.filtered(lambda line: line.incluir and line.description)
        if not seleccionadas:
            raise UserError(self.env._('Selecciona al menos una línea para aplicar.'))

        Line = self.env['account.payment.order.material.line']
        for line in seleccionadas:
            Line.create({
                'order_id': self.order_id.id,
                'description': line.description,
                'qty': line.qty,
                'uom_name': line.uom_name,
                'estimated_price': line.estimated_price,
                'vendor_name': self.proveedor_extraido or False,
            })
        if self.proveedor_extraido and not self.order_id.proveedor_materiales_name:
            self.order_id.proveedor_materiales_name = self.proveedor_extraido

        self.order_id.message_post(body=self.env._(
            '%(count)s línea(s) de materiales aplicada(s) desde una cotización cargada con IA.',
            count=len(seleccionadas)))
        return {'type': 'ir.actions.act_window_close'}

    def _reload_action(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }


class AccountPaymentOrderQuoteImportWizardLine(models.TransientModel):
    _name = 'account.payment.order.quote.import.wizard.line'
    _description = 'Línea Extraída de una Cotización (revisión antes de aplicar)'

    wizard_id = fields.Many2one(
        'account.payment.order.quote.import.wizard', required=True, ondelete='cascade')
    incluir = fields.Boolean(string='Incluir', default=True)
    description = fields.Char(string='Descripción')
    qty = fields.Float(string='Cantidad', default=1)
    uom_name = fields.Char(string='Unidad de Medida')
    estimated_price = fields.Float(string='Precio Estimado')
    subtotal = fields.Float(string='Subtotal', compute='_compute_subtotal')

    @api.depends('qty', 'estimated_price')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.qty * line.estimated_price
