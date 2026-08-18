import logging

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero

_logger = logging.getLogger(__name__)

# Código de la cuenta contable "IVA Retenido a Favor" (activo corriente) - ya
# creada a mano por el contador en el plan de cuentas real, espejo de la
# 110702 "ISR Retenido a Favor" que ya existía para el caso de ISR. Se busca
# por código, no por un external ID fijo (mismo criterio que
# _sat_get_default_iva_tax en sat_document.py) - un ID de cuenta varía por
# instalación/compañía, el código no.
_CODIGO_CUENTA_IVA_RETENIDO = '110705'
_CODIGO_DIARIO_RETENCIONES = 'RETIVA'


class ConstructecSatRetention(models.Model):
    _name = 'construtec.sat.retention'
    _description = 'Constancia de Retención de IVA (Agencia Virtual SAT)'
    _order = 'fecha_emision desc'

    numero_constancia = fields.Char(
        string='No. de Constancia', required=True, copy=False, index=True,
        help='Campo "Número de Constancia" del PDF SAT-2229 - único, evita reimportar la misma constancia.')
    fecha_emision = fields.Date(string='Fecha de Emisión')
    nit_contribuyente = fields.Char(
        string='NIT Contribuyente', help='NIT de quien recibió la retención - debería ser el de Construtec, '
                                          'ya que esta pantalla es "Retenciones Recibidas".')
    nombre_contribuyente = fields.Char(string='Nombre Contribuyente')
    nit_agente_retenedor = fields.Char(string='NIT Agente Retenedor')
    nombre_agente_retenedor = fields.Char(string='Nombre Agente Retenedor')
    agente_retenedor_partner_id = fields.Many2one(
        'res.partner', string='Contacto Agente Retenedor',
        help='Resuelto por NIT contra contactos ya existentes (solo búsqueda, no se crea uno nuevo aquí - '
             'este campo es informativo/de reporte, a diferencia de partner_id en construtec.sat.document que '
             'sí se resuelve/crea porque de ahí sale la factura). Corrige a mano si no encontró el contacto '
             'correcto o si no encontró ninguno.')
    tipo_agente_retencion = fields.Char(string='Tipo de Agente de Retención')
    cantidad_facturas = fields.Integer(
        string='Cantidad de Facturas', help='Campo "Cantidad de Facturas" del PDF - para contrastar contra la '
                                             'cantidad real de líneas vinculadas.')
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True, default=lambda self: self.env.company.id)
    currency_id = fields.Many2one(
        'res.currency', string='Moneda', default=lambda self: self.env.company.currency_id.id)
    monto_importe_neto_total = fields.Monetary(
        string='Importe Neto Total (líneas)', currency_field='currency_id',
        compute='_compute_totales_lineas', store=True)
    monto_retencion_total = fields.Monetary(
        string='Retención Total (líneas)', currency_field='currency_id',
        compute='_compute_totales_lineas', store=True)
    monto_retencion_pdf = fields.Monetary(
        string='Retención Total (según PDF)', currency_field='currency_id',
        help='Valor de la fila "TOTAL" leído directamente del PDF - se guarda aparte del calculado desde las '
             'líneas (monto_retencion_total) para poder detectar una discrepancia si el parseo de alguna línea '
             'salió mal.')
    pdf_attachment_id = fields.Many2one('ir.attachment', string='PDF', copy=False)
    anulado = fields.Boolean(
        string='Anulada', help='El PDF trae el sello "Anulada el DD-MM-YYYY" - el sello descoloca el orden de '
                                'lectura de todo el documento, por lo que los montos por línea normalmente no se '
                                'pudieron recuperar (ver requiere_revision_manual) y no representan un movimiento '
                                'contable real de todos modos.')
    fecha_anulacion = fields.Date(string='Fecha de Anulación')
    requiere_revision_manual = fields.Boolean(
        string='Requiere Revisión Manual',
        help='El layout del PDF no calzó con ninguno de los patrones conocidos (constancia anulada, o algún otro '
             'caso todavía no visto) - revisa manualmente los montos por línea.')
    line_ids = fields.One2many('construtec.sat.retention.line', 'retention_id', string='Facturas Cubiertas')
    state = fields.Selection([
        ('pendiente', 'Pendiente de Vincular'),
        ('parcial', 'Parcialmente Vinculada'),
        ('vinculada', 'Vinculada'),
    ], string='Estado', compute='_compute_state', store=True)

    _numero_constancia_uniq = models.Constraint(
        'unique(numero_constancia)',
        'Ya existe una constancia de retención importada con este número.',
    )

    @api.depends('line_ids.monto_importe_neto', 'line_ids.monto_retencion')
    def _compute_totales_lineas(self):
        for retention in self:
            retention.monto_importe_neto_total = sum(retention.line_ids.mapped('monto_importe_neto'))
            retention.monto_retencion_total = sum(retention.line_ids.mapped('monto_retencion'))

    @api.depends('line_ids.sat_document_id')
    def _compute_state(self):
        for retention in self:
            documentos = retention.line_ids.mapped('sat_document_id')
            if not retention.line_ids or not documentos:
                retention.state = 'pendiente'
            elif len(documentos) == len(retention.line_ids):
                retention.state = 'vinculada'
            else:
                retention.state = 'parcial'

    def action_vincular_facturas(self):
        """Reintenta resolver sat_document_id en las líneas que aún no lo tengan - por
        ejemplo, si la constancia se importó ANTES que el documento SAT (emitida)
        correspondiente. Fills-blanks-only: nunca reemplaza un vínculo ya resuelto a
        mano o automáticamente."""
        actualizadas = 0
        for retention in self:
            for line in retention.line_ids.filtered(lambda l: not l.sat_document_id):
                line._sat_buscar_documento()
                if line.sat_document_id:
                    actualizadas += 1
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._('Vincular Facturas'),
                'message': self.env._('Líneas vinculadas: %(n)s', n=actualizadas),
                'type': 'success',
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def action_aplicar_retenciones_contables(self):
        """Registra, para cada línea ya vinculada a una factura, un pago parcial
        (account.payment) por el monto de la retención - conciliándolo contra el
        saldo de esa factura. Ver ConstructecSatRetentionLine.action_aplicar_retencion_contable
        para el detalle contable; esto solo es el loop masivo por encabezado, con
        savepoint por línea para que un error en una no tumbe el resto del lote."""
        aplicadas = 0
        omitidas = 0
        errores = []
        for retention in self:
            if retention.anulado or retention.requiere_revision_manual:
                omitidas += len(retention.line_ids)
                continue
            for line in retention.line_ids.filtered(lambda l: not l.payment_id):
                try:
                    with self.env.cr.savepoint():
                        aplicada = line.action_aplicar_retencion_contable()
                        if aplicada:
                            aplicadas += 1
                        else:
                            omitidas += 1
                except UserError as exc:
                    omitidas += 1
                    errores.append(str(exc))
                except Exception as exc:
                    omitidas += 1
                    errores.append(str(exc))
                    _logger.exception(
                        'No se pudo aplicar la retención de la línea %s (constancia %s)',
                        line.id, retention.numero_constancia,
                    )
        message = self.env._('Aplicadas: %(a)s | Omitidas: %(o)s', a=aplicadas, o=omitidas)
        if errores:
            message += '\n' + '\n'.join(errores[:5])
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._('Aplicar Retenciones a Facturas'),
                'message': message,
                'type': 'success' if not errores else 'warning',
                'sticky': bool(errores),
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    @api.model
    def _sat_find_partner_by_nit(self, nit):
        if not nit:
            return self.env['res.partner']
        return self.env['res.partner'].search([('vat', '=', nit)], limit=1)

    @api.model
    def create_from_pdf(self, pdf_base64, pdf_filename=None):
        """Punto de entrada para importar una Constancia de Retención de IVA desde su
        PDF (formulario SAT-2229) - ver sat_retention_import.py::_parse_constancia_pdf
        para el detalle del parseo. Idempotente por numero_constancia, igual que
        construtec.sat.document.create_from_dte.

        Devuelve un dict con `state` ('success' | 'skipped_duplicate' | 'nit_no_permitido') y
        `retention_id`.
        """
        from .sat_retention_import import _parse_constancia_pdf
        import base64

        pdf_bytes = base64.b64decode(pdf_base64)
        vals = _parse_constancia_pdf(pdf_bytes)

        numero_constancia = vals.get('numero_constancia')
        existing = self.search([('numero_constancia', '=', numero_constancia)], limit=1)
        if existing:
            return {'state': 'skipped_duplicate', 'retention_id': existing.id}

        # Mismo criterio que _sat_nits_permitidos() en sat_document.py: el bot
        # de descarga podría algún día correr contra varios NITs (ver memoria
        # "sat_bot_multitenant_vision"), así que antes de crear nada se
        # confirma que "NIT del contribuyente" del PDF (quien recibió la
        # retención) sea el de ESTA compañía - reutiliza res.company.vat, no
        # un parámetro aparte que mantener sincronizado. Si la compañía no
        # tiene NIT configurado, no se filtra nada (mismo comportamiento que
        # el filtro de sat.document).
        company_vat = (self.env.company.vat or '').strip()
        nit_contribuyente = (vals.get('nit_contribuyente') or '').strip()
        if company_vat and nit_contribuyente and nit_contribuyente != company_vat:
            _logger.warning(
                'Constancia %s rechazada: NIT del contribuyente (%s) no coincide con el NIT de %s (%s).',
                numero_constancia, nit_contribuyente, self.env.company.name, company_vat,
            )
            return {'state': 'nit_no_permitido', 'retention_id': False}

        agente_partner = self._sat_find_partner_by_nit(vals.get('nit_agente_retenedor'))

        retention = self.create({
            'numero_constancia': numero_constancia,
            'fecha_emision': vals.get('fecha_emision'),
            'nit_contribuyente': vals.get('nit_contribuyente'),
            'nombre_contribuyente': vals.get('nombre_contribuyente'),
            'nit_agente_retenedor': vals.get('nit_agente_retenedor'),
            'nombre_agente_retenedor': vals.get('nombre_agente_retenedor'),
            'agente_retenedor_partner_id': agente_partner.id if agente_partner else False,
            'tipo_agente_retencion': vals.get('tipo_agente_retencion'),
            'cantidad_facturas': vals.get('cantidad_facturas', 0),
            'monto_retencion_pdf': vals.get('monto_retencion_pdf', 0.0),
            'requiere_revision_manual': vals.get('requiere_revision_manual', False),
            'anulado': vals.get('anulado', False),
            'fecha_anulacion': vals.get('fecha_anulacion'),
            'line_ids': [(0, 0, {
                'serie': linea.get('serie'),
                'numero_factura': linea.get('numero_factura'),
                'fecha_factura': linea.get('fecha_factura'),
                'concepto': linea.get('concepto'),
                'tarifa': linea.get('tarifa', 0.0),
                'monto_importe_neto': linea.get('monto_importe_neto', 0.0),
                'monto_retencion': linea.get('monto_retencion', 0.0),
            }) for linea in vals.get('lines', [])],
        })

        if pdf_base64:
            attachment = self.env['ir.attachment'].create({
                'name': pdf_filename or f'{numero_constancia}.pdf',
                'datas': pdf_base64,
                'res_model': 'construtec.sat.retention',
                'res_id': retention.id,
            })
            retention.pdf_attachment_id = attachment.id

        return {'state': 'success', 'retention_id': retention.id}


