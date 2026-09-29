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
DOCUMENT_MODEL = 'construtec.sat.document'
PARTNER_MODEL = 'res.partner'
INVOICE_MODEL = 'account.move'


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


def fetch_vendor_catalog(url, db, login, api_key):
    """Read-only pull de los proveedores conocidos en Enterprise - derivados de TODOS los
    Documentos SAT recibidos (`construtec.sat.document`, `direction='recibida'`), no solo los
    que ya tienen materiales catalogados (lista deliberadamente más amplia, ver CLAUDE.md).

    No existe ningún modelo/copia local en Enterprise para esto (a diferencia del Catálogo de
    Materiales) - `construtec.sat.document.partner_id` ya es la fuente real, resuelta. Dos
    llamadas, mismo patrón que `fetch_employees()` en `construtec_account_payment_order_19`
    para la cuenta bancaria: (1) `search_read` sobre los documentos para obtener los
    `partner_id` distintos, (2) `read` sobre esos `res.partner` para `name`/`vat`.

    **Requiere que el usuario de integración tenga acceso a `construtec.sat.document`**
    (`account.group_account_invoice` en Enterprise, no `base.group_user`) - a diferencia de
    `fetch_materials_catalog()`, que solo necesita leer un mirror abierto a cualquier usuario.
    Reutiliza las mismas credenciales `materials_catalog_sync_*` (ver res_company.py) - si esas
    credenciales apuntan a un usuario sin ese grupo en Enterprise, esta llamada fallará con un
    error de permisos aunque `fetch_materials_catalog()` siga funcionando con las mismas
    credenciales."""
    if not (url and db and login and api_key):
        raise EnterpriseSyncError(
            'Sincronización de Proveedores incompleta (falta URL, base de datos, usuario o '
            'API Key).')
    uid = authenticate(url, db, login, api_key)
    documentos = _jsonrpc(
        url, 'object', 'execute_kw',
        [db, uid, api_key, DOCUMENT_MODEL, 'search_read',
         [[('direction', '=', 'recibida')]], {'fields': ['partner_id']}])
    partner_ids = sorted({d['partner_id'][0] for d in documentos if d.get('partner_id')})
    if not partner_ids:
        return []
    partners = _jsonrpc(
        url, 'object', 'execute_kw',
        [db, uid, api_key, PARTNER_MODEL, 'read', [partner_ids], {'fields': ['name', 'vat']}])
    return [{'origin_id': p['id'], 'name': p['name'], 'nit': p.get('vat') or False} for p in partners]


