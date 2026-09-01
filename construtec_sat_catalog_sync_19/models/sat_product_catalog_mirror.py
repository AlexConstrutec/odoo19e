# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import api, fields, models


class ConstructecMaterialsCatalogMirror(models.Model):
    _name = 'construtec.materials.catalog.mirror'
    _description = (
        'Catálogo de productos de proveedor derivado de las facturas descargadas de la SAT '
        '(construtec.sat.product.catalog, módulo construtec_account_19, Enterprise) - se '
        'sincroniza TODO (bienes y servicios), sin ningún filtro aquí en el origen; cada '
        'consumidor filtra por `bien_o_servicio` según lo que necesite (ej. la Solicitud de '
        'Materiales solo usa "Bien" - ver construtec_account_payment_order_19). Referencia para '
        'autocompletar - nunca crea product.product ni ninguna relación viva con Enterprise. '
        'Mismo modelo/mismo `_name` '
        'instalado en Enterprise (poblado localmente, sin red, desde construtec.sat.product.'
        'catalog) y en Community (poblado por sync_from_enterprise() vía XML-RPC) - nombre '
        'técnico ("construtec.materials.catalog.mirror", no "construtec.sat.*") elegido a '
        'propósito para coincidir EXACTO con la llamada XML-RPC ya desplegada en Enterprise - no '
        'cambiar sin también cambiar esa llamada.'
    )
    _order = 'ultima_fecha_compra desc'

    origin_id = fields.Integer(
        string='ID en Enterprise', required=True, index=True,
        help='El id real de la entrada de origen en construtec.sat.product.catalog (Enterprise) - '
             'clave de actualización (upsert) usada por sync_from_enterprise(), sea que se llame '
             'localmente (Enterprise, misma base) o vía XML-RPC (Community). NUNCA un id local de '
             'este registro en Community - no confundir con el id propio de este registro.')
    name = fields.Char(string='Producto', required=True)
    codigo = fields.Char(string='Código de Producto')
    partner_name = fields.Char(
        string='Proveedor',
        help='Texto plano, no un res.partner real - en Community, un id de contacto de Enterprise '
             'no significa nada aquí (bases distintas). En Enterprise (donde este modelo también '
             'vive), tampoco se resuelve como relación, por consistencia con el mismo campo del '
             'lado Community - usar `name_search` con `vendor_hint` en el contexto para preferir '
             'coincidencias por este texto, no un Many2one real a res.partner.')
    partner_vat = fields.Char(string='NIT del Proveedor')
    bien_o_servicio = fields.Selection(
        [('B', 'Bien'), ('S', 'Servicio')], string='Bien/Servicio',
        help='Copiado de `construtec.sat.product.catalog.bien_o_servicio` (Enterprise) - dato '
             'real del propio Documento SAT. No hay ningún filtro por este campo en el modelo '
             'ni en la sincronización - se sincroniza todo, cada consumidor decide qué mostrar '
             '(ej. `account.payment.order.material.line.catalogo_id` solo muestra "Bien").')
    uom_name = fields.Char(string='Unidad de Medida')
    currency_name = fields.Char(string='Moneda')
    precio_referencia = fields.Float(string='Precio de Referencia')
    primera_fecha_compra = fields.Date(string='Primera Compra')
    ultima_fecha_compra = fields.Date(string='Última Compra')
    company_id = fields.Many2one(
        'res.company', string='Compañía',
        help='En Enterprise, la compañía real de la entrada de origen. En Community no se '
             'resuelve por id cruzado (bases distintas) - si Enterprise no lo manda, cae en la '
             'compañía activa de quien sincroniza, solo como respaldo.')
    received_date = fields.Datetime(
        string='Última Recepción', default=fields.Datetime.now, readonly=True)

    _origin_id_uniq = models.Constraint(
        'unique(origin_id)',
        'Ya existe una entrada de catálogo para ese id de origen en Enterprise.',
    )

    @api.model
    def sync_from_enterprise(self, vals):
        """Punto de entrada único, llamado de dos formas distintas según dónde viva este modelo:
        - **Enterprise**: llamada ORM directa, en proceso, sin red - `construtec_account_19.
          sat_product_catalog.py::_sat_sync_to_community()` la invoca localmente porque el
          modelo ya está en la misma base de datos.
        - **Community**: llamada externa vía XML-RPC estándar de Odoo (`/xmlrpc/2/object`), desde
          ese mismo método en Enterprise, cuando además hay credenciales de conexión remota
          configuradas.

        Mismo contrato en ambos casos - ver el CLAUDE.md de este módulo para el `vals` completo.

        Upsert por `origin_id` (no create-only, a diferencia de `helpdesk.material.requisition.
        mirror`): el catálogo cambia con el tiempo (nuevo precio/fecha de última compra en cada
        factura nueva del mismo producto) y Enterprise reenvía la fila completa en cada cambio.

        Deliberadamente SIN `sudo()` - la seguridad de este endpoint depende por completo de que
        el usuario de integración (`group_sat_catalog_sync_integration`, create+write SOLO sobre
        este modelo) sea el único con permiso real de escribir aquí vía RPC; un `sudo()` aquí
        dejaría que cualquier usuario autenticado escribiera en el catálogo sin importar sus
        permisos reales. En Enterprise, la llamada local corre con el usuario real que disparó la
        sincronización (normalmente el propio flujo de `create_from_dte`), no necesita sudo
        tampoco - ya tiene permiso de sobra sobre sus propios modelos."""
        origin_id = vals.get('origin_id')
        if not origin_id:
            raise ValueError('Falta origin_id - no se puede actualizar sin la clave de origen.')
        vals = dict(vals, received_date=fields.Datetime.now())
        if not vals.get('company_id'):
            vals['company_id'] = self.env.company.id
        entry = self.search([('origin_id', '=', origin_id)], limit=1)
        if entry:
            entry.write(vals)
        else:
            entry = self.create(vals)
        return entry.id

    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        """Preferencia por proveedor, sin restringir - si el widget que llama trae `vendor_hint`
        en el contexto (ver `account.payment.order.material.line.catalogo_id` en
        construtec_account_payment_order_19), las entradas cuyo `partner_name` coincide con ese
        texto aparecen primero, pero el resto del catálogo sigue siendo buscable normalmente -
        deliberadamente NUNCA un `domain=` que oculte nada (pedido explícito del usuario: "no es
        como que restringido... sino que pueda meter más productos"). Sin `vendor_hint`, se
        comporta exactamente como el name_search nativo.

        Nota Odoo 19: el parámetro del `name_search()` nativo se llama `domain` (no `args`, como
        en versiones anteriores) - `BaseModel.name_search()` de este árbol ya lo declara así
        (`..\\odoo\\orm\\models.py`)."""
        domain = list(domain or [])
        vendor_hint = (self.env.context.get('vendor_hint') or '').strip()
        if not vendor_hint:
            return super().name_search(name=name, domain=domain, operator=operator, limit=limit)

        if name:
            search_domain = domain + ['|', ('name', operator, name), ('codigo', operator, name)]
        else:
            search_domain = domain
        records = self.search(search_domain, limit=2000)
        hint = vendor_hint.lower()
        preferidos = records.filtered(lambda r: hint in (r.partner_name or '').lower())
        ordenados = preferidos + (records - preferidos)
        return [(r.id, r.display_name) for r in ordenados[:limit]]
