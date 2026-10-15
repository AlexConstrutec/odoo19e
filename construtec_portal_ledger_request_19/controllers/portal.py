from odoo import fields, http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal


class LedgerRequestPortal(CustomerPortal):

    def _ledger_render(self, error=None, values=None):
        user = request.env.user
        companies = user.sudo().ledger_portal_company_ids
        today = fields.Date.context_today(user)
        page_values = self._prepare_portal_layout_values()
        page_values.update({
            "page_name": "libro_mayor",
            "ledger_companies": companies,
            "ledger_requests": request.env["construtec.ledger.request"].sudo().search(
                [("user_id", "=", user.id)], limit=20),
            "ledger_email": user.partner_id.email,
            "ledger_error": error,
            "ledger_sent": request.params.get("enviado"),
            "form": values or {
                "company_id": companies[:1].id,
                "date_from": today.replace(day=1, month=1).isoformat(),
                "date_to": today.isoformat(),
            },
        })
        return request.render("construtec_portal_ledger_request_19.portal_my_ledger_request", page_values)

    @http.route("/my/libro-mayor", type="http", auth="user", website=True, methods=["GET"])
    def portal_my_ledger_request(self, **kw):
        if not request.env.user.sudo().ledger_portal_company_ids:
            return request.not_found()
        return self._ledger_render()

    @http.route("/my/libro-mayor/solicitar", type="http", auth="user", website=True, methods=["POST"])
    def portal_my_ledger_request_submit(self, company_id=None, date_from=None, date_to=None, **kw):
        if not request.env.user.sudo().ledger_portal_company_ids:
            return request.not_found()
        try:
            request.env["construtec.ledger.request"].sudo()._portal_create_request(
                request.env.user, company_id, date_from, date_to)
        except UserError as e:
            form = {"company_id": int(company_id) if (company_id or "").isdigit() else False,
                    "date_from": date_from, "date_to": date_to}
            return self._ledger_render(error=e.args[0], values=form)
        return request.redirect("/my/libro-mayor?enviado=1")
