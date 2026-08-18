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


_ROW_PATTERN_RETENCIONES = re.compile(
    r'([0-9A-Fa-f]{6,12})\s+(\d{4,15})\s+(\d{1,2}/\d{1,2}/\d{4})\s+'
    r'(\d+)%\s+Q([\d,]+\.\d{2})\s+Q([\d,]+\.\d{2})\s+'
    r'(\d+)%\s+Q([\d,]+\.\d{2})\s+Q([\d,]+\.\d{2})\s+'
    r'(\d+)%\s+Q([\d,]+\.\d{2})\s+Q([\d,]+\.\d{2})'
)


def _parse_constancia_pdf(pdf_bytes):
    """Parsea el formulario SAT-2229 (Constancia de Retención de IVA) descargado de
    Agencia Virtual - Servicios Tributarios > Constancias de Retenciones y
    Exenciones > Constancias de Retención del IVA e ISR Recibidas.

    Se probó PyPDF2 primero y se descartó: además de la misma corrupción de
    acentos, el orden de lectura de celdas de tabla no es confiable (fecha y
    Serie quedaban concatenados sin separador). pdfminer.six separa cada valor
    en su propia línea, lo que sí permite anclar por texto de etiqueta con
    regex de forma confiable.

    El formulario tiene DOS layouts distintos confirmados contra PDFs reales,
    según cuántas facturas cubre la constancia:

    - **1 factura** (`cantidad_facturas == 1`): la única página trae el par
      Serie/Número de Factura directamente bajo "Serie" / "Número de Factura",
      y la tabla "DETALLE DE CONSTANCIA" trae exactamente 1 fila con los
      montos de esa factura.
    - **Varias facturas**: la página 1 NO trae ningún par Serie/Número (solo
      un total agregado en "DETALLE DE CONSTANCIA"); en su lugar, una SEGUNDA
      página trae "DETALLE DE RETENCIONES", una tabla con 1 fila por factura
      (Serie, Factura, Fecha, y 3 columnas repetidas de Tarifa/Importe/
      Retención - solo una de las 3 trae valores distintos de cero por fila
      en los ejemplos reales vistos; las otras dos parecen reservadas para
      otras categorías de tarifa que no aplicaron en esos casos). Confirmado
      contra una constancia real de 7 facturas: la suma de "Retención" de
      las 7 filas coincide exactamente con el total de la página 1.

    Si el PDF no calza con ninguno de los dos layouts (un caso todavía no
    visto), no se adivina cómo repartir los montos - se marca
    `requiere_revision_manual` para completar a mano, mismo criterio de "no
    adivinar" que `_fix_mangled_accents`.
    """
    from pdfminer.high_level import extract_text

    texto = extract_text(io.BytesIO(pdf_bytes))
    lines = [line.strip() for line in texto.splitlines() if line.strip()]
    full_text = ' '.join(lines)

    vals = {}

    m = re.search(r'Constancia\s+(\d+)\s+EL SUSCRITO', full_text)
    vals['numero_constancia'] = m.group(1) if m else None

    m = re.search(r'contribuyente\s+([\dK]{5,12})\s+(.+?)\s+Fecha de emisi', full_text)
    if m:
        vals['nit_contribuyente'] = m.group(1)
        vals['nombre_contribuyente'] = _fix_pdf_accents(m.group(2))

    m = re.search(r'D.a\s+(\d{1,2})\s+Mes\s+(\d{1,2})\s+A.o\s+(\d{4})', full_text)
    if m:
        dia, mes, anio = m.groups()
        vals['fecha_emision'] = f'{anio}-{int(mes):02d}-{int(dia):02d}'

    # Total de la constancia - siempre en "DETALLE DE CONSTANCIA" de la página
    # 1, sea de 1 o de varias facturas (en el caso de varias, es la suma
    # agregada, no una fila real de factura - solo se usa para contrastar
    # contra la suma de las líneas, ver monto_retencion_total en el modelo).
    m = re.search(
        r'CONCEPTO\s+TARIFA\s+IMPORTE NETO DEL BIEN\s+RETENCI.N\s+(.*?)\s*TOTAL\s+Q([\d,]+\.\d{2})',
        full_text)
    vals['monto_retencion_pdf'] = float(m.group(2).replace(',', '')) if m else 0.0

    # Layout de varias facturas: tabla "DETALLE DE RETENCIONES" (página 2).
    m_multi = re.search(
        r'Serie\s+Factura\s+Fecha\s+Tarifa\s+Importe\s+Retenci.n\s+Tarifa\s+Importe\s+Retenci.n\s+'
        r'Tarifa\s+Importe\s+Retenci.n\s+(.*?)\s*TOTAL\s+Q',
        full_text, re.IGNORECASE)

    facturas_multi = []
    if m_multi:
        for row in _ROW_PATTERN_RETENCIONES.findall(m_multi.group(1)):
            serie, numero_factura, fecha, t1, i1, r1, t2, i2, r2, t3, i3, r3 = row
            importes = [float(i1.replace(',', '')), float(i2.replace(',', '')), float(i3.replace(',', ''))]
            retenciones = [float(r1.replace(',', '')), float(r2.replace(',', '')), float(r3.replace(',', ''))]
            tarifas = [int(t1), int(t2), int(t3)]
            # Cada factura solo usa UNA de las 3 columnas de tarifa (las otras
            # quedan en 0%/Q0.00 de relleno) - se toma la del bucket con
            # retención > 0 como la tarifa real de esa factura.
            tarifa_real = next((t for t, r in zip(tarifas, retenciones) if r > 0), 0)
            dia_f, mes_f, anio_f = fecha.split('/')
            facturas_multi.append({
                'serie': serie,
                'numero_factura': numero_factura,
                'fecha_factura': f'{anio_f}-{int(mes_f):02d}-{int(dia_f):02d}',
                'tarifa': tarifa_real,
                'monto_importe_neto': sum(importes),
                'monto_retencion': sum(retenciones),
            })

    if facturas_multi:
        vals['cantidad_facturas'] = len(facturas_multi)
        vals['lines'] = facturas_multi
        vals['requiere_revision_manual'] = False
    else:
        # Layout de 1 factura: Serie/Número junto a la única fila de DETALLE
        # DE CONSTANCIA en la página 1.
        m_single = re.search(
            r'Serie\s+N.mero de Factura\s+(\d+)\s+((?:[0-9A-Fa-f]{4,12}\s+\d{4,15}\s*)+)DETALLE DE CONSTANCIA',
            full_text)
        detalle_rows = [
            {
                'concepto': _fix_pdf_accents(concepto.strip()),
                'tarifa': float(tarifa),
                'monto_importe_neto': float(importe.replace(',', '')),
                'monto_retencion': float(retencion.replace(',', '')),
            }
            for concepto, tarifa, importe, retencion in _ROW_PATTERN.findall(m.group(1))
        ] if m else []

        facturas_single = []
        if m_single:
            pares = re.findall(r'([0-9A-Fa-f]{4,12})\s+(\d{4,15})', m_single.group(2))
            facturas_single = [{'serie': serie, 'numero_factura': numero} for serie, numero in pares]

        if facturas_single and len(facturas_single) == len(detalle_rows):
            vals['cantidad_facturas'] = len(facturas_single)
            vals['lines'] = [{**factura, **detalle} for factura, detalle in zip(facturas_single, detalle_rows)]
            vals['requiere_revision_manual'] = False
        else:
            # Ninguno de los dos layouts conocidos calzó - no se adivina cómo
            # repartir los montos, se deja para revisión manual.
            vals['cantidad_facturas'] = len(facturas_single) or len(detalle_rows)
            vals['lines'] = facturas_single or [dict(fila) for fila in detalle_rows]
            vals['requiere_revision_manual'] = True
            _logger.warning(
                'Constancia %s: no calzó con ningún layout conocido (%s factura(s) vs %s fila(s) de '
                'detalle) - revisar montos por línea manualmente.',
                vals.get('numero_constancia'), len(facturas_single), len(detalle_rows),
            )

    m = re.search(
        r'\bNIT\b\s+([\dK]{5,12})\s+Contribuyente\s+(.+?)\s+IDENTIFICACI.N DEL AGENTE RETENEDOR', full_text)
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
