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
    # Mismos nombres de campo que PERSONAL_DATA_FIELDS en hr_employee.py (no se importa desde
    # aquí para evitar un import circular tools->models) - se leen también aquí para poder
    # rellenar en Community los que sigan en blanco (ver _sync_employees_from_enterprise(),
    # que solo los usa para completar huecos, nunca para pisar algo que el usuario ya cargó).
    PERSONAL_DATA_READ_FIELDS = [
        'primer_nombre', 'segundo_nombre', 'tercer_nombre', 'primer_apellido', 'segundo_apellido',
        'apellido_casada', 'discapacidad', 'nit', 'igss', 'pueblo_pertenencia', 'comunidad_linguistica',
        'marital', 'sex', 'birthday', 'children', 'identification_id', 'permit_no', 'certificate',
        'study_field', 'country_id', 'country_of_birth', 'municipio_id',
    ]
    # `context: active_test=False` - de lo contrario un empleado dado de baja (archivado,
    # `active=False`) en Enterprise DESAPARECE de este `search_read` en vez de venir con
    # `active: False` - Community nunca se enteraría de que hay que archivarlo también aquí
    # (ver `_sync_employees_from_enterprise()`, que es quien realmente actúa sobre esto).
    employees = _jsonrpc(
        url, 'object', 'execute_kw',
        [db, uid, api_key, 'hr.employee', 'search_read',
         [[]], {'context': {'active_test': False},
                'fields': ['name', 'department_id', 'job_id', 'job_title', 'bank_account_ids', 'active',
                           'work_phone', 'mobile_phone', 'private_phone',
                           'work_email', 'private_email'] + PERSONAL_DATA_READ_FIELDS}])

    bank_ids = sorted({bid for emp in employees for bid in (emp.get('bank_account_ids') or [])})
    banks_by_id = {}
    if bank_ids:
        bank_records = _jsonrpc(
            url, 'object', 'execute_kw',
            [db, uid, api_key, 'res.partner.bank', 'read',
             [bank_ids], {'fields': ['acc_number', 'bank_id', 'tipo_cuenta']}])
        banks_by_id = {b['id']: b for b in bank_records}

    # country_id/country_of_birth/municipio_id vienen como [id, display_name] del `search_read`
    # de arriba - esos ids son de la base de datos de ENTERPRISE, no sirven tal cual en
    # Community (bases distintas). Se resuelven aquí a `code`/`name` (segunda vuelta, mismo
    # patrón que bank_account_ids arriba) para que Community los busque por esos valores, no
    # por id - igual que ya hace `sync_personal_data_from_community()` en la otra dirección.
    country_ids = sorted({
        ref[0] for emp in employees for ref in (emp.get('country_id'), emp.get('country_of_birth')) if ref})
    countries_by_id = {}
    if country_ids:
        country_records = _jsonrpc(
            url, 'object', 'execute_kw',
            [db, uid, api_key, 'res.country', 'read', [country_ids], {'fields': ['code']}])
        countries_by_id = {c['id']: c for c in country_records}

    municipio_ids = sorted({emp['municipio_id'][0] for emp in employees if emp.get('municipio_id')})
    municipios_by_id = {}
    if municipio_ids:
        municipio_records = _jsonrpc(
            url, 'object', 'execute_kw',
            [db, uid, api_key, 'hr.municipio', 'read', [municipio_ids], {'fields': ['name']}])
        municipios_by_id = {m['id']: m for m in municipio_records}

    for emp in employees:
        primary_bank_id = (emp.get('bank_account_ids') or [None])[0]
        bank = banks_by_id.get(primary_bank_id) or {}
        emp['acc_number'] = bank.get('acc_number') or False
        emp['bank_name'] = bank.get('bank_id') and bank['bank_id'][1] or False
        emp['tipo_cuenta'] = bank.get('tipo_cuenta') or False

        country_id = emp.get('country_id')
        emp['nacionalidad_code'] = country_id and countries_by_id.get(country_id[0], {}).get('code') or False
        country_of_birth = emp.get('country_of_birth')
        emp['pais_origen_code'] = (
            country_of_birth and countries_by_id.get(country_of_birth[0], {}).get('code') or False)
        municipio_id = emp.get('municipio_id')
        emp['municipio_nombre'] = municipio_id and municipios_by_id.get(municipio_id[0], {}).get('name') or False
    return employees