class ConstructecSatRetentionLine(models.Model):
    _name = 'construtec.sat.retention.line'
    _description = 'Factura cubierta por una Constancia de Retención de IVA'

    retention_id = fields.Many2one(
        'construtec.sat.retention', string='Constancia', required=True, ondelete='cascade')
    serie = fields.Char(string='Serie')
    numero_factura = fields.Char(string='Número de Factura')
    fecha_factura = fields.Date(
        string='Fecha de la Factura',
        help='Solo viene en constancias que cubren varias facturas (tabla "DETALLE DE RETENCIONES" del PDF) - '
             'en una constancia de 1 sola factura el PDF no repite esta fecha por línea, solo la fecha de '
             'emisión de la constancia misma (fecha_emision del encabezado).')
    concepto = fields.Char(string='Concepto')
    tarifa = fields.Float(string='Tarifa (%)')
    currency_id = fields.Many2one(related='retention_id.currency_id', string='Moneda', store=True)
    monto_importe_neto = fields.Monetary(string='Importe Neto del Bien', currency_field='currency_id')
    monto_retencion = fields.Monetary(string='Retención', currency_field='currency_id')
    sat_document_id = fields.Many2one(
        'construtec.sat.document', string='Documento SAT',
        domain="[('direction', '=', 'emitida')]",
        help='Resuelto automáticamente por Serie + Número de Documento contra construtec.sat.document con '
             'direction=emitida - esta pantalla es "Retenciones Recibidas": Construtec es quien recibió la '
             'retención en una venta propia, nunca en una compra. Corrige a mano si resolvió el documento '
             'incorrecto, o si no encontró ninguno (por ejemplo, si el documento SAT todavía no se ha '
             'importado - en ese caso usa el botón "Vincular Facturas" del encabezado una vez exista).')
    move_id = fields.Many2one(related='sat_document_id.move_id', string='Factura', store=True)
    partner_id = fields.Many2one(related='sat_document_id.partner_id', string='Cliente', store=True)
    payment_id = fields.Many2one(
        'account.payment', string='Pago de Retención Aplicado', readonly=True, copy=False,
        help='Pago registrado y conciliado contra la factura por el monto de esta línea - ver '
             'action_aplicar_retencion_contable(). Vacío mientras la retención solo está archivada/vinculada '
             'pero no se ha reflejado contablemente todavía.')

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        for line in lines:
            if not line.sat_document_id:
                line._sat_buscar_documento()
        return lines

    def _sat_get_retencion_iva_account(self, company):
        """Cuenta 'IVA Retenido a Favor' (activo corriente, código 110705) - ya
        creada a mano en el plan de cuentas real por el contador, espejo de la
        110702 'ISR Retenido a Favor' que ya existía para ISR. Deliberadamente
        NO se auto-crea (a diferencia del diario de abajo): el usuario confirmó
        que esta cuenta ya existe en producción, así que si no aparece aquí es
        una señal real de que falta configurar algo, no algo que adivinar."""
        account = self.env['account.account'].search([
            ('code', '=', _CODIGO_CUENTA_IVA_RETENIDO),
            ('company_ids', 'in', company.id),
        ], limit=1)
        if not account:
            raise UserError(self.env._(
                'No se encontró la cuenta %(codigo)s "IVA Retenido a Favor" en %(empresa)s. Créala primero '
                '(cuenta de tipo Activo Corriente) antes de aplicar retenciones contablemente.',
                codigo=_CODIGO_CUENTA_IVA_RETENIDO, empresa=company.name,
            ))
        return account

    def _sat_get_or_create_retencion_journal(self, company):
        """Diario dedicado para los 'pagos' que en realidad son retenciones (no
        dinero real de banco/caja) - mismo patrón usado en varias
        localizaciones de Odoo para retenciones: un diario tipo 'cash' cuya
        cuenta de contrapartida (payment_account_id de su línea de método de
        pago) es la cuenta de activo de retención, en vez de una cuenta
        bancaria real. A diferencia de la cuenta 110705 (que ya existe, creada
        a mano), este diario no tiene por qué existir de antemano en ninguna
        instalación - se busca por código fijo y se crea solo si falta."""
        journal = self.env['account.journal'].search([
            ('code', '=', _CODIGO_DIARIO_RETENCIONES),
            ('company_id', '=', company.id),
        ], limit=1)
        if journal:
            return journal

        account = self._sat_get_retencion_iva_account(company)
        journal = self.env['account.journal'].create({
            'name': 'Retenciones IVA',
            'code': _CODIGO_DIARIO_RETENCIONES,
            'type': 'cash',
            'company_id': company.id,
            'default_account_id': account.id,
        })
        # El método de pago (ej. "Manual") de un diario cash/bank se computa
        # solo al crearlo - su payment_account_id es lo que Odoo usa como
        # contrapartida real al contabilizar un account.payment con este
        # diario (confirmado leyendo account_payment.py/_compute_outstanding_account_id
        # en el código fuente de Odoo 19 - NO es el default_account_id de
        # arriba, ese es solo la cuenta "general" del diario).
        for method_line in journal.inbound_payment_method_line_ids:
            method_line.payment_account_id = account.id
        return journal

    def action_aplicar_retencion_contable(self):
        """Registra un account.payment (inbound, cliente) por el monto de esta
        línea usando el diario dedicado de retenciones, y lo concilia contra la
        línea por cobrar de la factura vinculada - dejando el saldo de la
        factura reducido exactamente en ese monto (conciliación parcial nativa
        de Odoo si la factura tiene más saldo que solo esta retención, ej. el
        resto se cobra en efectivo/banco después).

        Devuelve True si aplicó algo nuevo, False si no había nada que hacer
        (ya aplicado, retención anulada, monto en cero) - nunca "adivina" un
        monto ni fuerza la aplicación de una constancia marcada
        requiere_revision_manual, cuyos montos por línea podrían no ser
        confiables."""
        self.ensure_one()
        if self.payment_id:
            return False
        if self.retention_id.anulado:
            return False
        if self.retention_id.requiere_revision_manual:
            raise UserError(self.env._(
                'La constancia %(numero)s requiere revisión manual (el layout del PDF no se pudo parsear '
                'con confianza) - confirma/corrige los montos de línea antes de aplicarla contablemente.',
                numero=self.retention_id.numero_constancia,
            ))
        if not self.sat_document_id or not self.move_id:
            raise UserError(self.env._(
                'La línea Serie %(serie)s / Factura %(factura)s de la constancia %(numero)s no está vinculada '
                'a ninguna factura todavía - vincúlala primero (botón "Vincular Facturas").',
                serie=self.serie, factura=self.numero_factura, numero=self.retention_id.numero_constancia,
            ))
        if self.move_id.state != 'posted':
            raise UserError(self.env._(
                'La factura %(factura)s todavía no está contabilizada (borrador) - contabilízala antes de '
                'aplicar la retención.', factura=self.move_id.name,
            ))
        if float_is_zero(self.monto_retencion, precision_digits=self.currency_id.decimal_places or 2):
            return False

        company = self.move_id.company_id
        journal = self._sat_get_or_create_retencion_journal(company)
        payment = self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.move_id.partner_id.id,
            'amount': self.monto_retencion,
            'journal_id': journal.id,
            'currency_id': self.currency_id.id,
            'date': self.retention_id.fecha_emision or self.move_id.invoice_date or fields.Date.context_today(self),
            'memo': self.env._(
                'Retención IVA - Constancia %(numero)s', numero=self.retention_id.numero_constancia),
        })
        payment.action_post()

        receivable_line = payment.move_id.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled)
        invoice_receivable = self.move_id.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled)
        (receivable_line + invoice_receivable).reconcile()

        self.payment_id = payment.id
        return True

    def _sat_buscar_documento(self):
        self.ensure_one()
        if not self.serie or not self.numero_factura:
            return
        documento = self.env['construtec.sat.document'].search([
            ('direction', '=', 'emitida'),
            ('serie', '=', self.serie),
            ('numero_documento', '=', self.numero_factura),
            # Filtro de compañía: sin esto, en una instalación multi-compañía
            # una constancia de una compañía podría emparejar por error el
            # documento SAT de OTRA compañía que casualmente comparta
            # serie+número (poco probable pero no imposible - dos NITs
            # distintos usando el mismo rango de numeración de su propio
            # certificador). Es un resguardo distinto y complementario al
            # filtro de NIT en create_from_pdf (ese evita que entre una
            # constancia que no es de esta compañía; este evita que, ya
            # dentro, empareje con el documento SAT equivocado).
            ('company_id', '=', self.retention_id.company_id.id),
        ], limit=1)
        if documento:
            self.sat_document_id = documento.id
            # Si la factura ya existe y ya está contabilizada (posted), la
            # retención pudo haberse importado DESPUÉS de la factura (el caso
            # más común, dado el rango de 45 días del bot) - se intenta
            # aplicar el asiento ya mismo en vez de esperar a que alguien
            # apriete el botón manual. Nunca falla en silencio hacia arriba:
            # si algo sale mal (ej. falta la cuenta 110705), se registra en el
            # log y la línea queda vinculada pero sin aplicar, para
            # completarla a mano después.
            self._sat_intentar_aplicar_retencion_automatica()

    def _sat_intentar_aplicar_retencion_automatica(self):
        self.ensure_one()
        if not self.move_id or self.move_id.state != 'posted' or self.payment_id:
            return
        try:
            self.action_aplicar_retencion_contable()
        except Exception:
            _logger.exception(
                'No se pudo aplicar automáticamente la retención de la línea %s (constancia %s, factura %s)',
                self.id, self.retention_id.numero_constancia, self.move_id.name,
            )
