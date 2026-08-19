"""Thin JSON-RPC client for pushing Solicitudes de Pago to a Procesador instance.

Deliberate small copy of construtec_materials_19/tools/enterprise_sync_api.py (Odoo19C),
not a shared library: this lets each integration (Materiales, Solicitudes de Pago) use its
own URL/credentials and be revoked independently, without coupling this module to another
one just to reuse ~90 lines. The receiving side is just this same module's own
`account.payment.order.request` model, installed on the Procesador instance - reached
through Odoo's own built-in `/jsonrpc` endpoint, no custom controller needed.
"""
import logging

import requests

_logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 10
SYNC_MODEL = 'account.payment.order.request'


class EnterpriseSyncError(Exception):
    """Any failure talking to the Procesador instance (config/network/auth/API)."""


def _jsonrpc(url, service, method, args):
    if not url:
        raise EnterpriseSyncError('No se configuró la URL de la instalación Procesadora.')
    if not url.lower().startswith('https://'):
        _logger.warning(
            'Sincronización de Solicitudes de Pago usando una URL no-HTTPS (%s); '
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
        raise EnterpriseSyncError(f'No se pudo conectar a la instalación Procesadora: {exc}') from exc
    except ValueError as exc:
        raise EnterpriseSyncError('Respuesta inválida del servidor Procesador.') from exc

    if 'error' in data:
        err = data['error']
        message = (err.get('data') or {}).get('message') or err.get('message') or str(err)
        raise EnterpriseSyncError(message)
    if 'result' not in data:
        raise EnterpriseSyncError(
            'El servidor Procesador no devolvió resultado (¿URL/versión correcta?).')
    return data['result']


def authenticate(url, db, login, api_key):
    uid = _jsonrpc(url, 'common', 'authenticate', [db, login, api_key, {}])
    if not uid:
        raise EnterpriseSyncError(
            'Autenticación rechazada por el Procesador: usuario, base de datos o API Key inválidos.')
    return uid


def check_connection(url, db, login, api_key):
    """Validate credentials against the Procesador without writing any data.

    Returns (uid, server_version_info) on success; raises EnterpriseSyncError on failure.
    """
    if not (url and db and login and api_key):
        raise EnterpriseSyncError(
            'Complete URL, base de datos, usuario y API Key antes de probar la conexión.')
    version_info = _jsonrpc(url, 'common', 'version', [])
    uid = authenticate(url, db, login, api_key)
    return uid, version_info


def create_sync_record(url, db, login, api_key, vals):
    if not (url and db and login and api_key):
        raise EnterpriseSyncError(
            'Sincronización de Solicitudes de Pago incompleta (falta URL, base de datos, '
            'usuario o API Key).')
    uid = authenticate(url, db, login, api_key)
    return _jsonrpc(
        url, 'object', 'execute_kw', [db, uid, api_key, SYNC_MODEL, 'create', [vals]])


def fetch_employees(url, db, login, api_key):
    """Read-only pull of the Enterprise employee directory (name/department/job only).

    Uses the same admin-level credentials already configured for pushing Solicitudes de
    Pago - by explicit decision, no dedicated read-only user/model was added on the
    Enterprise side for this. Deliberately requests only these 3 fields even though the
    connected user can see the full hr.employee record, to keep the payload itself free of
    any sensitive HR data (salary, bank, address, etc.) regardless of what the credentials
    could technically read.
    """
    if not (url and db and login and api_key):
        raise EnterpriseSyncError(
            'Sincronización de Empleados incompleta (falta URL, base de datos, usuario o '
            'API Key).')
    uid = authenticate(url, db, login, api_key)
    return _jsonrpc(
        url, 'object', 'execute_kw',
        [db, uid, api_key, 'hr.employee', 'search_read',
         [[]], {'fields': ['name', 'department_id', 'job_title']}])
