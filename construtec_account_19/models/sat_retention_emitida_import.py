import io
import logging
import re

from odoo import fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


def _parse_constancia_emitida_pdf(pdf_bytes):
    """Parsea el formulario SAT-1911 (Constancia de Retención de ISR EMITIDA) descargado de
    Agencia Virtual - Servicios Tributarios > Retenciones Web > Consulta constancias de
    retención, para las categorías "Opcional Simplificado Sobre Ingresos", "Rentas de Capital
    Inmobiliario" y "Rentas de Capital Mobiliario" (la cuarta categoría de esa pantalla,
    "Facturas Especiales", no trae PDF descargable fila-por-fila y de todas formas ya se
    extrae automáticamente del complemento FESP del propio XML del DTE - ver
    `_extraer_retencion_fesp` en sat_document_import.py - así que se omite aquí a propósito).

    A diferencia del formulario SAT-2229 (`_parse_constancia_pdf`, Constancias Recibidas), este
    SIEMPRE trae exactamente 1 Serie/Número de Factura por constancia (confirmado contra 2 PDF
    reales de categorías distintas, mismo layout) - no existe el caso multi-factura de aquel
    otro formulario.

    Verificado contra 2 PDF reales (extract_text real de pdfminer.six, no la lectura-de-PDF de
    Claude, que muestra el texto ya limpio y no reproduce la corrupción de acentos real que
    ve el parser en producción):
    - Constancia 1787178826546 ("RÉGIMEN OPCIONAL SIMPLIFICADO...", tarifa 5%).
    - Constancia 1788278827554 ("RENTAS DE CAPITAL INMOBILIARIO", tarifa 10%).
    Ambos PDF son idénticos en estructura, solo cambia el texto del régimen/monto/tarifa
    implícita - confirma que basta UN parser genérico (sin casos especiales por régimen).
    """
    from pdfminer.high_level import extract_text
    from .sat_document_import import _fix_mangled_accents

    def fix_accents(text):
        if not text:
            return text
        return _fix_mangled_accents(text.replace('�', '?'))

    texto = extract_text(io.BytesIO(pdf_bytes))
    lines = [line.strip() for line in texto.splitlines() if line.strip()]
    full_text = ' '.join(lines)

    vals = {'requiere_revision_manual': False}

    m = re.search(r'Constancia\s+(\d+)\s+EL SUSCRITO AGENTE RETENEDOR', full_text)
    vals['numero_constancia'] = m.group(1) if m else None

    m = re.search(r'contribuyente\s+([\dK]{5,12})\s+(.+?)\s+Fecha de emisi', full_text)
    if m:
        vals['nit_retenido'] = m.group(1)
        vals['nombre_retenido'] = fix_accents(m.group(2))

    m = re.search(r'D.a\s+(\d{1,2})\s+Mes\s+(\d{1,2})\s+A.o\s+(\d{4})', full_text)
    if m:
        dia, mes, anio = m.groups()
        vals['fecha_emision'] = f'{anio}-{int(mes):02d}-{int(dia):02d}'

    # Anclado con la etiqueta "Serie Número de factura" - único punto donde aparece ese texto
    # literal, justo antes del par Serie/Número correcto. Un primer intento capturaba Serie/
    # Número con un regex SEPARADO del de régimen/concepto/montos, y volvía a hacer re.search
    # contra full_text para ese segundo regex - eso emparejaba por error la MISMA corrida de
    # dígitos de numero_constancia (aparece antes en el texto y también tiene 4-15 dígitos) en
    # vez del numero_factura real. Combinar ambas capturas en un solo regex, anclado en el
    # literal "Serie Número de factura", lo resuelve sin ambigüedad - confirmado real contra
    # los 2 PDF de muestra.
    m = re.search(
        r'Serie\s+N.mero de factura\s+([0-9A-Fa-f]{4,12})\s+(\d{4,15})\s+(.+?)\s+CONCEPTO\s+'
        r'RENTA IMPONIBLE\s+RETENCI.N\s+(.+?)\s+TOTAL\s+Q([\d,]+\.\d{2})\s+Q([\d,]+\.\d{2})\s+'
        r'Q([\d,]+\.\d{2})',
        full_text)
    if m:
        serie, numero_factura, regimen, concepto, renta_imponible, retencion, _total = m.groups()
        vals['serie'] = serie
        vals['numero_factura'] = numero_factura
        vals['lines'] = [{
            'regimen': fix_accents(regimen.strip()),
            'concepto': fix_accents(concepto.strip()),
            'monto_renta_imponible': float(renta_imponible.replace(',', '')),
            'monto_retencion': float(retencion.replace(',', '')),
        }]
    else:
        # No calzó con el único layout confirmado - no se adivina cómo repartir los montos,
        # se deja para revisión manual (mismo criterio de "no adivinar" que sat_retention_import.py).
        vals['lines'] = []
        vals['requiere_revision_manual'] = True
        _logger.warning(
            'Constancia emitida %s: no calzó con el layout SAT-1911 conocido - revisar '
            'Serie/Número de factura y montos manualmente.', vals.get('numero_constancia'),
        )

    m = re.search(
        r'NIT\s+([\dK]{5,12})\s+Contribuyente\s+(.+?)\s+IDENTIFICACI.N DEL AGENTE RETENEDOR',
        full_text)
    if m:
        vals['nit_agente_retenedor'] = m.group(1)
        vals['nombre_agente_retenedor'] = fix_accents(m.group(2))

    return vals


class ConstructecSatRetentionEmitidaImportWizard(models.TransientModel):
    _name = 'construtec.sat.retention.emitida.import.wizard'
    _description = 'Importar Constancia de Retención de ISR Emitida desde PDF'

    pdf_file = fields.Binary(string='PDF de la Constancia', required=True)
    pdf_filename = fields.Char(string='Nombre de Archivo')

    def action_importar(self):
        self.ensure_one()
        if not self.pdf_file:
            raise UserError(self.env._('Selecciona un archivo PDF primero.'))

        result = self.env['construtec.sat.retention.emitida'].create_from_pdf(
            self.pdf_file, self.pdf_filename)

        if result['state'] == 'skipped_duplicate':
            message = self.env._('Esta constancia ya había sido importada.')
        elif result['state'] == 'nit_no_permitido':
            message = self.env._(
                'El NIT del agente retenedor del PDF no coincide con el de esta compañía - no '
                'se importó nada.')
        else:
            message = self.env._('Constancia importada correctamente.')

        notification = {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._('Importar Constancia Emitida'),
                'message': message,
                'type': 'success' if result['state'] == 'success' else 'warning',
            },
        }
        if result.get('retention_id'):
            notification['params']['next'] = {
                'type': 'ir.actions.act_window',
                'res_model': 'construtec.sat.retention.emitida',
                'res_id': result['retention_id'],
                'view_mode': 'form',
                'target': 'current',
            }
        return notification
