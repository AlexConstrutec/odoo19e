import base64
import re
import shutil
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from odoo import api, models

# La SAT a veces certifica el DTE con el nombre/dirección del contribuyente ya
# dañado: un carácter acentuado (á/é/í/ó/ú/ñ) llega reemplazado por un '?'
# literal ANTES de que nosotros lo veamos - confirmado inspeccionando los bytes
# crudos de XML reales (ej. NombreEmisor="Avi?n Company, S.A.", "AN?NIMA"). No
# es un problema de decodificación de nuestro lado: el carácter original ya se
# perdió. _fix_mangled_accents() intenta recuperarlo por diccionario - si una
# palabra con '?' coincide con una palabra conocida (apellidos/términos legales
# comunes en Guatemala) al probar cada vocal acentuada o 'ñ' en esa posición,
# se corrige. Si no hay una coincidencia clara, se deja el '?' tal cual: mejor
# no adivinar mal que inventar un dato incorrecto en un documento fiscal.
_ACCENT_LOWER = ('á', 'é', 'í', 'ó', 'ú', 'ñ')
_ACCENT_UPPER = ('Á', 'É', 'Í', 'Ó', 'Ú', 'Ñ')
_KNOWN_WORDS_RAW = {
    # Términos legales / societarios
    'ANONIMA', 'COMPAÑIA', 'SUCESION',
    # Sustantivos terminados en "-ción"/"-sión", muy comunes en nombres comerciales
    'ADMINISTRACION', 'CONSTRUCCION', 'DISTRIBUCION', 'IMPORTACION', 'EXPORTACION',
    'PRODUCCION', 'OPERACION', 'ASOCIACION', 'EDUCACION', 'COMUNICACION',
    'ORGANIZACION', 'INFORMACION', 'NACION', 'INVERSION', 'INVERSIONES',
    'CORPORACION', 'FUNDACION', 'TRANSPORTACION', 'PLANIFICACION', 'CAPACITACION',
    'CERTIFICACION', 'CONTRATACION', 'LIQUIDACION', 'ADQUISICION', 'PARTICIPACION',
    'REPRESENTACION', 'COMERCIALIZACION', 'FABRICACION', 'ELABORACION',
    'PRESTACION', 'RECEPCION', 'PROMOCION', 'GESTION', 'REGION', 'PENSION',
    'EXTENSION', 'DIMENSION', 'COMISION', 'MISION', 'VISION', 'DECISION',
    'REVISION', 'PROVISION', 'SUPERVISION', 'DIVISION', 'CONDICION', 'POSICION',
    'CONFECCION',
    # Sustantivos/adjetivos comunes
    'CANTON', 'AVION', 'CAMION', 'ALMACEN', 'ALMACENES', 'ENERGIA', 'ELECTRONICA',
    'ELECTRICA', 'MECANICA', 'QUIMICA', 'TECNICA', 'MEDICA', 'ACADEMICA',
    'ECONOMICA', 'LOGISTICA', 'AUTOMATICA', 'PLASTICA', 'GRAFICA', 'AGRICOLA',
    'UNICA', 'PUBLICA', 'REPUBLICA', 'MULTIPLE', 'CREDITO', 'CLINICA', 'FARMACIA',
    'MAQUINA', 'MAQUINARIA', 'TELEFONO', 'TELEFONICA', 'BASICA', 'PRACTICA',
    'ULTIMA', 'PROXIMA', 'MAXIMA', 'MINIMA', 'OPTICA', 'GENETICA', 'DOMESTICA',
    # Apellidos comunes en Guatemala
    'MENDEZ', 'GARCIA', 'RODRIGUEZ', 'HERNANDEZ', 'PEREZ', 'GOMEZ', 'MARTINEZ',
    'SANCHEZ', 'RAMIREZ', 'JIMENEZ', 'DOMINGUEZ', 'VASQUEZ', 'VELASQUEZ',
    'CHAVEZ', 'CORDOVA', 'NUÑEZ', 'MUÑOZ', 'IBAÑEZ', 'ORDOÑEZ', 'PANIAGUA',
    'CASTAÑEDA', 'ZUÑIGA', 'PEÑA', 'MONTAÑO', 'BARRIENTOS', 'ESQUIVEL',
    # Nombres propios comunes
    'JOSE', 'MARIA', 'JESUS', 'ANGEL', 'RAUL', 'ANDRES', 'RENE', 'MOISES',
    'GERMAN', 'RAMON', 'SIMON', 'ADRIAN', 'JULIAN', 'HECTOR', 'TOMAS',
    'NICOLAS', 'IGNACIO', 'AGUSTIN', 'JOAQUIN', 'ANTON',
}


