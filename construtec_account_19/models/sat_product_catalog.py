import logging
import re

from odoo import api, fields, models

from .sat_document import BIEN_O_SERVICIO_SELECTION

_logger = logging.getLogger(__name__)

# Extracción del "código de producto" a partir del nombre/descripción del DTE -
# la SAT no manda un código de producto separado, así que si el proveedor pone
# uno, va mezclado en el mismo texto de la descripción, en una de tres formas
# (confirmado contra nombres reales de este catálogo): entre corchetes
# ("[C2X-2] COMBO 2 CAMARAS..."), antes de una barra vertical
# ("8471.30.00 | LAPTOP DELL..."), o como una secuencia de dígitos al inicio
# seguida de espacio ("784512 CABLE UTP CAT6..."). Se prueban en ese orden -
# corchetes primero por ser la marca más explícita - y si ninguna aplica se
# deja vacío en vez de adivinar (mismo criterio que _fix_mangled_accents en
# sat_document_import.py: mejor vacío que un dato incorrecto).
_CODIGO_BRACKET_RE = re.compile(r'\[([^\[\]]+)\]')
_CODIGO_NUMERIC_PREFIX_RE = re.compile(r'^\s*(\d{4,}(?:[.\-]\d+)*)\s+\S')


def _sat_extract_codigo(name):
    if not name:
        return False

    match = _CODIGO_BRACKET_RE.search(name)
    if match:
        codigo = match.group(1).strip()
        if codigo:
            return codigo

    if '|' in name:
        codigo = name.split('|', 1)[0].strip()
        if codigo:
            return codigo

    match = _CODIGO_NUMERIC_PREFIX_RE.match(name)
    if match:
        return match.group(1)

    return False