def fetch_vendor_invoices(url, db, login, api_key):
    """Read-only pull de los Documentos SAT de proveedor en Enterprise - pendientes o ya
    convertidos a factura - la fuente real para que una Solicitud de Pago tipo Pago Directo,
    creada en Community, pueda vincularse a un Documento SAT real en vez de a un monto capturado
    a mano. Ver construtec_account_payment_order_19, _resolve_factura_origin_ids()/
    _resolve_sat_document_pendiente_ids() (Enterprise, construtec_account_19).

    La fuente de la BÚSQUEDA es `construtec.sat.document` - pedido explícito del usuario:
    "lo que existe es el Documento SAT - el Documento SAT se convierte en una factura de Odoo".
    El saldo pendiente/estado de pago de un documento YA convertido vive de forma nativa en la
    factura, pero se "copia" hacia el Documento SAT vía los campos `related`
    `move_amount_residual`/`move_payment_state` (`construtec_account_19/models/sat_document.py`)
    - se mantienen solos, sin ningún cron ni sincronización propia. Un documento todavía
    Pendiente no tiene ninguna factura de la que copiar nada - su saldo es simplemente
    `monto_total` (nada se ha pagado) y su estado de pago se reporta como `not_paid`.

    Un documento se INCLUYE en el picker si `state in ('pendiente', 'convertido_factura')` - un
    jefe de técnicos puede pedir el pago de un documento todavía pendiente (el Contador lo
    convierte a factura real al Aprobar la Solicitud, ver account_payment_order_sat_document.py).
    Se EXCLUYE del todo (no solo se bloquea al seleccionar - pedido explícito del usuario) si ya
    está `payment_state == 'paid'` (100% pagada), o si su `move_id` no calza con lo esperado
    (`move_type` fuera de in_invoice/in_refund, o no `posted` - un documento convertido pero cuya
    factura sigue en borrador todavía no es pagable).

    `direction='recibida' OR tipo_dte='FESP'` (no solo `direction='recibida'`) - bug real
    encontrado por el usuario probando esto en producción (solo aparecían 13 facturas de las
    muchas que existen): la Factura Especial (FESP) la EMITE la propia Construtec
    (`direction='emitida'` según la SAT - se usa al comprarle a alguien sin capacidad de emitir
    su propia factura), pero económicamente sigue siendo una compra - mismo criterio que ya
    centraliza `construtec.sat.document._sat_es_compra()` en Enterprise
    (`direction == 'recibida' or tipo_dte in TIPOS_DTE_FACTURA_ESPECIAL`, hoy solo `('FESP',)`).
    No se puede llamar ese método Python desde aquí (JSON-RPC, dos procesos separados) - se
    traduce a domain. Si `TIPOS_DTE_FACTURA_ESPECIAL` cambia allá, hay que reflejarlo aquí
    también.

    `partner_name` viene de `partner_id` (no de `nombre_emisor`, el campo CRUDO de "quién emitió
    el DTE" - para una Factura Especial sería la propia Construtec, no el proveedor real).
    `partner_id` en el Documento SAT ya está resuelto correctamente por NIT sin importar la
    dirección ("emisor si es Recibida, receptor si es Emitida") - siempre el contacto real de la
    otra parte. `nit_contacto` (related a `partner_id.vat`, ya `store=True` en el propio
    Documento SAT) evita una tercera llamada solo para el NIT.

    **`origin_id` en el resultado es SIEMPRE el id del `construtec.sat.document` (`doc['id']`),
    nunca el del `account.move`** - decisión explícita del usuario (2026-09-29): "de Enterprise a
    Community solo deben copiarse los documentos SAT". El `move_id` solo se usa AQUÍ, del lado
    Enterprise, para resolver `currency_id`/`amount_residual`/`payment_state`/`linked_order_name`
    de un documento ya convertido - ese id nunca viaja hacia Community ni se guarda en el mirror.
    Community no necesita saber si un Documento SAT ya es factura o no para poder vincularlo -
    Enterprise decide qué hacer según el estado real del documento al recibir la sincronización
    (ver `_resolve_sat_document_ids()`, `account_payment_order_sat_document.py`).

    Dos llamadas: (1) `search_read` sobre `construtec.sat.document` (todo resuelto en un solo
    lugar - incluido `payment_order_id`, el candado propio de un documento aún pendiente), (2)
    `read` sobre `account.move` (por los `move_id` recolectados, solo para los ya convertidos,
    solo para uso interno de esta función) para `currency_id`/`move_type`/`state`/
    `payment_order_id`. Requiere que el usuario de integración tenga acceso a
    `construtec.sat.document`/`account.move` (`account.group_account_invoice` en Enterprise),
    igual que `fetch_vendor_catalog()`."""
    if not (url and db and login and api_key):
        raise EnterpriseSyncError(
            'Sincronización de Facturas de Proveedor incompleta (falta URL, base de datos, '
            'usuario o API Key).')
    uid = authenticate(url, db, login, api_key)
    documentos = _jsonrpc(
        url, 'object', 'execute_kw',
        [db, uid, api_key, DOCUMENT_MODEL, 'search_read',
         [['&', '|', ('direction', '=', 'recibida'), ('tipo_dte', '=', 'FESP'),
           ('state', 'in', ('pendiente', 'convertido_factura'))]],
         {'fields': ['move_id', 'state', 'numero_autorizacion', 'partner_id', 'nit_contacto',
                     'fecha_certificacion', 'monto_total', 'currency_id',
                     'move_amount_residual', 'move_payment_state', 'payment_order_id']}])
    if not documentos:
        return []

    move_ids = sorted({doc['move_id'][0] for doc in documentos if doc.get('move_id')})
    moves_by_id = {}
    if move_ids:
        moves = _jsonrpc(
            url, 'object', 'execute_kw',
            [db, uid, api_key, INVOICE_MODEL, 'read', [move_ids],
             {'fields': ['currency_id', 'move_type', 'state', 'payment_order_id']}])
        moves_by_id = {m['id']: m for m in moves}

    result = []
    for doc in documentos:
        base = {
            'origin_id': doc['id'],
            'numero_autorizacion': doc.get('numero_autorizacion') or False,
            'partner_name': doc['partner_id'][1] if doc.get('partner_id') else False,
            'partner_vat': doc.get('nit_contacto') or False,
            'fecha': doc['fecha_certificacion'][:10] if doc.get('fecha_certificacion') else False,
            'monto_total': doc.get('monto_total') or 0.0,
        }
        if doc['state'] == 'convertido_factura':
            if not doc.get('move_id'):
                continue
            move = moves_by_id.get(doc['move_id'][0]) or {}
            if move.get('move_type') not in ('in_invoice', 'in_refund') or move.get('state') != 'posted':
                continue
            if doc.get('move_payment_state') == 'paid':
                continue
            result.append({
                **base,
                'state': 'convertido_factura',
                'currency_name': move['currency_id'][1] if move.get('currency_id') else False,
                'amount_residual': doc.get('move_amount_residual') or 0.0,
                'payment_state': doc.get('move_payment_state') or False,
                'linked_order_name': (
                    move['payment_order_id'][1] if move.get('payment_order_id') else False),
            })
        else:
            result.append({
                **base,
                'state': 'pendiente',
                'currency_name': doc['currency_id'][1] if doc.get('currency_id') else False,
                'amount_residual': doc.get('monto_total') or 0.0,
                'payment_state': 'not_paid',
                'linked_order_name': (
                    doc['payment_order_id'][1] if doc.get('payment_order_id') else False),
            })
    return result
