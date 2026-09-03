"""Thin JSON-RPC client for pushing Órdenes de Pago (tipo Anticipo) to a Procesador instance.

Deliberate small copy of construtec_materials_19/tools/enterprise_sync_api.py (Odoo19C),
not a shared library: this lets each integration (Materiales, Órdenes de Pago) use its
own URL/credentials and be revoked independently, without coupling this module to another
one just to reuse ~90 lines. The receiving side is just this same module's own
`account.payment.order` model (fused with the former `account.payment.order.request` -
see CLAUDE.md), installed on the Procesador instance - reached through Odoo's own
built-in `/jsonrpc` endpoint, no custom controller needed.
"""
import logging

import requests

_logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 10
SYNC_MODEL = 'account.payment.order'


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
    """Read-only pull of the Enterprise employee directory: name/department/job plus each
    employee's own primary bank account (number + bank name + tipo_cuenta, Ahorro/Monetaria,
    see res_partner_bank.py).

    Uses the same admin-level credentials already configured for pushing Solicitudes de
    Pago - by explicit decision, no dedicated read-only user/model was added on the
    Enterprise side for this, and the user explicitly chose to include bank account data in
    this same batch pull (accepting that risk) rather than a narrower per-user live fetch.
    The resulting sensitivity is contained entirely on the Community side: the receiving
    `hr.employee.cuenta_bancaria_raw`/`banco_nombre_raw` fields are `groups='hr.group_hr_manager'`
    (invisible to a plain internal user via any read path), and the only way a regular user
    ever sees a real value is through `cuenta_bancaria`/`banco_nombre` compute fields that
    explicitly only resolve for the employee's own linked user - see
    `construtec_account_payment_order_19/models/hr_employee.py`.

    Bank data needs a second round-trip: `search_read` only returns Many2many fields as a
    plain list of ids, not their sub-fields, so `bank_account_ids` (res.partner.bank ids) are
    collected here and read again for `acc_number`/`bank_id`.
    """
    if not (url and db and login and api_key):
        raise EnterpriseSyncError(
            'Sincronización de Empleados incompleta (falta URL, base de datos, usuario o '
            'API Key).')
    uid = authenticate(url, db, login, api_key)
    employees = _jsonrpc(
        url, 'object', 'execute_kw',
        [db, uid, api_key, 'hr.employee', 'search_read',
         [[]], {'fields': ['name', 'department_id', 'job_title', 'bank_account_ids',
                            'work_phone', 'mobile_phone', 'private_phone',
                            'work_email', 'private_email']}])

    bank_ids = sorted({bid for emp in employees for bid in (emp.get('bank_account_ids') or [])})
    banks_by_id = {}
    if bank_ids:
        bank_records = _jsonrpc(
            url, 'object', 'execute_kw',
            [db, uid, api_key, 'res.partner.bank', 'read',
             [bank_ids], {'fields': ['acc_number', 'bank_id', 'tipo_cuenta']}])
        banks_by_id = {b['id']: b for b in bank_records}

    for emp in employees:
        primary_bank_id = (emp.get('bank_account_ids') or [None])[0]
        bank = banks_by_id.get(primary_bank_id) or {}
        emp['acc_number'] = bank.get('acc_number') or False
        emp['bank_name'] = bank.get('bank_id') and bank['bank_id'][1] or False
        emp['tipo_cuenta'] = bank.get('tipo_cuenta') or False
    return employees


def fetch_analytic_accounts(url, db, login, api_key):
    """Read-only pull of the Enterprise analytic account catalog (used as "Proyecto" in
    Solicitudes de Pago). `plan_id` comes back as [id, display_name] - only the name travels
    onward when mirroring, same "no ids across independent databases" rule as everywhere else
    in this module."""
    if not (url and db and login and api_key):
        raise EnterpriseSyncError(
            'Sincronización de Cuentas Analíticas incompleta (falta URL, base de datos, '
            'usuario o API Key).')
    uid = authenticate(url, db, login, api_key)
    return _jsonrpc(
        url, 'object', 'execute_kw',
        [db, uid, api_key, 'account.analytic.account', 'search_read',
         [[]], {'fields': ['name', 'code', 'plan_id']}])


def fetch_order_status(url, db, login, api_key, external_refs):
    """Read-only pull del estado real de Órdenes de Pago ya enviadas por esta instalación -
    buscadas por `external_ref` (el `name` original en la instalación Solicitante, guardado del
    otro lado por `_prepare_sync_vals()`), nunca por id (bases de datos distintas). Sin esto, el
    registro original en la instalación Solicitante se queda congelado en 'enviado' para
    siempre, sin enterarse si la Procesadora lo aprobó/rechazó/aplicó - `_sync_to_enterprise()`
    solo empuja en un sentido (crea un registro NUEVO allá), nunca trae nada de vuelta.

    Usa las MISMAS credenciales que `create_sync_record()` - el usuario de integración
    (`group_payment_order_sync_integration`) ya tiene permiso de lectura sobre este modelo
    (lo necesitan sus propios `@api.constrains` al validar un `create()`, ej.
    `_check_journal_id`), así que no hace falta un usuario/grupo aparte para esto."""
    if not (url and db and login and api_key):
        raise EnterpriseSyncError(
            'Sincronización de estado de Órdenes de Pago incompleta (falta URL, base de datos, '
            'usuario o API Key).')
    if not external_refs:
        return []
    uid = authenticate(url, db, login, api_key)
    return _jsonrpc(
        url, 'object', 'execute_kw',
        [db, uid, api_key, SYNC_MODEL, 'search_read',
         [[('external_ref', 'in', list(external_refs))]],
         {'fields': ['external_ref', 'state', 'reject_reason', 'approve_date', 'reject_date']}])


def fetch_partners(url, db, login, api_key):
    """Read-only pull de los contactos que ya son Clientes o Proveedores reales en Enterprise
    (`customer_rank > 0` o `supplier_rank > 0`, campos nativos de `account`) - deliberadamente
    NO todos los `res.partner` (decisión explícita del usuario, ver el plan de esta feature).
    Deliberadamente NO se pide `category_id` aquí - las etiquetas Empleados/Proveedores/
    Clientes las deriva Community por su cuenta desde `customer_rank`/`supplier_rank`
    (`_construtec_tag_names_for()`), nunca copiando las etiquetas reales de Enterprise (que
    podrían incluir "Empleados" u otras ajenas a este mecanismo)."""
    if not (url and db and login and api_key):
        raise EnterpriseSyncError(
            'Sincronización de Contactos incompleta (falta URL, base de datos, usuario o '
            'API Key).')
    uid = authenticate(url, db, login, api_key)
    return _jsonrpc(
        url, 'object', 'execute_kw',
        [db, uid, api_key, 'res.partner', 'search_read',
         [['|', ('customer_rank', '>', 0), ('supplier_rank', '>', 0)]],
         {'fields': ['name', 'email', 'phone', 'vat', 'street', 'city',
                     'is_company', 'customer_rank', 'supplier_rank']}])


def fetch_companies(url, db, login, api_key):
    """Read-only pull of the Enterprise company list - usado para el desplegable "Compañía por
    defecto" (`res.company.payment_order_default_company_id`), el respaldo cuando el empleado
    de una Solicitud no se puede resolver por `enterprise_employee_ref` (ej. no sincronizado
    todavía). No hay nada sensible en `name`, se pide sin restricción."""
    if not (url and db and login and api_key):
        raise EnterpriseSyncError(
            'Sincronización de Compañías incompleta (falta URL, base de datos, usuario o '
            'API Key).')
    uid = authenticate(url, db, login, api_key)
    return _jsonrpc(
        url, 'object', 'execute_kw',
        [db, uid, api_key, 'res.company', 'search_read', [[]], {'fields': ['name']}])
