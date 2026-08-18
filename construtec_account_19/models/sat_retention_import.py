import io
import logging
import re

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


def _fix_pdf_accents(text):
    """El PDF de la Constancia (formulario SAT-2229) sufre una corrupción de
    codificación DISTINTA a la del '?' literal en los XML del DTE (ver
    _fix_mangled_accents en sat_document_import.py): pdfminer.six extrae cada
    vocal acentuada/ñ del PDF como el carácter de reemplazo Unicode U+FFFD
    ('�'), de forma consistente incluso en las etiquetas fijas del formulario
    ("RETENCIÓN" -> "RETENCI�N"). Se reutiliza el mismo diccionario de
    _fix_mangled_accents reemplazando U+FFFD por '?' antes de llamarlo, en vez
    de duplicar la lista de palabras conocidas en dos lugares."""
    from .sat_document_import import _fix_mangled_accents
    if not text:
        return text
    return _fix_mangled_accents(text.replace('�', '?'))


_ROW_PATTERN = re.compile(r'([A-Za-zÀ-ÿ\s]+?)\s+(\d+)%\s+Q([\d,]+\.\d{2})\s+Q([\d,]+\.\d{2})')


def _parse_constancia_pdf(pdf_bytes):
    """Parsea el formulario SAT-2229 (Constancia de Retención de IVA) descargado de
    Agencia Virtual - Servicios Tributarios > Constancias de Retenciones y
    Exenciones > Constancias de Retención del IVA e ISR Recibidas.

    Se probó PyPDF2 primero y se descartó: además de la misma corrupción de
    acentos, el orden de lectura de celdas de tabla no es confiable (fecha y
    Serie quedaban concatenados sin separador). pdfminer.six separa cada valor
    en su propia línea, lo que sí permite anclar por texto de etiqueta con
    regex de forma confiable.

    Solo verificado contra una constancia real de 1 factura (cantidad_facturas
    == 1, 1 sola fila en DETALLE DE CONSTANCIA) - ver el bloque de abajo para
    el manejo (best-effort, marcando requiere_revision_manual) del caso de más
    de una factura, todavía sin un PDF real contra el cual confirmar el
    layout exacto de esa tabla.
    """
    from pdfminer.high_level import extract_text

    texto = extract_text(io.BytesIO(pdf_bytes))
    lines = [line.strip() for line in texto.splitlines() if line.strip()]
    full_text = ' '.join(lines)

    vals = {}

    m = re.search(r'Constancia\s+(\d+)\s+EL SUSCRITO', full_text)
    vals['numero_constancia'] = m.group(1) if m else None

    m = re.search(r'contribuyente\s+(\d{5,12})\s+(.+?)\s+Fecha de emisi', full_text)
    if m:
        vals['nit_contribuyente'] = m.group(1)
        vals['nombre_contribuyente'] = _fix_pdf_accents(m.group(2))

    m = re.search(r'D.a\s+(\d{1,2})\s+Mes\s+(\d{1,2})\s+A.o\s+(\d{4})', full_text)
    if m:
        dia, mes, anio = m.groups()
        vals['fecha_emision'] = f'{anio}-{int(mes):02d}-{int(dia):02d}'

    facturas = []
    m = re.search(
        r'Serie\s+N.mero de Factura\s+(\d+)\s+((?:[0-9A-Fa-f]{4,12}\s+\d{4,15}\s*)+)DETALLE DE CONSTANCIA',
        full_text)
    if m:
        vals['cantidad_facturas'] = int(m.group(1))
        pares = re.findall(r'([0-9A-Fa-f]{4,12})\s+(\d{4,15})', m.group(2))
        facturas = [{'serie': serie, 'numero_factura': numero} for serie, numero in pares]

    detalle_rows = []
    m = re.search(
        r'CONCEPTO\s+TARIFA\s+IMPORTE NETO DEL BIEN\s+RETENCI.N\s+(.*?)\s*TOTAL\s+Q([\d,]+\.\d{2})',
        full_text)
    if m:
        vals['monto_retencion_pdf'] = float(m.group(2).replace(',', ''))
        detalle_rows = [
            {
                'concepto': _fix_pdf_accents(concepto.strip()),
                'tarifa': float(tarifa),
                'monto_importe_neto': float(importe.replace(',', '')),
                'monto_retencion': float(retencion.replace(',', '')),
            }
            for concepto, tarifa, importe, retencion in _ROW_PATTERN.findall(m.group(1))
        ]

    # Solo se conoce con certeza el layout de 1 factura / 1 fila DETALLE (el
    # único PDF real disponible al escribir esto). Si cantidad_facturas > 1 y
    # el número de pares Serie/Número coincide con el número de filas
    # DETALLE, se asume que van emparejados en el mismo orden de lectura -
    # todavía sin confirmar contra un PDF real multi-factura. Si NO coinciden
    # (ej. una sola fila agregada para varias facturas), no se adivina cómo
    # repartir los montos entre facturas (mismo criterio de "no adivinar" que
    # _fix_mangled_accents) - se listan las facturas sin monto y se marca
    # requiere_revision_manual para que se complete a mano.
    if facturas and len(facturas) == len(detalle_rows):
        vals['lines'] = [{**factura, **detalle} for factura, detalle in zip(facturas, detalle_rows)]
        vals['requiere_revision_manual'] = False
    else:
        vals['lines'] = facturas or [dict(fila) for fila in detalle_rows]
        vals['requiere_revision_manual'] = len(facturas) != len(detalle_rows)
        if vals['requiere_revision_manual']:
            _logger.warning(
                'Constancia %s: %s factura(s) declaradas pero %s fila(s) de detalle - no se pudo '
                'emparejar automáticamente, revisar montos por línea manualmente.',
                vals.get('numero_constancia'), len(facturas), len(detalle_rows),
            )

    m = re.search(
        r'\bNIT\b\s+(\d{5,12})\s+Contribuyente\s+(.+?)\s+IDENTIFICACI.N DEL AGENTE RETENEDOR', full_text)
    if m:
        vals['nit_agente_retenedor'] = m.group(1)
        vals['nombre_agente_retenedor'] = _fix_pdf_accents(m.group(2))

    m = re.search(
        r'IDENTIFICACI.N DEL AGENTE RETENEDOR\s+Tipo agente\s+de retenci.n\s+(.+?)\s+Los documentos de soporte',
        full_text)
    vals['tipo_agente_retencion'] = _fix_pdf_accents(m.group(1)) if m else None

    return vals


class ConstructecSatRetentionImportWizard(models.TransientModel):
    _name = 'construtec.sat.retention.import.wizard'
    _description = 'Importar Constancia de Retención de IVA desde PDF'

    pdf_file = fields.Binary(string='PDF de la Constancia', required=True)
    pdf_filename = fields.Char(string='Nombre de Archivo')

    def action_importar(self):
        self.ensure_one()
        if not self.pdf_file:
            raise UserError(self.env._('Selecciona un archivo PDF primero.'))

        result = self.env['construtec.sat.retention'].create_from_pdf(
            self.pdf_file, self.pdf_filename)

        if result['state'] == 'skipped_duplicate':
            message = self.env._('Esta constancia ya había sido importada.')
        else:
            message = self.env._('Constancia importada correctamente.')

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._('Importar Constancia'),
                'message': message,
                'type': 'success' if result['state'] == 'success' else 'warning',
                'next': {
                    'type': 'ir.actions.act_window',
                    'res_model': 'construtec.sat.retention',
                    'res_id': result['retention_id'],
                    'view_mode': 'form',
                    'target': 'current',
                },
            },
        }
