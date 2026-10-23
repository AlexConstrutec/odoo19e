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
from datetime import datetime, timedelta

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


def fetch_sat_document_status(url, db, login, api_key, extra_ids=()):
    """Estado de pago de los Documentos SAT de compra (2026-10-23, unificación: antes lo traía
    `fetch_vendor_invoices()` hacia un segundo modelo, `construtec.sat.invoice.mirror`, que
    duplicaba los mismos documentos - ahora todo vive en la réplica `construtec.sat.document`).

    Devuelve {id del Documento SAT en Enterprise: vals} para:
    - todo documento de compra que todavía se puede pedir a pagar (`state` pendiente o
      convertido_factura), sin importar cuándo se modificó - el saldo de la factura cambia sin que
      cambie el documento, así que la ventana de días no sirve para esto;
    - `extra_ids`: documentos que Community tenía como disponibles y ya no aparecen arriba (se
      pagaron, se convirtieron a Orden de Compra...), para apagarlos.

    vals: `state`, `move_amount_residual` (para un pendiente, `monto_total`: nada se ha pagado),
    `move_payment_state` (`not_paid` si pendiente), `linked_order_name` (el `name` de la
    requisición que lo tiene tomado, nunca un id) y `disponible_pago`. Un documento convertido
    solo es pagable si su factura es de proveedor, está publicada y no está pagada. El `move_id`
    solo se usa aquí, del lado Enterprise - nunca viaja a Community."""
    if not (url and db and login and api_key):
        raise EnterpriseSyncError(
            'Sincronización de Documentos SAT incompleta (falta URL, base de datos, usuario o '
            'API Key).')
    uid = authenticate(url, db, login, api_key)
    domain = ['&', '|', ('direction', '=', 'recibida'), ('tipo_dte', '=', 'FESP'),
              ('state', 'in', ('pendiente', 'convertido_factura'))]
    extra_ids = sorted({int(i) for i in extra_ids if i})
    if extra_ids:
        domain = ['|', ('id', 'in', extra_ids)] + domain
    documentos = _jsonrpc(
        url, 'object', 'execute_kw',
        [db, uid, api_key, DOCUMENT_MODEL, 'search_read', [domain],
         {'fields': ['move_id', 'state', 'monto_total', 'move_amount_residual',
                     'move_payment_state', 'payment_order_id']}])
    move_ids = sorted({doc['move_id'][0] for doc in documentos if doc.get('move_id')})
    moves_by_id = {}
    if move_ids:
        moves = _jsonrpc(
            url, 'object', 'execute_kw',
            [db, uid, api_key, INVOICE_MODEL, 'read', [move_ids],
             {'fields': ['move_type', 'state', 'payment_order_id']}])
        moves_by_id = {m['id']: m for m in moves}

    result = {}
    for doc in documentos:
        state = doc.get('state')
        if state == 'pendiente':
            result[doc['id']] = {
                'state': state,
                'move_amount_residual': doc.get('monto_total') or 0.0,
                'move_payment_state': 'not_paid',
                'linked_order_name': (
                    doc['payment_order_id'][1] if doc.get('payment_order_id') else False),
                'disponible_pago': True,
            }
            continue
        move = moves_by_id.get(doc['move_id'][0]) if doc.get('move_id') else {}
        move = move or {}
        pagable = (state == 'convertido_factura'
                   and move.get('move_type') in ('in_invoice', 'in_refund')
                   and move.get('state') == 'posted'
                   and doc.get('move_payment_state') != 'paid')
        result[doc['id']] = {
            'state': state,
            'move_amount_residual': doc.get('move_amount_residual') or 0.0,
            'move_payment_state': doc.get('move_payment_state') or False,
            'linked_order_name': (
                move['payment_order_id'][1] if move.get('payment_order_id') else False),
            'disponible_pago': pagable,
        }
    return result


