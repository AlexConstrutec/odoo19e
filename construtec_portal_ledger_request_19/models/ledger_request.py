import base64
import logging
from datetime import timedelta

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import formataddr

_logger = logging.getLogger(__name__)

EMAIL_FROM_PARAM = "construtec_portal_ledger_request_19.email_from"
MAX_RANGE_DAYS = 366
MAX_REQUESTS_PER_DAY = 10


class ConstrutecLedgerRequest(models.Model):
    _name = "construtec.ledger.request"
    _description = "Solicitud de Libro Mayor desde el portal"
    _order = "create_date desc, id desc"

    name = fields.Char(compute="_compute_name", store=True, string="Solicitud")
    user_id = fields.Many2one("res.users", string="Solicitado por", required=True, readonly=True, ondelete="cascade")
    partner_id = fields.Many2one(related="user_id.partner_id", store=True, string="Contacto")
    # Se congela al crear la solicitud: el Excel solo va al correo registrado del contacto,
    # nunca a uno que se escriba en el portal.
    email_to = fields.Char(string="Enviado a", required=True, readonly=True)
    company_id = fields.Many2one("res.company", string="Empresa", required=True, readonly=True)
    date_from = fields.Date(string="Fecha inicio", required=True, readonly=True)
    date_to = fields.Date(string="Fecha fin", required=True, readonly=True)
    state = fields.Selection(
        [("pendiente", "Pendiente"), ("enviado", "Enviado"), ("error", "Error")],
        string="Estado", default="pendiente", required=True, readonly=True,
    )
    error_message = fields.Text(string="Error", readonly=True)
    attachment_id = fields.Many2one("ir.attachment", string="Excel", readonly=True)
    sent_date = fields.Datetime(string="Fecha de envío", readonly=True)

    @api.depends("company_id", "date_from", "date_to")
    def _compute_name(self):
        for rec in self:
            rec.name = _("Libro Mayor %(company)s %(date_from)s a %(date_to)s",
                         company=rec.company_id.name or "", date_from=rec.date_from or "", date_to=rec.date_to or "")

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for rec in self:
            if rec.date_from > rec.date_to:
                raise ValidationError(_("La fecha inicio no puede ser mayor que la fecha fin."))
            if (rec.date_to - rec.date_from).days >= MAX_RANGE_DAYS:
                raise ValidationError(_("El rango máximo es de %s días.", MAX_RANGE_DAYS))

    # ------------------------------------------------------------------
    # Portal
    # ------------------------------------------------------------------
    @api.model
    def _portal_create_request(self, user, company_id, date_from, date_to):
        """Crea la solicitud validando todo del lado del servidor. Se llama con sudo()
        desde el controlador; `user` es request.env.user, nunca un id que venga del formulario."""
        user = user.sudo()
        try:
            company_id = int(company_id or 0)
            date_from = fields.Date.to_date(date_from)
            date_to = fields.Date.to_date(date_to)
        except (TypeError, ValueError):
            raise UserError(_("Revisa la empresa y las fechas."))
        if not date_from or not date_to:
            raise UserError(_("Indica fecha inicio y fecha fin."))
        company = user.ledger_portal_company_ids.filtered(lambda c: c.id == company_id)
        if not company:
            raise UserError(_("No tienes autorizada esa empresa."))
        if date_to > fields.Date.context_today(self):
            raise UserError(_("La fecha fin no puede ser futura."))
        email = (user.partner_id.email or "").strip()
        if not email:
            raise UserError(_("Tu contacto no tiene correo registrado. Pide a la empresa que lo agregue."))
        today_start = fields.Datetime.now() - timedelta(days=1)
        if self.search_count([("user_id", "=", user.id), ("create_date", ">=", today_start)]) >= MAX_REQUESTS_PER_DAY:
            raise UserError(_("Llegaste al límite de %s solicitudes en 24 horas.", MAX_REQUESTS_PER_DAY))

        try:
            rec = self.create({
                "user_id": user.id,
                "email_to": email,
                "company_id": company.id,
                "date_from": date_from,
                "date_to": date_to,
            })
        except ValidationError as e:
            raise UserError(e.args[0])
        self.env.ref("construtec_portal_ledger_request_19.cron_process_ledger_requests").sudo()._trigger()
        return rec

    # ------------------------------------------------------------------
    # Generación y envío
    # ------------------------------------------------------------------
    @api.model
    def _cron_process_pending(self, limit=20):
        pending = self.search([("state", "=", "pendiente")], order="id", limit=limit)
        in_cron = bool(self.env.context.get("cron_id"))
        for rec in pending:
            try:
                with self.env.cr.savepoint():
                    rec._generate_and_send()
            except Exception as e:  # noqa: BLE001 - una solicitud mala no debe trabar la cola
                _logger.exception("Error generando Libro Mayor para la solicitud %s", rec.id)
                rec.write({"state": "error", "error_message": str(e)})
            if in_cron:
                self.env["ir.cron"]._commit_progress(1)

    def _build_report_options(self):
        self.ensure_one()
        return {
            "date": {
                "date_from": fields.Date.to_string(self.date_from),
                "date_to": fields.Date.to_string(self.date_to),
                "mode": "range",
                "filter": "custom",
            },
            # Solo asientos publicados, como el reporte por defecto.
            "all_entries": False,
        }

    def _generate_xlsx(self):
        self.ensure_one()
        company = self.company_id
        report = (
            self.env.ref("account_reports.general_ledger_report").sudo()
            .with_company(company)
            .with_context(allowed_company_ids=company.ids)
        )
        options = report.get_options(self._build_report_options())
        # Defensa extra: el reporte debe quedar limitado a la empresa solicitada.
        if set(report.get_report_company_ids(options)) != {company.id}:
            raise UserError(_("El reporte no quedó limitado a la empresa %s.", company.name))
        return report.export_to_xlsx(options)

    def _get_email_from(self):
        """Remitente fijo del parámetro del sistema (el servidor SMTP de producción, Outlook, solo deja
        enviar como su propia cuenta: cualquier otro From da SendAsDenied). Se muestra con el nombre de la
        empresa solicitada. Sin parámetro: correo de la empresa, o el del usuario del cron."""
        self.ensure_one()
        company = self.company_id
        email = self.env["ir.config_parameter"].sudo().get_param(EMAIL_FROM_PARAM, "").strip()
        if email:
            return formataddr((company.name, email))
        return company.email_formatted or self.env.user.email_formatted

    def _generate_and_send(self):
        self.ensure_one()
        result = self._generate_xlsx()
        file_name = "Libro Mayor %s %s a %s.xlsx" % (self.company_id.name, self.date_from, self.date_to)
        attachment = self.env["ir.attachment"].sudo().create({
            "name": file_name,
            "datas": base64.b64encode(result["file_content"]),
            "res_model": self._name,
            "res_id": self.id,
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })
        company = self.company_id
        # Markup escapa los valores interpolados; el texto fijo queda como HTML.
        body = Markup(
            "<p>Hola %(name)s,</p>"
            "<p>Adjunto el Libro Mayor de <b>%(company)s</b> del %(date_from)s al %(date_to)s, "
            "que solicitaste desde el portal.</p>"
            "<p>Este correo se generó automáticamente.</p>"
        ) % {
            "name": self.partner_id.name or "",
            "company": company.name,
            "date_from": self.date_from.strftime("%d/%m/%Y"),
            "date_to": self.date_to.strftime("%d/%m/%Y"),
        }
        mail = self.env["mail.mail"].sudo().create({
            "subject": _("Libro Mayor %(company)s %(date_from)s a %(date_to)s",
                         company=company.name, date_from=self.date_from.strftime("%d/%m/%Y"),
                         date_to=self.date_to.strftime("%d/%m/%Y")),
            "body_html": body,
            "email_from": self._get_email_from(),
            "email_to": self.email_to,
            "attachment_ids": [(4, attachment.id)],
            "auto_delete": False,
        })
        mail.send()
        if mail.state == "exception":
            raise UserError(_("No se pudo enviar el correo: %s", mail.failure_reason or ""))
        self.write({
            "state": "enviado",
            "attachment_id": attachment.id,
            "sent_date": fields.Datetime.now(),
            "error_message": False,
        })

    def action_retry(self):
        """Backend: volver a poner en cola solicitudes con error."""
        self.filtered(lambda r: r.state == "error").write({"state": "pendiente", "error_message": False})
        self.env.ref("construtec_portal_ledger_request_19.cron_process_ledger_requests")._trigger()