def fetch_analytic_accounts(url, db, login, api_key):
    """Read-only pull of the Enterprise analytic account catalog (used as "Proyecto" en
    Solicitudes de Pago, y como "Cuenta Analítica" en Tickets de Helpdesk). `plan_id` viene
    como [id, display_name] - solo el nombre viaja al mirror (mismo criterio "nunca ids entre
    bases independientes" de todo este módulo). `partner_id` viaja como el id REAL en
    Enterprise (no el nombre) - a diferencia de `plan_id`, este SÍ se resuelve por id del
    otro lado, igual que `employee_enterprise_ref`/`analytic_enterprise_ref`, porque ya existe
    `res.partner.enterprise_partner_ref` (ver `_sync_partners_from_enterprise()`) capaz de
    resolverlo a un contacto real de Community."""
    if not (url and db and login and api_key):
        raise EnterpriseSyncError(
            'Sincronización de Cuentas Analíticas incompleta (falta URL, base de datos, '
            'usuario o API Key).')
    uid = authenticate(url, db, login, api_key)
    return _jsonrpc(
        url, 'object', 'execute_kw',
        [db, uid, api_key, 'account.analytic.account', 'search_read',
         [[]], {'fields': ['name', 'code', 'plan_id', 'partner_id', 'disponible_tickets']}])


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
         {'fields': ['external_ref', 'state', 'monto', 'reject_reason', 'approve_date', 'reject_date']}])


def fetch_partners(url, db, login, api_key):
    """Read-only pull de los contactos que ya son Clientes o Proveedores reales en Enterprise -
    deliberadamente NO todos los `res.partner` (decisión explícita del usuario, ver el plan de
    esta feature).

    **Proveedor se define por tener al menos un Documento SAT de compra** (`construtec.sat.
    document`, `direction='recibida'` o `tipo_dte='FESP'` - mismo criterio que `_sat_es_compra()`
    en Enterprise), NO por `supplier_rank > 0` - corrección explícita del usuario (2026-09-29):
    "deben ser contactos con al menos un documento SAT, para ser proveedores". `supplier_rank`
    puede subir por motivos que no son un Documento SAT real (ej. una factura de proveedor
    capturada a mano) y ya no se usa para esta calificación. **Cliente sigue usando
    `customer_rank > 0`** sin cambios - el usuario solo corrigió el lado de Proveedores.

    Dos llamadas: (1) `search_read` sobre `construtec.sat.document` para los `partner_id`
    distintos que califican como compra, (2) `search_read` sobre `res.partner` con el domain
    combinado (`customer_rank > 0` OR id en esa lista). `es_proveedor_sat` (Boolean, calculado
    aquí mismo) viaja en el resultado en vez de `supplier_rank` - `_construtec_tag_names_for()`
    (Community) lo usa directo para la etiqueta "Proveedores".

    Deliberadamente NO se pide `category_id` aquí - las etiquetas Empleados/Proveedores/
    Clientes las deriva Community por su cuenta (`_construtec_tag_names_for()`), nunca copiando
    las etiquetas reales de Enterprise (que podrían incluir "Empleados" u otras ajenas a este
    mecanismo). Requiere que el usuario de integración tenga acceso a `construtec.sat.document`
    (`account.group_account_invoice` en Enterprise) - mismas credenciales ya usadas por
    `fetch_vendor_catalog()`/`fetch_vendor_invoices()` en `construtec_sat_catalog_sync_19`."""
    if not (url and db and login and api_key):
        raise EnterpriseSyncError(
            'Sincronización de Contactos incompleta (falta URL, base de datos, usuario o '
            'API Key).')
    uid = authenticate(url, db, login, api_key)
    documentos = _jsonrpc(
        url, 'object', 'execute_kw',
        [db, uid, api_key, 'construtec.sat.document', 'search_read',
         [['|', ('direction', '=', 'recibida'), ('tipo_dte', '=', 'FESP')]],
         {'fields': ['partner_id']}])
    proveedor_ids = {d['partner_id'][0] for d in documentos if d.get('partner_id')}
    partners = _jsonrpc(
        url, 'object', 'execute_kw',
        [db, uid, api_key, 'res.partner', 'search_read',
         [['|', ('customer_rank', '>', 0), ('id', 'in', sorted(proveedor_ids))]],
         {'fields': ['name', 'email', 'phone', 'vat', 'street', 'city',
                     'is_company', 'customer_rank']}])
    for p in partners:
        p['es_proveedor_sat'] = p['id'] in proveedor_ids
    return partners


def push_employee_personal_data(url, db, login, api_key, enterprise_employee_ref, vals):
    """Empuja "datos personales" del empleado (nombres/apellidos, DPI, NIT, IGSS, estado civil,
    etc. - ver `PERSONAL_DATA_FIELDS` en el `hr_employee.py` de Enterprise) hacia el `hr.employee`
    REAL en Enterprise, identificado por `enterprise_employee_ref` - a diferencia del resto de
    este módulo (que siempre CREA un registro nuevo del otro lado), aquí se actualiza un
    registro YA EXISTENTE, porque Community es la fuente para este subconjunto de campos
    mientras Enterprise sigue siendo dueño del resto (salario, banco, estado laboral).

    Llama a un método whitelisted (`sync_personal_data_from_community`), nunca `write()`
    directo - ese método filtra `vals` contra su propia lista blanca de campos permitidos, así
    que una fuga de esta API Key nunca puede escribir salario/banco/estado laboral, solo lo que
    ese método decide aceptar."""
    if not (url and db and login and api_key):
        raise EnterpriseSyncError(
            'Sincronización de Datos Personales incompleta (falta URL, base de datos, usuario '
            'o API Key).')
    if not enterprise_employee_ref:
        raise EnterpriseSyncError(
            'Este empleado todavía no tiene una referencia de Enterprise (enterprise_employee_ref) '
            '- no se puede sincronizar hasta que el directorio de empleados se sincronice primero.')
    uid = authenticate(url, db, login, api_key)
    return _jsonrpc(
        url, 'object', 'execute_kw',
        [db, uid, api_key, 'hr.employee', 'sync_personal_data_from_community',
         [[int(enterprise_employee_ref)], vals]])


def create_employee_in_enterprise(url, db, login, api_key, vals):
    """Crea un `hr.employee` NUEVO en Enterprise a partir de un alta hecha en Community -
    decisión explícita del usuario 2026-09-18: la puerta de entrada para dar de alta
    colaboradores puede ser Community (persona con `group_construtec_employee_data_entry`,
    sin cuenta/privilegios de nómina en Enterprise), no solo Enterprise.

    A diferencia de `push_employee_personal_data()`, aquí no hay ningún id existente que
    resolver - se llama al método whitelisted `create_employee_from_community` con una lista
    de ids VACÍA (`[[], vals]`), que internamente hace `.sudo().create(...)` y devuelve el id
    del empleado recién creado - Community lo guarda como `enterprise_employee_ref` y desde
    ahí en adelante este empleado se sincroniza igual que cualquier otro (ver
    `push_employee_personal_data()` para ediciones futuras). Mismo criterio de lista blanca
    (`PERSONAL_DATA_FIELDS`) del lado de Enterprise - una fuga de esta API Key no puede crear
    un empleado con campos fuera de esa lista."""
    if not (url and db and login and api_key):
        raise EnterpriseSyncError(
            'Sincronización de Empleados incompleta (falta URL, base de datos, usuario o '
            'API Key).')
    uid = authenticate(url, db, login, api_key)
    return _jsonrpc(
        url, 'object', 'execute_kw',
        [db, uid, api_key, 'hr.employee', 'create_employee_from_community', [[], vals]])


def create_partner_in_enterprise(url, db, login, api_key, vals):
    """Crea un `res.partner` NUEVO en Enterprise a partir de un contacto creado en Community
    (ej. "Crear Contacto" desde una conversación de WhatsApp del Contact Center, ver
    `res_partner.py::_push_new_partner_to_enterprise()`).

    Mismo patrón que `create_employee_in_enterprise()`: sin ningún id existente que resolver,
    se llama al método whitelisted `create_partner_from_community` con una lista de ids VACÍA
    (`[[], vals]`) - internamente hace `.sudo().create(...)` (con su propia lista blanca de
    campos aceptados) y devuelve el id del contacto recién creado. Community lo guarda como
    `enterprise_partner_ref`."""
    if not (url and db and login and api_key):
        raise EnterpriseSyncError(
            'Sincronización de Contactos incompleta (falta URL, base de datos, usuario o '
            'API Key).')
    uid = authenticate(url, db, login, api_key)
    return _jsonrpc(
        url, 'object', 'execute_kw',
        [db, uid, api_key, 'res.partner', 'create_partner_from_community', [[], vals]])


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