# Campos de construtec.sat.document (Enterprise) que se copian TAL CUAL (mismo nombre) hacia el
# Documento SAT réplica de Community - todos escalares, sin necesitar ninguna resolución de
# relación. Deliberadamente excluidos: adjuntos (xml/pdf), cuenta_analitica_id/cuenta_contable_id,
# line_ids, y cualquier id de account.move/purchase.order/sale.order (nunca cruzan a Community,
# ver construtec_account_payment_order_19/CLAUDE.md "Community nunca vuelve a conocer ningún id
# de account.move").
_SAT_DOCUMENT_PLAIN_FIELDS = [
    'direction', 'numero_autorizacion', 'tipo_dte', 'tipo_compra',
    'numero_autorizacion_referencia', 'motivo_ajuste_nota', 'serie', 'numero_documento',
    'fecha_certificacion', 'fecha_vencimiento', 'nit_emisor', 'nombre_emisor', 'nit_receptor',
    'nombre_receptor', 'nit_contacto', 'moneda_codigo', 'monto_total', 'monto_iva',
    'monto_petroleo', 'monto_turismo_hospedaje', 'monto_turismo_pasajes', 'monto_timbre_prensa',
    'monto_bomberos', 'monto_tasa_municipal', 'monto_bebidas_alcoholicas', 'monto_tabaco',
    'monto_cemento', 'monto_bebidas_no_alcoholicas', 'monto_tarifa_portuaria',
    'monto_retencion_isr_fesp', 'monto_retencion_iva_fesp', 'monto_neto_pagado_fesp',
    'codigo_establecimiento', 'nombre_establecimiento', 'nombre_comercial_emisor',
    'direccion_emisor', 'nit_certificador', 'nombre_certificador', 'clasificacion_emisor',
    'exportacion', 'estado_sat', 'anulado', 'fecha_anulacion', 'state', 'move_amount_residual',
    'move_payment_state',
]


def fetch_sat_documents(url, db, login, api_key, since_days=7, ids=None):
    """Read-only pull de una réplica CASI completa de `construtec.sat.document` (Enterprise) -
    mismo `_name`/mismos campos del lado Community (`construtec_sat_catalog_sync_19.models.
    sat_document`) - pedido explícito del usuario (2026-09-29): "el modelo Documento SAT de
    Enterprise, replícalo tal cual en Community... que tenga los mismos campos".

    Solo documentos de compra (`direction='recibida'` o `tipo_dte='FESP'`, mismo criterio que
    `_sat_es_compra()` en Enterprise) creados O modificados en los últimos `since_days` días
    (`write_date >= cutoff OR create_date >= cutoff`) - NO se vuelve a traer el histórico
    completo en cada corrida (podrían ser miles de documentos); corridas sucesivas (cron/botón)
    van completando el histórico real solas, mientras cada corrida individual se queda rápida.
    `origin_id` (el `id` real en Enterprise) es la clave de upsert - un documento que ya se trajo
    antes y no ha vuelto a cambiar simplemente no vuelve a aparecer en corridas siguientes, sin
    que eso signifique que "desapareció" del lado Community.

    La mayoría de los campos viajan TAL CUAL (mismo nombre, mismo valor escalar) - solo
    `partner_id`/`currency_id` (Many2one en Enterprise) se resuelven aquí a texto plano
    (`partner_name`/`currency_name`), mismo criterio que el resto de los mirrors de este módulo
    (un id de Enterprise no significa nada en Community)."""
    if not (url and db and login and api_key):
        raise EnterpriseSyncError(
            'Sincronización de Documentos SAT incompleta (falta URL, base de datos, usuario o '
            'API Key).')
    uid = authenticate(url, db, login, api_key)
    if ids is not None:
        # Documentos puntuales (2026-10-23): los que Community todavía no tiene completos.
        if not ids:
            return []
        domain = [('id', 'in', sorted({int(i) for i in ids}))]
    else:
        cutoff = (datetime.now() - timedelta(days=since_days)).strftime('%Y-%m-%d %H:%M:%S')
        domain = ['&', '|', ('direction', '=', 'recibida'), ('tipo_dte', '=', 'FESP'),
                  '|', ('write_date', '>=', cutoff), ('create_date', '>=', cutoff)]
    documentos = _jsonrpc(
        url, 'object', 'execute_kw',
        [db, uid, api_key, DOCUMENT_MODEL, 'search_read',
         [domain],
         {'fields': _SAT_DOCUMENT_PLAIN_FIELDS + ['id', 'partner_id', 'currency_id', 'write_date']}])
    result = []
    for doc in documentos:
        vals = {field: doc.get(field) for field in _SAT_DOCUMENT_PLAIN_FIELDS}
        vals.update({
            'origin_id': doc['id'],
            'partner_name': doc['partner_id'][1] if doc.get('partner_id') else False,
            'currency_name': doc['currency_id'][1] if doc.get('currency_id') else False,
            'enterprise_write_date': doc.get('write_date') or False,
        })
        result.append(vals)
    return result