class ConstructecSatProductCatalog(models.Model):
    _name = 'construtec.sat.product.catalog'
    _description = 'Catálogo de Productos de Proveedor (referencia de precio, sin crear product.product)'
    _order = 'ultima_fecha_compra desc'

    name = fields.Char(string='Producto', required=True)
    codigo = fields.Char(
        string='Código de Producto',
        help='Extraído automáticamente del nombre al crearse la entrada (entre corchetes, antes '
             'de una barra vertical "|", o una secuencia de dígitos al inicio) - vacío si el '
             'proveedor no incluyó ningún código reconocible. Editable a mano; no se vuelve a '
             'recalcular sobre un valor ya puesto, salvo con la acción "Extraer Código de '
             'Producto" (ver CLAUDE.md).')
    name_normalized = fields.Char(
        compute='_compute_name_normalized', store=True, index=True,
        help='Nombre en mayúsculas/sin espacios sobrantes, usado solo para detectar duplicados '
             'al reimportar (no se muestra al usuario).')
    partner_id = fields.Many2one('res.partner', string='Proveedor', required=True)
    bien_o_servicio = fields.Selection(
        BIEN_O_SERVICIO_SELECTION, string='Bien/Servicio',
        help='Copiado de `construtec.sat.document.line.bien_o_servicio` (dato real del propio '
             'DTE) al crearse la entrada - nunca recalculado después. Viaja tal cual hacia el '
             'Catálogo de Materiales (bienes Y servicios, sin filtro aquí) - el filtro real vive '
             'en cada consumidor (ej. la Solicitud de Materiales solo usa "Bien"), ver CLAUDE.md.')
    uom_id = fields.Many2one(
        'uom.uom', string='Unidad de Medida',
        help='La SAT no envía unidad de medida en el DTE - este campo queda vacío al crearse '
             'automáticamente y se completa a mano si un técnico la conoce.')
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True, default=lambda self: self.env.company.id)
    currency_id = fields.Many2one(
        'res.currency', string='Moneda', default=lambda self: self.env.company.currency_id.id)
    precio_referencia = fields.Monetary(
        string='Precio de Referencia', currency_field='currency_id',
        help='Precio unitario tomado del documento SAT más reciente de este proveedor para este '
             'producto - una referencia para los técnicos, no un precio de lista ni de compra '
             'vigente garantizado.')
    primera_fecha_compra = fields.Date(string='Primera Compra', readonly=True)
    ultima_fecha_compra = fields.Date(string='Última Compra', readonly=True)
    sync_state = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('sincronizado', 'Sincronizado'),
        ('error', 'Error'),
    ], string='Estado de Sincronización', default='pendiente', copy=False, required=True,
        help='Refleja solo la copia LOCAL de Enterprise en el Catálogo de Materiales '
             '(`construtec.materials.catalog.mirror`) - se registra TODA entrada (bien o '
             'servicio), ver `bien_o_servicio` para el dato que cada consumidor usa para '
             'filtrar según lo que necesite. Community ya no recibe esto por push - jala su '
             'propia copia directamente de este modelo (ver CLAUDE.md).')
    sync_error = fields.Text(string='Detalle del Error', readonly=True, copy=False)
    sync_date = fields.Datetime(string='Última Sincronización Exitosa', readonly=True, copy=False)

    _name_normalized_uniq = models.Constraint(
        'unique(company_id, partner_id, name_normalized)',
        'Ya existe un producto de este proveedor con ese mismo nombre en el catálogo.',
    )

    @api.depends('name')
    def _compute_name_normalized(self):
        for record in self:
            record.name_normalized = (record.name or '').strip().upper()

    @api.model
    def _sat_register_from_line(self, document, line):
        """Registra o actualiza una entrada del catálogo a partir de una línea de un
        documento SAT ya creado - ver CLAUDE.md, sección "Catálogo de Productos de
        Proveedor". Deliberadamente NO crea product.product: esto es solo una
        referencia de precio para los técnicos (a nivel contable no aporta, son
        demasiados productos de demasiados proveedores para mantener como
        maestro real). Solo aplica a documentos RECIBIDOS (compras) - un
        documento emitido no tiene "proveedor".

        Idempotente por (company_id, partner_id, nombre normalizado): reimportar
        el mismo rango de fechas actualiza la entrada existente en vez de
        duplicarla. `primera_fecha_compra`/`ultima_fecha_compra` se ajustan por
        fecha real del documento, no por orden de importación - así un backfill
        de documentos antiguos después de haber importado los recientes no
        pisa `ultima_fecha_compra` con una fecha vieja, ni dos importaciones
        del mismo rango generan un "cambio" que dispare una sincronización de
        más hacia Community.
        """
        if document.direction != 'recibida' or not document.partner_id or not line.descripcion:
            return self.browse()

        nombre = line.descripcion.strip()
        name_normalized = nombre.upper()
        if not name_normalized:
            return self.browse()

        fecha = document.fecha_certificacion and document.fecha_certificacion.date()
        entry = self.search([
            ('company_id', '=', document.company_id.id),
            ('partner_id', '=', document.partner_id.id),
            ('name_normalized', '=', name_normalized),
        ], limit=1)

        cambio = False
        if not entry:
            entry = self.create({
                'name': nombre,
                'codigo': _sat_extract_codigo(nombre),
                'partner_id': document.partner_id.id,
                'company_id': document.company_id.id,
                'currency_id': document.currency_id.id,
                'precio_referencia': line.precio_unitario,
                'primera_fecha_compra': fecha,
                'ultima_fecha_compra': fecha,
                'bien_o_servicio': line.bien_o_servicio or False,
            })
            cambio = True
        elif fecha:
            vals = {}
            if not entry.primera_fecha_compra or fecha < entry.primera_fecha_compra:
                vals['primera_fecha_compra'] = fecha
            if not entry.ultima_fecha_compra or fecha >= entry.ultima_fecha_compra:
                vals['ultima_fecha_compra'] = fecha
                vals['precio_referencia'] = line.precio_unitario
            if vals:
                entry.write(vals)
                cambio = True

        if cambio:
            entry._sat_sync_local_mirror()
        return entry

    def _sat_prepare_materials_catalog_vals(self):
        """Payload que arma sync_from_enterprise() para la copia LOCAL de Enterprise. Un solo
        lugar para el contrato, ver CLAUDE.md. Community ya no recibe este payload por push -
        jala directamente este mismo modelo (`construtec.materials.catalog.mirror`) vía su
        propio pull (`construtec_sat_catalog_sync_19`, lado Community)."""
        self.ensure_one()
        return {
            'origin_id': self.id,
            'name': self.name,
            'codigo': self.codigo or False,
            'partner_name': self.partner_id.display_name,
            'partner_vat': self.partner_id.vat or False,
            'uom_name': self.uom_id.display_name if self.uom_id else False,
            'currency_name': self.currency_id.name,
            'precio_referencia': self.precio_referencia,
            'primera_fecha_compra': self.primera_fecha_compra.isoformat() if self.primera_fecha_compra else False,
            'ultima_fecha_compra': self.ultima_fecha_compra.isoformat() if self.ultima_fecha_compra else False,
            'company_id': self.company_id.id,
            'bien_o_servicio': self.bien_o_servicio or False,
        }

    def _sat_sync_local_mirror(self):
        """Registra/actualiza esta entrada en la copia LOCAL de Enterprise del Catálogo de
        Materiales (`construtec.materials.catalog.mirror`, módulo construtec_sat_catalog_sync_19)
        - llamada ORM directa, sin red, sin filtrar por `bien_o_servicio` aquí: se registra TODO
        (bienes y servicios), el campo viaja en el payload para que cada consumidor filtre según
        lo que necesite (ver CLAUDE.md).

        **Ya NO empuja hacia Community por XML-RPC** - antes de 2026-09-01 este método también
        intentaba una copia remota vía XML-RPC; se retiró a pedido explícito del usuario, que
        prefirió el mismo patrón "pull" ya usado para empleados/cuentas analíticas
        (`construtec_account_payment_order_19`): ahora Community jala directamente este mismo
        modelo (`construtec.materials.catalog.mirror`) por su cuenta, vía un pull propio en
        `construtec_sat_catalog_sync_19` (lado Community) - ver el CLAUDE.md de ese módulo.

        Nunca lanza excepción hacia el llamador: un fallo real de escritura local se registra en
        sync_state/sync_error para revisión y reintento posterior - no debe impedir que el
        documento SAT/factura que sí importa contablemente se guarde en Enterprise.

        sudo() deliberado aquí, en el llamador de confianza (vals ya construido por este mismo
        método, no input externo) - sync_from_enterprise() en sí sigue sin sudo() a propósito,
        para que la vía RPC (el pull de Community) siga dependiendo por completo del ACL del
        usuario de integración real. Ver el CLAUDE.md de construtec_sat_catalog_sync_19.
        """
        self.ensure_one()
        vals = self._sat_prepare_materials_catalog_vals()
        try:
            self.env['construtec.materials.catalog.mirror'].sudo().sync_from_enterprise(vals)
        except Exception as exc:
            _logger.warning(
                'No se pudo actualizar el Catálogo de Materiales local para #%s ("%s"): %s',
                self.id, self.name, exc)
            self.write({'sync_state': 'error', 'sync_error': str(exc)})
            return

        self.write({'sync_state': 'sincronizado', 'sync_error': False, 'sync_date': fields.Datetime.now()})

    @api.model
    def action_extraer_codigo(self):
        """Backfill de `codigo` (ver _sat_extract_codigo) para entradas creadas antes
        de que este campo existiera. Solo toca entradas con codigo vacío - nunca
        pisa uno ya puesto (automático o corregido a mano). No sincroniza con
        Community por sí sola: si alguna entrada estaba pendiente/con error de
        sincronización, el próximo reintento (botón, acción masiva o el cron)
        ya manda el código actualizado junto con el resto de campos."""
        entradas = self.search([('codigo', '=', False)])
        actualizadas = 0
        for entry in entradas:
            codigo = _sat_extract_codigo(entry.name)
            if codigo:
                entry.codigo = codigo
                actualizadas += 1
        mensaje = f"Código extraído en {actualizadas} de {len(entradas)} entradas sin código."
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Extracción de Código de Producto',
                'message': mensaje,
                'sticky': False,
                'type': 'success',
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def action_retry_sync(self):
        for entry in self:
            entry._sat_sync_local_mirror()
        # Sin esto, el formulario abierto se queda mostrando sync_state/sync_error
        # viejos (ej. "error") aunque el reintento sí haya funcionado - hace falta
        # forzar al cliente web a releer el registro, no solo escribirlo en la BD.
        return {'type': 'ir.actions.client', 'tag': 'soft_reload'}

    @api.model
    def _cron_retry_pending_sync(self):
        """Red de seguridad para cuando el intento inmediato en _sat_register_from_line
        falló al escribir en la copia local del Catálogo de Materiales - ver ir_cron en
        data/ir_cron_sat_product_catalog.xml. El intento en tiempo real sigue
        siendo el camino principal; esto es solo el reintento periódico."""
        pendientes = self.search([('sync_state', '!=', 'sincronizado')])
        for entry in pendientes:
            entry._sat_sync_local_mirror()

    @api.model
    def action_retry_pending_sync_notify(self):
        """Igual que _cron_retry_pending_sync() pero con notificación en pantalla -
        para el botón de menú, que a diferencia del cron sí tiene un usuario
        mirando la pantalla en ese momento."""
        pendientes = self.search([('sync_state', '!=', 'sincronizado')])
        total = len(pendientes)
        for entry in pendientes:
            entry._sat_sync_local_mirror()
        con_error = self.search_count([('id', 'in', pendientes.ids), ('sync_state', '=', 'error')])
        mensaje = f"Reintentados: {total} | Siguen con error: {con_error}"
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Sincronización del Catálogo de Materiales (local)',
                'message': mensaje,
                'sticky': con_error > 0,
                'type': 'warning' if con_error > 0 else 'success',
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }
