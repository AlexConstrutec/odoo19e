"""Cliente delgado para la API de Anthropic (Claude) - extrae datos estructurados de una
cotización de proveedor (imagen, PDF o texto plano ya extraído de un .docx).

Copia deliberada del mismo estilo que `enterprise_sync_api.py` (requests puro, una excepción
propia, funciones pequeñas de un solo propósito) - no se agrega el SDK oficial `anthropic`,
que sería la única dependencia de SDK en un módulo que mantiene cada integración externa como
su propio cliente HTTP pequeño, sin librerías compartidas entre integraciones.
"""
import base64
import io
import logging
import re

import requests

_logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 90  # una llamada con imagen/PDF tarda más que las de enterprise_sync_api (10s)
ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages'
ANTHROPIC_VERSION = '2023-06-01'
DEFAULT_MODEL = 'claude-sonnet-5'
MAX_IMAGE_LONG_EDGE = 1568  # límite recomendado por Anthropic para el lado largo de una imagen
TOOL_NAME = 'registrar_cotizacion'

_TOOL_SCHEMA = {
    'name': TOOL_NAME,
    'description': 'Registra los datos extraídos de una cotización de proveedor (precios de materiales).',
    'input_schema': {
        'type': 'object',
        'properties': {
            'proveedor': {
                'type': 'string',
                'description': 'Nombre del proveedor que emitió la cotización. Cadena vacía si no se puede determinar.',
            },
            'fecha': {
                'type': 'string',
                'description': 'Fecha de la cotización, en formato AAAA-MM-DD. Cadena vacía si no aparece en el documento.',
            },
            'lineas': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'descripcion': {'type': 'string', 'description': 'Descripción del material/producto.'},
                        'cantidad': {'type': 'number'},
                        'unidad': {'type': 'string', 'description': 'Unidad de medida (ej. "bolsa", "unidad", "metro"). Cadena vacía si no aparece.'},
                        'precio_unitario': {'type': 'number'},
                    },
                    'required': ['descripcion', 'cantidad', 'precio_unitario'],
                },
            },
        },
        'required': ['lineas'],
    },
}

_INSTRUCCIONES = (
    'Eres un asistente que extrae cotizaciones de proveedores de materiales de construcción '
    'en Guatemala. Extrae el nombre del proveedor, la fecha de la cotización y cada línea de '
    'materiales/precios que encuentres, usando la herramienta registrar_cotizacion. Si un dato '
    'no aparece en el documento, omítelo o usa una cadena vacía - nunca inventes cifras que no '
    'estén ahí.'
)


class QuoteExtractionError(Exception):
    """Cualquier falla llamando a la API de Anthropic o interpretando su respuesta."""


def _call_messages_api(api_key, content_blocks):
    if not api_key:
        raise QuoteExtractionError('No se configuró la Anthropic API Key (Ajustes > Facturación).')
    headers = {
        'x-api-key': api_key,
        'anthropic-version': ANTHROPIC_VERSION,
        'content-type': 'application/json',
    }
    body = {
        'model': DEFAULT_MODEL,
        'max_tokens': 4096,
        'tools': [_TOOL_SCHEMA],
        'tool_choice': {'type': 'tool', 'name': TOOL_NAME},
        'messages': [{
            'role': 'user',
            'content': content_blocks + [{'type': 'text', 'text': _INSTRUCCIONES}],
        }],
    }
    try:
        response = requests.post(ANTHROPIC_API_URL, json=body, headers=headers, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise QuoteExtractionError(f'No se pudo conectar con Anthropic: {exc}') from exc

    if response.status_code != 200:
        try:
            detail = response.json().get('error', {}).get('message', response.text)
        except ValueError:
            detail = response.text
        raise QuoteExtractionError(f'Anthropic devolvió un error ({response.status_code}): {detail}')

    try:
        data = response.json()
    except ValueError as exc:
        raise QuoteExtractionError('Respuesta inválida de Anthropic (no es JSON).') from exc

    tool_blocks = [
        b for b in data.get('content', [])
        if b.get('type') == 'tool_use' and b.get('name') == TOOL_NAME
    ]
    if not tool_blocks:
        raise QuoteExtractionError('Anthropic no devolvió datos estructurados (respuesta inesperada).')
    return _validar_resultado(tool_blocks[0].get('input') or {})


_FECHA_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def _validar_resultado(result):
    limpias = []
    for linea in result.get('lineas') or []:
        try:
            limpias.append({
                'descripcion': str(linea.get('descripcion') or '').strip(),
                'cantidad': float(linea.get('cantidad') or 0),
                'unidad': str(linea.get('unidad') or '').strip() or False,
                'precio_unitario': float(linea.get('precio_unitario') or 0),
            })
        except (TypeError, ValueError):
            _logger.warning('Línea de cotización descartada por datos no numéricos: %r', linea)

    fecha = str(result.get('fecha') or '').strip()
    if not _FECHA_RE.match(fecha):
        # No inventamos ni intentamos "arreglar" un formato raro - si la IA no devolvió
        # AAAA-MM-DD exacto, se deja vacío y el jefe de técnicos lo llena a mano si hace falta.
        if fecha:
            _logger.warning('Fecha de cotización descartada por formato inesperado: %r', fecha)
        fecha = False

    return {
        'proveedor': (result.get('proveedor') or '').strip() or False,
        'fecha': fecha,
        'lineas': limpias,
    }


def _resize_image_if_needed(image_bytes):
    """Reduce fotos de teléfono grandes antes de enviarlas - baja el costo de tokens y evita
    tropezar con el límite de tamaño de Anthropic. Usa Pillow, ya disponible en este entorno
    (Odoo mismo depende de PIL para campos Image)."""
    from PIL import Image
    img = Image.open(io.BytesIO(image_bytes))
    if max(img.size) <= MAX_IMAGE_LONG_EDGE:
        return image_bytes
    img.thumbnail((MAX_IMAGE_LONG_EDGE, MAX_IMAGE_LONG_EDGE))
    buf = io.BytesIO()
    img.convert('RGB').save(buf, format='JPEG', quality=85)
    return buf.getvalue()


def extract_quote_from_image(api_key, image_bytes, media_type):
    image_bytes = _resize_image_if_needed(image_bytes)
    data = base64.b64encode(image_bytes).decode('ascii')
    block = {'type': 'image', 'source': {'type': 'base64', 'media_type': media_type, 'data': data}}
    return _call_messages_api(api_key, [block])


def extract_quote_from_pdf(api_key, pdf_bytes):
    data = base64.b64encode(pdf_bytes).decode('ascii')
    block = {'type': 'document', 'source': {'type': 'base64', 'media_type': 'application/pdf', 'data': data}}
    return _call_messages_api(api_key, [block])


def extract_quote_from_text(api_key, text):
    block = {'type': 'text', 'text': f'Texto extraído de un documento Word:\n\n{text}'}
    return _call_messages_api(api_key, [block])