def _strip_accents_upper(text):
    import unicodedata
    normalized = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in normalized if not unicodedata.combining(c)).upper()


# Normalizado una sola vez: algunas palabras de la lista de arriba llevan ñ/tilde
# escritas directamente (NUÑEZ, COMPAÑIA...) porque así se leen mejor en el
# código, pero la comparación en _fix_mangled_accents es siempre sin acentos.
_KNOWN_WORDS_UPPER = {_strip_accents_upper(w) for w in _KNOWN_WORDS_RAW}


def _fix_mangled_accents(text):
    if not text or '?' not in text:
        return text

    def _fix_token(match):
        token = match.group(0)
        # Si el resto de la palabra está en mayúsculas, la tilde insertada
        # también debe serlo (ANÓNIMA, no ANóNIMA) - se decide por el resto de
        # letras del propio token, no por una lista fija.
        letras = token.replace('?', '')
        candidatos = _ACCENT_UPPER if letras.isupper() else _ACCENT_LOWER
        for accented in candidatos:
            candidate = token.replace('?', accented, 1)
            # Comparar sin acentos: _KNOWN_WORDS_UPPER guarda las palabras SIN
            # tilde (ANONIMA, MENDEZ...) a propósito, para no tener que listar
            # cada palabra dos veces - la tilde insertada aquí es la que se usa
            # en el resultado si hay coincidencia.
            if _strip_accents_upper(candidate) in _KNOWN_WORDS_UPPER:
                return candidate
        return token

    return re.sub(r'[^\W\d_]*\?[^\W\d_]*', _fix_token, text, flags=re.UNICODE)

# Ruta por defecto donde run_sat_download_only.py/run_sat_download_range.py (bot
# Selenium fuera de Odoo, en C:\Users\Alex\Documents\n8n\sat-bot) dejan los
# XML/PDF/Excel descargados de Agencia Virtual. Configurable sin tocar código vía
# el parámetro de sistema 'construtec_account_19.sat_outbox_path' (Ajustes >
# Técnico > Parámetros del Sistema), por si algún día corre en otra máquina/ruta.
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

# Encabezados del Excel del portal -> nombre de campo del modelo. Se empareja
# por texto de encabezado normalizado (sin acentos, minúsculas) porque xlrd a
# veces entrega el texto con problemas de acentos según la máquina/locale, y
# emparejar por posición de columna sería frágil si el portal cambia el orden.
EXCEL_HEADER_MAP = {
    'clasificacion emisor': 'clasificacion_emisor',
    'exportacion': 'exportacion',
    'nombre del establecimiento': 'nombre_establecimiento',
    'estado': 'estado_sat',
    'marca de anulado': 'anulado',
    'fecha de anulacion': 'fecha_anulacion',
    'petroleo (monto de este impuesto)': 'monto_petroleo',
    'turismo hospedaje (monto de este impuesto)': 'monto_turismo_hospedaje',
    'turismo pasajes (monto de este impuesto)': 'monto_turismo_pasajes',
    'timbre de prensa (monto de este impuesto)': 'monto_timbre_prensa',
    'bomberos (monto de este impuesto)': 'monto_bomberos',
    'tasa municipal (monto de este impuesto)': 'monto_tasa_municipal',
    'bebidas alcoholicas (monto de este impuesto)': 'monto_bebidas_alcoholicas',
    'tabaco (monto de este impuesto)': 'monto_tabaco',
    'cemento (monto de este impuesto)': 'monto_cemento',
    'bebidas no alcoholicas (monto de este impuesto)': 'monto_bebidas_no_alcoholicas',
    'tarifa portuaria (monto de este impuesto)': 'monto_tarifa_portuaria',
}
EXCEL_HEADER_NUMERO_AUTORIZACION = 'numero de autorizacion'
EXCEL_MONETARY_FIELDS = {
    'monto_petroleo', 'monto_turismo_hospedaje', 'monto_turismo_pasajes', 'monto_timbre_prensa',
    'monto_bomberos', 'monto_tasa_municipal', 'monto_bebidas_alcoholicas', 'monto_tabaco',
    'monto_cemento', 'monto_bebidas_no_alcoholicas', 'monto_tarifa_portuaria',
}


def _normalize_header(text: str) -> str:
    import unicodedata
    text = unicodedata.normalize('NFKD', text or '').encode('ascii', 'ignore').decode('ascii')
    return text.strip().lower()


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
    direccion_emisor_el = root.find('.//dte:Emisor/dte:DireccionEmisor/dte:Direccion', NS)
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

        numero_linea_raw = item.get('NumeroLinea')
        lines.append({
            'numero_linea': int(numero_linea_raw) if numero_linea_raw else 0,
            'bien_o_servicio': item.get('BienOServicio'),
            'descripcion': _fix_mangled_accents(_text('Descripcion', '')),
            'cantidad': float(_text('Cantidad')),
            'precio_unitario': float(_text('PrecioUnitario')),
            'monto_descuento': float(_text('Descuento')),
            'otro_descuento': float(_text('OtrosDescuento')),
            'monto_iva': monto_iva_linea,
            'monto_total': float(_text('Total')),
        })

    return {
        'numero_autorizacion': (numero_autorizacion_el.text or '').strip()
        if numero_autorizacion_el is not None else '',
        'tipo_dte': datos_generales.get('Tipo') if datos_generales is not None else None,
        'moneda_codigo': datos_generales.get('CodigoMoneda') if datos_generales is not None else None,
        'serie': numero_autorizacion_el.get('Serie') if numero_autorizacion_el is not None else None,
        'numero_documento': numero_autorizacion_el.get('Numero') if numero_autorizacion_el is not None else None,
        'fecha_certificacion': _parse_dte_datetime(certificacion.find('dte:FechaHoraCertificacion', NS).text)
        if certificacion is not None else None,
        'nit_emisor': emisor.get('NITEmisor') if emisor is not None else None,
        'nombre_emisor': _fix_mangled_accents(emisor.get('NombreEmisor')) if emisor is not None else None,
        'nombre_comercial_emisor': _fix_mangled_accents(emisor.get('NombreComercial')) if emisor is not None else None,
        'codigo_establecimiento': emisor.get('CodigoEstablecimiento') if emisor is not None else None,
        'direccion_emisor': _fix_mangled_accents(direccion_emisor_el.text) if direccion_emisor_el is not None else None,
        'nit_receptor': receptor.get('IDReceptor') if receptor is not None else None,
        'nombre_receptor': _fix_mangled_accents(receptor.get('NombreReceptor')) if receptor is not None else None,
        'nit_certificador': certificacion.find('dte:NITCertificador', NS).text
        if certificacion is not None and certificacion.find('dte:NITCertificador', NS) is not None else None,
        'nombre_certificador': _fix_mangled_accents(certificacion.find('dte:NombreCertificador', NS).text)
        if certificacion is not None and certificacion.find('dte:NombreCertificador', NS) is not None else None,
        'monto_total': float(gran_total_el.text) if gran_total_el is not None and gran_total_el.text else 0.0,
        'monto_iva': float(total_iva_el.get('TotalMontoImpuesto')) if total_iva_el is not None else 0.0,
        'lines': lines,
    }


def _parse_dte_excel(xls_bytes: bytes) -> dict:
    """Lee el Excel-resumen que trae el portal (un renglon por DTE) y regresa
    {numero_autorizacion: {campos del modelo}} para complementar documentos ya
    creados desde el XML - notablemente 'anulado'/'fecha_anulacion', que el
    XML nunca refleja porque se certifica antes de que exista la posibilidad
    de anular. Usa xlrd (ya viene con Odoo) porque el portal entrega .xls
    clásico, no .xlsx. Recibe los bytes crudos (no una ruta) para poder
    parsearse igual sea que el archivo viva en el mismo disco (acción local
    action_import_from_outbox) o llegue por API desde otra máquina
    (import_excel_summary, para cuando Odoo corre remoto, ej. Odoo.sh).
    """
    import xlrd

    book = xlrd.open_workbook(file_contents=xls_bytes)
    sheet = book.sheet_by_index(0)
    if sheet.nrows < 2:
        return {}

    headers = [_normalize_header(str(sheet.cell_value(0, col))) for col in range(sheet.ncols)]
    col_numero_autorizacion = None
    col_by_field = {}
    for col, header in enumerate(headers):
        if header == EXCEL_HEADER_NUMERO_AUTORIZACION:
            col_numero_autorizacion = col
        elif header in EXCEL_HEADER_MAP:
            col_by_field[EXCEL_HEADER_MAP[header]] = col

    if col_numero_autorizacion is None:
        return {}

    result = {}
    for row in range(1, sheet.nrows):
        numero_autorizacion = str(sheet.cell_value(row, col_numero_autorizacion)).strip()
        if not numero_autorizacion:
            continue

        row_vals = {}
        for field_name, col in col_by_field.items():
            raw_value = sheet.cell_value(row, col)
            if field_name == 'anulado':
                row_vals[field_name] = str(raw_value).strip().lower() in {'si', 'sí', 'yes', 'true', '1'}
            elif field_name == 'fecha_anulacion':
                text_value = str(raw_value).strip()
                row_vals[field_name] = _parse_dte_datetime(text_value) if text_value else False
            elif field_name in EXCEL_MONETARY_FIELDS:
                try:
                    row_vals[field_name] = float(raw_value)
                except (TypeError, ValueError):
                    row_vals[field_name] = 0.0
            else:
                row_vals[field_name] = _fix_mangled_accents(str(raw_value).strip())
        result[numero_autorizacion] = row_vals

    return result


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
    def _sat_iter_outbox_excel_files(self):
        outbox = self._sat_outbox_path()
        if not outbox.exists():
            return
        for section_dir in outbox.glob('*/section_*/excel'):
            for xls_path in list(section_dir.glob('*.xls')) + list(section_dir.glob('*.xlsx')):
                yield xls_path

    @api.model
    def _sat_find_matching_pdf(self, xml_path):
        candidate = xml_path.parent.parent / 'pdf' / (xml_path.stem + '.pdf')
        return candidate if candidate.exists() else None

    @api.model
    def _sat_move_to_duplicados(self, xml_path, pdf_path):
        """Los documentos duplicados no se borran (a diferencia de éxito): se
        mueven a data/duplicados/<empresa>/<seccion>/{xml,pdf}, espejo de la
        estructura de outbox, para dejar rastro de qué se intentó reimportar
        sin tener que confiar solo en la bitácora de Odoo."""
        outbox_root = self._sat_outbox_path()
        duplicados_root = outbox_root.parent / 'duplicados'
        for path in (xml_path, pdf_path):
            if not path:
                continue
            try:
                relative = path.relative_to(outbox_root)
            except ValueError:
                continue
            destino = duplicados_root / relative
            destino.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(path), str(destino))
            except Exception:
                pass

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
    def import_excel_summary(self, xls_base64):
        """Equivalente remoto de la parte de Excel de action_import_from_outbox():
        pensado para cuando Odoo corre en otra máquina (ej. Odoo.sh) y por lo
        tanto no puede leer el Excel directo del disco del bot - el llamador
        externo solo manda los bytes en base64, y aquí se hace TODO el parseo
        (mismo _parse_dte_excel que usa la acción local) más la aplicación de
        cada fila vía update_from_excel_row(). Devuelve cuántas filas traía el
        Excel y a cuántas les encontró un documento ya existente para
        actualizar (las que no, es porque su XML aún no se ha importado).
        """
        filas = _parse_dte_excel(base64.b64decode(xls_base64))
        actualizados = 0
        for numero_autorizacion, row_vals in filas.items():
            if self.update_from_excel_row(numero_autorizacion, row_vals):
                actualizados += 1
        return {'filas_en_excel': len(filas), 'documentos_actualizados': actualizados}

    @api.model
    def action_import_from_outbox(self):
        """Botón/acción "Importar desde SAT": lee los XML/Excel que el bot
        (fuera de Odoo) dejó en la carpeta outbox local, los parsea, y llama a
        create_from_dte()/update_from_excel_row() DIRECTO por ORM (sin pasar
        por XML-RPC/JSON-RPC - el código ya corre dentro de Odoo).

        Ciclo de vida de los archivos tras procesarlos (para no reimportar ni
        acumular basura en el outbox):
          - Creado en Odoo: se borran XML+PDF locales (el XML ya trae todos
            los campos que se necesitan - no se adjunta el PDF a Odoo, es
            informacion redundante con lo que ya se guarda en los campos del
            documento).
          - Duplicado (numero_autorizacion ya existía): se mueven a
            data/duplicados/<empresa>/<seccion>/ en vez de borrarse, para
            dejar rastro de qué se reintentó.
          - Error: se dejan intactos en outbox para reintentar en la próxima
            corrida.
          - Excel: se usa solo para leer datos (anulado/estado/etc, ver
            update_from_excel_row) y aplicarlos a los documentos que ya
            existan - nunca se adjunta como archivo, y se borra del outbox
            tras leerlo (es un resumen de muchos documentos, no algo que
            pueda "duplicarse" como un XML individual).
        """
        resumen = {'success': 0, 'skipped_duplicate': 0, 'error': 0}
        Document = self.env['construtec.sat.document']

        for direction, xml_path in self._sat_iter_outbox_xml_files():
            pdf_path = self._sat_find_matching_pdf(xml_path)
            try:
                with open(xml_path, 'rb') as f:
                    xml_bytes = f.read()
                vals = _parse_dte_xml(xml_bytes)
                vals['direction'] = direction
                vals['xml_filename'] = xml_path.name
                vals['xml_base64'] = base64.b64encode(xml_bytes).decode()

                result = Document.create_from_dte(vals)
                estado = result.get('state', 'error')
            except Exception:
                estado = 'error'
            resumen[estado] = resumen.get(estado, 0) + 1

            if estado == 'success':
                for path in (xml_path, pdf_path):
                    if path:
                        path.unlink(missing_ok=True)
            elif estado == 'skipped_duplicate':
                self._sat_move_to_duplicados(xml_path, pdf_path)
            # estado == 'error': se deja todo intacto para reintentar despues.

        for xls_path in self._sat_iter_outbox_excel_files():
            try:
                with open(xls_path, 'rb') as f:
                    xls_bytes = f.read()
                filas = _parse_dte_excel(xls_bytes)
                for numero_autorizacion, row_vals in filas.items():
                    Document.update_from_excel_row(numero_autorizacion, row_vals)
                xls_path.unlink(missing_ok=True)
            except Exception:
                pass

        mensaje = (
            f"Creados: {resumen.get('success', 0)} | "
            f"Duplicados (movidos): {resumen.get('skipped_duplicate', 0)} | "
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
