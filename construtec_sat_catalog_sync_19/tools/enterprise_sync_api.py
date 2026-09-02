"""Thin JSON-RPC client for pulling the Materials Catalog directly from Enterprise's own local
copy of it (`construtec.materials.catalog.mirror`).

Community used to receive this by push (Enterprise calling it over XML-RPC on every catalog
change) - as of 2026-09 that was replaced by this pull, matching the pattern already used by
construtec_account_payment_order_19 for empleados/cuentas analíticas (Enterprise is the source
of truth, Community only needs a read-only reference copy). Deliberate small copy of that
module's own tools/enterprise_sync_api.py, not a shared dependency - this module is
deliberately standalone (`depends: ['base']` only, no dependency on
construtec_account_payment_order_19 nor construtec_account_19), so it keeps its own
URL/credentials, revocable independently of any other integration.
"""
import logging

import requests

_logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 10
SYNC_MODEL = 'construtec.materials.catalog.mirror'


class EnterpriseSyncError(Exception):
    """Any failure talking to Enterprise (config/network/auth/API)."""


def _jsonrpc(url, service, method, args):
    if not url:
        raise EnterpriseSyncError('No se configuró la URL de Enterprise.')
    if not url.lower().startswith('https://'):
        _logger.warning(
            'Sincronización del Catálogo de Materiales usando una URL no-HTTPS (%s); '
            'use HTTPS en producción.', url)
    endpoint = f"{url.rstrip('/')}/jsonrpc"
    payload = {
        'jsonrpc': '2.0',
        'method': 'call',
        'params': {'service': service, 'method': method, 'args': args},
        'id': 1,
    }
    try:
        response = requests.post(endpoint, json=payload, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise EnterpriseSyncError(f'No se pudo conectar a Enterprise: {exc}') from exc
    except ValueError as exc:
        raise EnterpriseSyncError('Respuesta inválida del servidor Enterprise.') from exc

    if 'error' in data:
        err = data['error']
        message = (err.get('data') or {}).get('message') or err.get('message') or str(err)
        raise EnterpriseSyncError(message)
    if 'result' not in data:
        raise EnterpriseSyncError('Enterprise no devolvió resultado (¿URL/versión correcta?).')
    return data['result']


def authenticate(url, db, login, api_key):
    uid = _jsonrpc(url, 'common', 'authenticate', [db, login, api_key, {}])
    if not uid:
        raise EnterpriseSyncError(
            'Autenticación rechazada por Enterprise: usuario, base de datos o API Key inválidos.')
    return uid


def check_connection(url, db, login, api_key):
    """Valida credenciales contra Enterprise sin escribir nada.

    Returns (uid, server_version_info) on success; raises EnterpriseSyncError on failure.
    """
    if not (url and db and login and api_key):
        raise EnterpriseSyncError(
            'Complete URL, base de datos, usuario y API Key antes de probar la conexión.')
    version_info = _jsonrpc(url, 'common', 'version', [])
    uid = authenticate(url, db, login, api_key)
    return uid, version_info


def fetch_materials_catalog(url, db, login, api_key):
    """Read-only pull de la copia local de Enterprise del Catálogo de Materiales - el mismo
    modelo (`construtec.materials.catalog.mirror`) que Enterprise ya llena localmente desde
    `construtec.sat.product.catalog` (ver construtec_account_19). `base.group_user` ya tiene
    acceso de solo lectura a este modelo (security/ir.model.access.csv, ambos lados) - no hace
    falta un grupo de integración dedicado del lado Enterprise para esto, a diferencia del lado
    Community (que sí necesita `group_sat_catalog_sync_integration` para poder escribir vía
    `sync_from_enterprise()`, aquí llamado localmente en vez de por RPC entrante).

    Deliberadamente NO se pide `company_id` - el id de compañía de Enterprise no significa nada
    en Community (bases de datos distintas); `sync_from_enterprise()` ya cae en la compañía
    activa de quien sincroniza cuando `company_id` no llega en `vals`."""
    if not (url and db and login and api_key):
        raise EnterpriseSyncError(
            'Sincronización del Catálogo de Materiales incompleta (falta URL, base de datos, '
            'usuario o API Key).')
    uid = authenticate(url, db, login, api_key)
    return _jsonrpc(
        url, 'object', 'execute_kw',
        [db, uid, api_key, SYNC_MODEL, 'search_read', [[]],
         {'fields': ['origin_id', 'name', 'codigo', 'partner_name', 'partner_vat', 'uom_name',
                     'currency_name', 'precio_referencia', 'primera_fecha_compra',
                     'ultima_fecha_compra', 'bien_o_servicio']}])
