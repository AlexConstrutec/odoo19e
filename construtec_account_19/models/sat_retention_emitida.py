import logging

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero

_logger = logging.getLogger(__name__)

# Cuenta "ISR Retenido por Pagar (a terceros)" (pasivo corriente, código 210203)
# - ya creada a mano por el contador en el plan de cuentas real, DISTINTA de la
# 210209 "ISR por Pagar Retenido (FE)" que ya usa Factura Especial
# (_sat_get_retencion_taxes_fesp en sat_document.py, un account.tax de tasa
# fija -5%, no una cuenta referenciada directo como aquí). Se busca por
# código, nunca se auto-crea - mismo criterio que 110705 "IVA Retenido a
# Favor" en sat_retention.py: el usuario confirmó que esta cuenta ya existe en
# producción, así que si no aparece es una señal real de configuración
# faltante, no algo que adivinar.
_CODIGO_CUENTA_ISR_RETENIDO_TERCEROS = '210203'


class ConstructecSatRetentionEmitida(models.Model):
    _name = 'construtec.sat.retention.emitida'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Constancia de Retención de ISR Emitida (Agencia Virtual SAT)'
    _order = 'fecha_emision desc'

    numero_constancia = fields.Char(
        string='No. Constancia', required=True, copy=False, index=True,
        help='Campo "Número de Constancia" del PDF SAT-1911 - único, evita reimportar la misma constancia.')
    fecha_emision = fields.Date(string='Fecha de Emisión')
    nit_retenido = fields.Char(
        string='NIT Retenido',
        help='NIT del proveedor a quien Construtec le retuvo - a diferencia de construtec.sat.retention '
             '("Retenciones Recibidas", donde Construtec es quien recibe la retención en una venta propia), '
             'esta es la pantalla "Retenciones Emitidas": Construtec es el AGENTE RETENEDOR.')
    nombre_retenido = fields.Char(string='Nombre Retenido')
    retenido_partner_id = fields.Many2one(
        'res.partner', string='Contacto Retenido',
        help='Resuelto por NIT contra contactos ya existentes (solo búsqueda, no se crea uno nuevo aquí - '
             'campo informativo/de reporte, igual que agente_retenedor_partner_id en construtec.sat.retention). '
             'El vínculo contable real va por sat_document_id/move_id, no por este campo.')
    nit_agente_retenedor = fields.Char(
        string='NIT Agente Retenedor',
        help='Debería ser siempre el de Construtec (esta pantalla es "Retenciones Emitidas": Construtec es '
             'quien retiene, no quien recibe).')
    nombre_agente_retenedor = fields.Char(string='Nombre Agente Retenedor')
    serie = fields.Char(
        string='Serie', help='De la factura del PROVEEDOR a la que corresponde esta retención - confirmado '
                              'contra 2 PDF reales: el formulario SAT-1911 trae Serie/Número de Factura UNA '
                              'sola vez por constancia (a diferencia de SAT-2229/Recibidas, que puede cubrir '
                              'varias facturas en una sola constancia).')
    numero_factura = fields.Char(string='Número de Factura')
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True, default=lambda self: self.env.company.id)
    currency_id = fields.Many2one(
        'res.currency', string='Moneda', default=lambda self: self.env.company.currency_id.id)
    monto_renta_imponible_total = fields.Monetary(
        string='Renta Imponible Total (líneas)', currency_field='currency_id',
        compute='_compute_totales_lineas', store=True)
    monto_retencion_total = fields.Monetary(
        string='Retención Total (líneas)', currency_field='currency_id',
        compute='_compute_totales_lineas', store=True,
        help='Suma de line_ids.monto_retencion - lo que se le debe descontar al proveedor en total.')
    pdf_attachment_id = fields.Many2one('ir.attachment', string='PDF', copy=False)
    pdf_file = fields.Binary(
        string='PDF de la Constancia', related='pdf_attachment_id.datas', readonly=True,
        help='Mismo archivo que pdf_attachment_id, expuesto como campo Binary (con visor de PDF embebido) '
             'en vez de solo como adjunto.')
    pdf_filename = fields.Char(related='pdf_attachment_id.name', readonly=True)
    requiere_revision_manual = fields.Boolean(
        string='Requiere Revisión Manual',
        help='El layout del PDF no calzó con el único patrón confirmado (formulario SAT-1911, 1 factura con '
             '1 fila de concepto) - revisa/completa los montos manualmente. Una constancia con más de una '
             'fila de concepto todavía no se ha visto en un PDF real.')
    sat_document_id = fields.Many2one(
        'construtec.sat.document', string='Documento SAT',
        domain="[('direction', '=', 'recibida')]",
        help='Resuelto automáticamente por Serie + Número de Factura contra construtec.sat.document con '
             'direction=recibida - Construtec RETIENE al pagar una compra a un proveedor, nunca en una venta '
             'propia (eso es construtec.sat.retention/Recibidas). Corrige a mano si resolvió el documento '
             'incorrecto, o si no encontró ninguno (usa "Vincular Factura" una vez el documento SAT exista).')
    move_id = fields.Many2one(related='sat_document_id.move_id', string='Factura del Proveedor', store=True)
    partner_id = fields.Many2one(related='sat_document_id.partner_id', string='Proveedor', store=True)
    line_ids = fields.One2many(
        'construtec.sat.retention.emitida.line', 'retention_id', string='Conceptos Retenidos')
    state = fields.Selection([
        ('pendiente', 'Pendiente de Vincular'),
        ('vinculada', 'Vinculada'),
    ], string='Estado', compute='_compute_state', store=True)

    _numero_constancia_uniq = models.Constraint(
        'unique(numero_constancia)',
        'Ya existe una constancia de retención de ISR emitida importada con este número.',
    )

    @api.depends('line_ids.monto_renta_imponible', 'line_ids.monto_retencion')
    def _compute_totales_lineas(self):
        for retention in self:
            retention.monto_renta_imponible_total = sum(retention.line_ids.mapped('monto_renta_imponible'))
            retention.monto_retencion_total = sum(retention.line_ids.mapped('monto_retencion'))

    @api.depends('sat_document_id')
    def _compute_state(self):
        for retention in self:
            retention.state = 'vinculada' if retention.sat_document_id else 'pendiente'

    def action_vincular_factura(self):
        """Reintenta resolver sat_document_id en las constancias que aún no lo tengan - por
        ejemplo, si la constancia se importó ANTES que el documento SAT (recibida)
        correspondiente. Fills-blanks-only: nunca reemplaza un vínculo ya resuelto a mano o
        automáticamente."""
        vinculadas = 0
        for retention in self.filtered(lambda r: not r.sat_document_id):
            retention._sat_buscar_documento()
            if retention.sat_document_id:
                vinculadas += 1
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._('Vincular Factura'),
                'message': self.env._('Constancias vinculadas: %(n)s', n=vinculadas),
                'type': 'success',
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def _sat_buscar_documento(self):
        self.ensure_one()
        if self.sat_document_id or not self.serie or not self.numero_factura:
            return
        documento = self.env['construtec.sat.document'].search([
            ('direction', '=', 'recibida'),
            ('serie', '=', self.serie),
            ('numero_documento', '=', self.numero_factura),
            # Filtro de compañía: mismo resguardo que _sat_buscar_documento en
            # sat_retention.py - evita que, en una instalación multi-compañía,
            # esta constancia empareje por error el documento SAT de OTRA
            # compañía que casualmente comparta serie+número.
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if documento:
            self.sat_document_id = documento.id
            # Si la factura del proveedor ya existe y ya está posteada, la
            # constancia pudo haberse importado DESPUÉS (caso más común) - se
            # intenta aplicar el ajuste contable ya mismo en vez de esperar a
            # que alguien apriete el botón manual. Nunca falla en silencio
            # hacia arriba: si algo sale mal (ej. falta la cuenta 210203, o la
            # factura no se puede resetear a borrador porque ya tiene pagos
            # conciliados), se registra en el log y la constancia queda
            # vinculada pero sin aplicar, para completarla a mano después.
            self._sat_intentar_aplicar_retenciones_automatica()

    def _sat_intentar_aplicar_retenciones_automatica(self):
        self.ensure_one()
        if not self.move_id or self.move_id.state != 'posted':
            return
        try:
            self.action_aplicar_retenciones_contables()
        except Exception:
            _logger.exception(
                'No se pudo aplicar automáticamente la retención emitida %s (factura %s)',
                self.numero_constancia, self.move_id.name,
            )

    def action_aplicar_retenciones_contables(self):
        """Aplica, por cada línea de concepto todavía sin aplicar, el ajuste contable en la
        factura del proveedor - ver ConstructecSatRetentionEmitidaLine.action_aplicar_retencion_contable
        para el detalle. Loop masivo con savepoint por línea, mismo patrón que
        construtec.sat.retention.action_aplicar_retenciones_contables."""
        aplicadas = 0
        omitidas = 0
        errores = []
        for retention in self:
            if retention.requiere_revision_manual:
                omitidas += len(retention.line_ids)
                continue
            for line in retention.line_ids.filtered(lambda l: not l.move_line_id):
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
                        'No se pudo aplicar la retención emitida de la línea %s (constancia %s)',
                        line.id, retention.numero_constancia,
                    )
        message = self.env._('Aplicadas: %(a)s | Omitidas: %(o)s', a=aplicadas, o=omitidas)
        if errores:
            message += '\n' + '\n'.join(errores[:5])
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._('Aplicar Retenciones a Factura'),
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
        """Punto de entrada para importar una Constancia de Retención de ISR EMITIDA desde su
        PDF (formulario SAT-1911) - ver sat_retention_emitida_import.py::_parse_constancia_emitida_pdf
        para el detalle del parseo. Idempotente por numero_constancia, mismo patrón que
        construtec.sat.retention.create_from_pdf / construtec.sat.document.create_from_dte.

        Devuelve un dict con `state` ('success' | 'skipped_duplicate' | 'nit_no_permitido') y
        `retention_id`.
        """
        from .sat_retention_emitida_import import _parse_constancia_emitida_pdf
        import base64

        pdf_bytes = base64.b64decode(pdf_base64)
        vals = _parse_constancia_emitida_pdf(pdf_bytes)

        numero_constancia = vals.get('numero_constancia')
        existing = self.search([('numero_constancia', '=', numero_constancia)], limit=1)
        if existing:
            return {'state': 'skipped_duplicate', 'retention_id': existing.id}

        # Filtro de compañía: aquí se compara nit_agente_retenedor (Construtec es quien
        # retiene), NO nit_contribuyente como en construtec.sat.retention (ahí Construtec es
        # quien recibe la retención) - roles invertidos, mismo criterio de "no importar
        # constancias que no son de esta compañía".
        company_vat = (self.env.company.vat or '').strip()
        nit_agente = (vals.get('nit_agente_retenedor') or '').strip()
        if company_vat and nit_agente and nit_agente != company_vat:
            _logger.warning(
                'Constancia emitida %s rechazada: NIT del agente retenedor (%s) no coincide con el NIT de '
                '%s (%s).', numero_constancia, nit_agente, self.env.company.name, company_vat,
            )
            return {'state': 'nit_no_permitido', 'retention_id': False}

        retenido_partner = self._sat_find_partner_by_nit(vals.get('nit_retenido'))

        retention = self.create({
            'numero_constancia': numero_constancia,
            'fecha_emision': vals.get('fecha_emision'),
            'nit_retenido': vals.get('nit_retenido'),
            'nombre_retenido': vals.get('nombre_retenido'),
            'retenido_partner_id': retenido_partner.id if retenido_partner else False,
            'nit_agente_retenedor': vals.get('nit_agente_retenedor'),
            'nombre_agente_retenedor': vals.get('nombre_agente_retenedor'),
            'serie': vals.get('serie'),
            'numero_factura': vals.get('numero_factura'),
            'requiere_revision_manual': vals.get('requiere_revision_manual', False),
            'line_ids': [(0, 0, {
                'regimen': linea.get('regimen'),
                'concepto': linea.get('concepto'),
                'monto_renta_imponible': linea.get('monto_renta_imponible', 0.0),
                'monto_retencion': linea.get('monto_retencion', 0.0),
            }) for linea in vals.get('lines', [])],
        })

        if pdf_base64:
            attachment = self.env['ir.attachment'].create({
                'name': pdf_filename or f'{numero_constancia}.pdf',
                'datas': pdf_base64,
                'res_model': 'construtec.sat.retention.emitida',
                'res_id': retention.id,
            })
            retention.pdf_attachment_id = attachment.id

        return {'state': 'success', 'retention_id': retention.id}


class ConstructecSatRetentionEmitidaLine(models.Model):
    _name = 'construtec.sat.retention.emitida.line'
    _description = 'Concepto retenido de una Constancia de Retención de ISR Emitida'

    retention_id = fields.Many2one(
        'construtec.sat.retention.emitida', string='Constancia', required=True, ondelete='cascade')
    regimen = fields.Char(
        string='Régimen',
        help='Encabezado de sección del PDF (ej. "RÉGIMEN OPCIONAL SIMPLIFICADO SOBRE INGRESOS DE '
             'ACTIVIDADES LUCRATIVAS", "RENTAS DE CAPITAL INMOBILIARIO") - determina la tarifa de '
             'retención, que VARÍA por régimen (5% y 10% confirmados en los 2 PDF reales vistos, no una '
             'tasa única). Por eso monto_retencion siempre se toma tal cual del PDF, nunca se recalcula '
             'a partir de un porcentaje fijo.')
    concepto = fields.Char(string='Concepto')
    currency_id = fields.Many2one(related='retention_id.currency_id', string='Moneda', store=True)
    monto_renta_imponible = fields.Monetary(string='Renta Imponible', currency_field='currency_id')
    monto_retencion = fields.Monetary(string='Retención', currency_field='currency_id')
    move_line_id = fields.Many2one(
        'account.move.line', string='Línea de Retención Aplicada', readonly=True, copy=False,
        help='Línea negativa agregada a la factura del proveedor con el monto de esta retención - ver '
             'action_aplicar_retencion_contable(). Vacío mientras la retención solo está archivada/vinculada '
             'pero no se ha reflejado contablemente todavía.')

    def _sat_get_retencion_isr_account(self, company):
        account = self.env['account.account'].search([
            ('code', '=', _CODIGO_CUENTA_ISR_RETENIDO_TERCEROS),
            ('company_ids', 'in', company.id),
        ], limit=1)
        if not account:
            raise UserError(self.env._(
                'No se encontró la cuenta %(codigo)s "ISR Retenido por Pagar (a terceros)" en %(empresa)s. '
                'Créala primero (cuenta de tipo Pasivo Corriente) antes de aplicar retenciones contablemente.',
                codigo=_CODIGO_CUENTA_ISR_RETENIDO_TERCEROS, empresa=company.name,
            ))
        return account

    def action_aplicar_retencion_contable(self):
        """Agrega, a la factura del PROVEEDOR ya vinculada (retention_id.sat_document_id.move_id),
        una línea NEGATIVA por el monto de esta retención - a diferencia de
        construtec.sat.retention (Recibidas, donde Construtec RECIBE la retención en una venta
        propia y se crea un account.payment separado conciliado contra esa factura de venta),
        aquí Construtec es quien RETIENE al pagar una COMPRA: el efecto real es que se le debe
        pagar MENOS al proveedor, y esa diferencia se acredita a una cuenta de pasivo (lo que
        Construtec le debe a la SAT) - directamente como una línea más en la misma factura, no
        un pago aparte.

        Mismo mecanismo de fondo que _sat_get_retencion_taxes_fesp()/action_aplicar_retenciones_fesp()
        en sat_document.py (Factura Especial) - la diferencia es que ahí la tarifa es fija por ley
        (5% ISR/12% IVA, buscable como account.tax), mientras que aquí la tarifa VARÍA por
        régimen (5%/10% ya confirmados) y no hay una tasa única que buscar - por eso se usa el
        monto EXACTO del PDF como una línea directa, no un account.tax calculado.

        Si la factura ya está posteada, se resetea a borrador, se agrega la línea, y se vuelve a
        postear - mismo patrón que Odoo usa internamente para cualquier corrección posterior a
        una factura ya contabilizada. Si la factura tiene pagos ya conciliados, `button_draft()`
        fallará con el error nativo de Odoo (no se intenta deshacer conciliaciones aquí - a
        diferencia de Recibidas, esto no tiene un botón "Cancelar" dedicado todavía).

        Devuelve True si aplicó algo nuevo, False si no había nada que hacer (ya aplicado, monto
        en cero) - nunca "adivina" un monto ni fuerza la aplicación de una constancia marcada
        requiere_revision_manual."""
        self.ensure_one()
        if self.move_line_id:
            return False
        if self.retention_id.requiere_revision_manual:
            raise UserError(self.env._(
                'La constancia %(numero)s requiere revisión manual (el layout del PDF no se pudo parsear '
                'con confianza) - confirma/corrige los montos antes de aplicarla contablemente.',
                numero=self.retention_id.numero_constancia,
            ))
        if not self.retention_id.sat_document_id or not self.retention_id.move_id:
            raise UserError(self.env._(
                'La constancia %(numero)s (Serie %(serie)s / Factura %(factura)s) no está vinculada a '
                'ninguna factura todavía - vincúlala primero (botón "Vincular Factura").',
                numero=self.retention_id.numero_constancia, serie=self.retention_id.serie,
                factura=self.retention_id.numero_factura,
            ))
        if float_is_zero(self.monto_retencion, precision_digits=self.currency_id.decimal_places or 2):
            return False

        move = self.retention_id.move_id
        company = move.company_id
        account = self._sat_get_retencion_isr_account(company)

        lineas_antes = move.invoice_line_ids
        estaba_posted = move.state == 'posted'
        if estaba_posted:
            move.button_draft()
        move.write({
            'invoice_line_ids': [(0, 0, {
                'name': self.env._(
                    'Retención ISR - Constancia %(numero)s', numero=self.retention_id.numero_constancia),
                'account_id': account.id,
                'quantity': 1,
                'price_unit': -self.monto_retencion,
            })],
        })
        if estaba_posted:
            move.action_post()

        nueva_linea = move.invoice_line_ids - lineas_antes
        self.move_line_id = nueva_linea[:1].id

        # El asiento que cambia es el de la factura del proveedor (ya existía antes, no se
        # genera un documento nuevo como sí pasa en Recibidas con el account.payment) - por eso
        # el mensaje de chatter va en la propia factura.
        move.message_post(body=self.env._(
            'Retención ISR de %(monto)s aplicada (constancia %(numero)s) - se le pagará ese monto de menos '
            'al proveedor.', monto=self.monto_retencion, numero=self.retention_id.numero_constancia,
        ))

        return True
