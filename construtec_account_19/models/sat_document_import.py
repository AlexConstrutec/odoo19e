import base64
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from odoo import api, models

# Ruta por defecto donde run_sat_download_only.py (bot Selenium fuera de Odoo, en
# C:\Users\Alex\Documents\n8n\sat-bot) deja los XML/PDF descargados de Agencia
# Virtual. Configurable sin tocar código vía el parámetro de sistema
# 'construtec_account_19.sat_outbox_path' (Ajustes > Técnico > Parámetros del
# Sistema), por si algún día corre en otra máquina/ruta.
DEFAULT_OUTBOX_PATH = r'C:\Users\Alex\Documents\n8n\sat-bot\data\outbox'

NS = {'dte': 'http://www.sat.gob.gt/dte/fel/0.2.0'}

# Nombre de subcarpeta de sección -> dirección del documento SAT. Confirmado con
# datos reales: section_1 son documentos donde el Receptor del DTE es la cuenta
# propia (compras/recibidas); section_2 son donde el Emisor es la cuenta propia
# (ventas/emitidas).
SECTION_TO_DIRECTION = {
    'section_1': 'recibida',
    'section_2': 'emitida',
}


def _parse_dte_datetime(raw: str) -> str:
    """'2026-08-03T17:12:45-06:00' -> '2026-08-03 23:12:45' (UTC, formato Odoo)."""
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def _parse_dte_xml(xml_bytes: bytes) -> dict:
    root = ET.fromstring(xml_bytes)

    datos_generales = root.find('.//dte:DatosGenerales', NS)
    emisor = root.find('.//dte:Emisor', NS)
    receptor = root.find('.//dte:Receptor', NS)
    certificacion = root.find('.//dte:Certificacion', NS)
    numero_autorizacion_el = root.find('.//dte:NumeroAutorizacion', NS)
    gran_total_el = root.find('.//dte:Totales/dte:GranTotal', NS)
    total_iva_el = root.find(
        ".//dte:Totales/dte:TotalImpuestos/dte:TotalImpuesto[@NombreCorto='IVA']", NS)

    lines = []
    for item in root.findall('.//dte:Items/dte:Item', NS):
        monto_iva_linea = 0.0
        for impuesto in item.findall('.//dte:Impuestos/dte:Impuesto', NS):
            monto_el = impuesto.find('dte:MontoImpuesto', NS)
            if monto_el is not None and monto_el.text:
                monto_iva_linea += float(monto_el.text)

        def _text(tag, default='0'):
            el = item.find(f'dte:{tag}', NS)
            return el.text if el is not None and el.text else default

        lines.append({
            'descripcion': _text('Descripcion', ''),
            'cantidad': float(_text('Cantidad')),
            'precio_unitario': float(_text('PrecioUnitario')),
            'monto_descuento': float(_text('Descuento')),
            'monto_iva': monto_iva_linea,
            'monto_total': float(_text('Total')),
        })

    return {
        'numero_autorizacion': (numero_autorizacion_el.text or '').strip()
        if numero_autorizacion_el is not None else '',
        'tipo_dte': datos_generales.get('Tipo') if datos_generales is not None else None,
        'serie': numero_autorizacion_el.get('Serie') if numero_autorizacion_el is not None else None,
        'numero_documento': numero_autorizacion_el.get('Numero') if numero_autorizacion_el is not None else None,
        'fecha_certificacion': _parse_dte_datetime(certificacion.find('dte:FechaHoraCertificacion', NS).text)
        if certificacion is not None else None,
        'nit_emisor': emisor.get('NITEmisor') if emisor is not None else None,
        'nombre_emisor': emisor.get('NombreEmisor') if emisor is not None else None,
        'nit_receptor': receptor.get('IDReceptor') if receptor is not None else None,
        'nombre_receptor': receptor.get('NombreReceptor') if receptor is not None else None,
        'monto_total': float(gran_total_el.text) if gran_total_el is not None and gran_total_el.text else 0.0,
        'monto_iva': float(total_iva_el.get('TotalMontoImpuesto')) if total_iva_el is not None else 0.0,
        'lines': lines,
    }


class ConstructecSatDocument(models.Model):
    _inherit = 'construtec.sat.document'

    @api.model
    def _sat_outbox_path(self):
        return Path(self.env['ir.config_parameter'].sudo().get_param(
            'construtec_account_19.sat_outbox_path', DEFAULT_OUTBOX_PATH))

    @api.model
    def _sat_iter_outbox_xml_files(self):
        outbox = self._sat_outbox_path()
        if not outbox.exists():
            return
        for section_dir in outbox.glob('*/section_*/xml'):
            direction = SECTION_TO_DIRECTION.get(section_dir.parent.name)
            if not direction:
                continue
            for xml_path in section_dir.glob('*.xml'):
                yield direction, xml_path

    @api.model
    def _sat_find_matching_pdf(self, xml_path):
        candidate = xml_path.parent.parent / 'pdf' / (xml_path.stem + '.pdf')
        return candidate if candidate.exists() else None

    @api.model
    def create_from_dte_xml(self, xml_base64, direction):
        """Punto de entrada por API pensado para que n8n (u otro orquestador externo)
        lo llame directo vía execute_kw, pasando SOLO el XML del DTE en base64 y la
        dirección ('recibida'/'emitida', según de qué sección lo descargó) — sin PDF,
        sin parsear nada del lado de n8n. Reusa el mismo parser probado que usa
        action_import_from_outbox() y termina llamando a create_from_dte(), así que
        hereda toda su idempotencia por numero_autorizacion: n8n puede reintentar o
        volver a mandar el mismo XML sin miedo a duplicar, no necesita llevar su
        propio registro de "qué ya subí" - Odoo lo decide leyendo el numero_autorizacion
        que trae el propio XML.
        """
        xml_bytes = base64.b64decode(xml_base64)
        vals = _parse_dte_xml(xml_bytes)
        vals['direction'] = direction
        vals['xml_filename'] = f"{vals.get('numero_autorizacion') or 'documento'}.xml"
        vals['xml_base64'] = xml_base64
        return self.create_from_dte(vals)

    @api.model
    def action_import_from_outbox(self):
        """Botón/acción "Importar desde SAT": lee los XML que run_sat_download_only.py
        (el bot Selenium, fuera de Odoo) ya dejó en la carpeta outbox local, los
        parsea, y llama a create_from_dte() DIRECTO por ORM (sin pasar por
        XML-RPC/JSON-RPC - el código ya corre dentro de Odoo). Segura de repetir:
        create_from_dte ya es idempotente por numero_autorizacion.
        """
        resumen = {'success': 0, 'skipped_duplicate': 0, 'error': 0}
        Document = self.env['construtec.sat.document']

        for direction, xml_path in self._sat_iter_outbox_xml_files():
            try:
                with open(xml_path, 'rb') as f:
                    xml_bytes = f.read()
                vals = _parse_dte_xml(xml_bytes)
                vals['direction'] = direction
                vals['xml_filename'] = xml_path.name
                vals['xml_base64'] = base64.b64encode(xml_bytes).decode()

                pdf_path = self._sat_find_matching_pdf(xml_path)
                if pdf_path:
                    with open(pdf_path, 'rb') as f:
                        pdf_bytes = f.read()
                    vals['pdf_filename'] = pdf_path.name
                    vals['pdf_base64'] = base64.b64encode(pdf_bytes).decode()

                result = Document.create_from_dte(vals)
                estado = result.get('state', 'error')
            except Exception:
                estado = 'error'
            resumen[estado] = resumen.get(estado, 0) + 1

        mensaje = (
            f"Creados: {resumen.get('success', 0)} | "
            f"Duplicados (omitidos): {resumen.get('skipped_duplicate', 0)} | "
            f"Errores: {resumen.get('error', 0)}"
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Importación de documentos SAT',
                'message': mensaje,
                'sticky': resumen.get('error', 0) > 0,
                'type': 'warning' if resumen.get('error', 0) > 0 else 'success',
            },
        }
