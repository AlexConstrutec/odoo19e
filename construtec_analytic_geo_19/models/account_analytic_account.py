# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import logging

from odoo import api, fields, models
from odoo.addons.construtec_account_payment_order_19.tools.enterprise_sync_api import (
    EnterpriseSyncError, _jsonrpc, authenticate)

_logger = logging.getLogger(__name__)

GEO_FIELDS = ("region_id", "geo_latitude", "geo_longitude")


class AccountAnalyticAccount(models.Model):
    _inherit = "account.analytic.account"

    region_id = fields.Many2one(
        "construtec.region", string="Región", index=True, ondelete="restrict",
        help="Región de la ubicación (ruta de los tickets). Se empareja por nombre entre "
             "Community y Enterprise.")
    geo_latitude = fields.Float(string="Latitud", digits=(10, 7))
    geo_longitude = fields.Float(string="Longitud", digits=(10, 7))
    geo_map = fields.Char(
        string="Mapa", compute="_compute_geo_map", readonly=False,
        help="Solo sostiene el widget del mapa (no guarda nada): el pin se coloca con un clic. "
             "`readonly=False` es indispensable: un campo calculado es de solo lectura por "
             "defecto y el widget del mapa no deja seleccionar en solo lectura.")
    geo_write_date = fields.Datetime(
        string="Ubicación editada", readonly=True, copy=False,
        help="Cuándo se editó por última vez región/coordenada, en cualquiera de las dos "
             "bases. Si se edita en las dos antes de sincronizar, gana la edición más reciente.")
    geo_sync_state = fields.Selection(
        [("ok", "Sincronizada"), ("pending", "Pendiente de enviar"), ("error", "Error al enviar")],
        string="Estado de ubicación", default="ok", readonly=True, copy=False)
    geo_sync_error = fields.Char(string="Error de sincronización", readonly=True, copy=False)

    def _compute_geo_map(self):
        for rec in self:
            rec.geo_map = False

    # ---------------------------------------------------------------- edición local
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if any(vals.get(f) for f in GEO_FIELDS) and not self.env.context.get("construtec_geo_skip"):
                vals.setdefault("geo_write_date", fields.Datetime.now())
                vals.setdefault("geo_sync_state", self._geo_pending_state())
        return super().create(vals_list)

    def write(self, vals):
        if any(f in vals for f in GEO_FIELDS) and not self.env.context.get("construtec_geo_skip"):
            vals = dict(vals, geo_write_date=fields.Datetime.now(),
                        geo_sync_state=self._geo_pending_state(), geo_sync_error=False)
        return super().write(vals)

    @api.model
    def _geo_pending_state(self):
        """Solo la instalación Solicitante (Community) envía; Enterprise espera a que la jalen."""
        company = self.env.company
        if company.payment_order_role == "solicitante" and company.payment_order_sync_enabled:
            return "pending"
        return "ok"

    def _geo_payload(self):
        self.ensure_one()
        return {
            "region_name": self.region_id.name or False,
            "latitude": self.geo_latitude,
            "longitude": self.geo_longitude,
            "geo_write_date": self.geo_write_date and fields.Datetime.to_string(self.geo_write_date) or False,
        }

    def _geo_apply(self, payload):
        """Aplica un payload recibido (sin disparar de nuevo la lógica de edición local)."""
        self.ensure_one()
        region = self.env["construtec.region"]._find_or_create_by_name(payload.get("region_name"))
        self.sudo().with_context(construtec_geo_skip=True).write({
            "region_id": region.id or False,
            "geo_latitude": payload.get("latitude") or 0.0,
            "geo_longitude": payload.get("longitude") or 0.0,
            "geo_write_date": payload.get("geo_write_date") or False,
            "geo_sync_state": "ok",
            "geo_sync_error": False,
        })

    # ---------------------------------------------------------------- lado Enterprise (RPC)
    def sync_geo_from_community(self, payload):
        """Método whitelisted, llamado por JSON-RPC desde Community: aplica la ubicación SOLO
        si la edición de Community es más reciente que la de aquí. Devuelve si se aplicó y,
        si no, la ubicación vigente de aquí para que Community la adopte (gana la más reciente)."""
        self.ensure_one()
        mine = self.geo_write_date
        theirs = fields.Datetime.to_datetime(payload.get("geo_write_date")) if payload.get("geo_write_date") else False
        if theirs and (not mine or theirs >= mine):
            self._geo_apply(payload)
            return {"applied": True}
        return dict(self._geo_payload(), applied=False)

    # ---------------------------------------------------------------- lado Community (cron)
    @api.model
    def _cron_sync_geo(self):
        """Solo Community (rol Solicitante con sync activa): 1) empuja lo pendiente/con error,
        2) jala la ubicación de Enterprise y la adopta si es más reciente que la local. Por
        cuenta: nunca aborta el lote entero por una falla."""
        for company in self.env["res.company"].sudo().search([]):
            if company.payment_order_role != "solicitante" or not company.payment_order_sync_enabled:
                continue
            try:
                company._geo_sync_company()
            except EnterpriseSyncError as exc:
                _logger.warning("Sincronización de ubicación falló para %s: %s", company.name, exc)

    @api.model
    def _geo_rpc(self, company, model, method, args, kwargs=None):
        uid = authenticate(company.payment_order_sync_url, company.payment_order_sync_db,
                           company.payment_order_sync_login, company.payment_order_sync_api_key)
        return _jsonrpc(
            company.payment_order_sync_url, "object", "execute_kw",
            [company.payment_order_sync_db, uid, company.payment_order_sync_api_key,
             model, method, args, kwargs or {}])


class ResCompany(models.Model):
    _inherit = "res.company"

    def _geo_sync_company(self):
        self.ensure_one()
        Account = self.env["account.analytic.account"].sudo()
        # 1) empujar
        for acc in Account.search([("geo_sync_state", "in", ("pending", "error")),
                                   ("enterprise_analytic_ref", "!=", False)]):
            try:
                res = Account._geo_rpc(
                    self, "account.analytic.account", "sync_geo_from_community",
                    [[int(acc.enterprise_analytic_ref)], acc._geo_payload()])
                if res.get("applied"):
                    acc.with_context(construtec_geo_skip=True).write(
                        {"geo_sync_state": "ok", "geo_sync_error": False})
                else:
                    acc._geo_apply(res)  # Enterprise tenía una edición más reciente
            except EnterpriseSyncError as exc:
                acc.with_context(construtec_geo_skip=True).write(
                    {"geo_sync_state": "error", "geo_sync_error": str(exc)[:250]})
        # 2) jalar
        remotos = Account._geo_rpc(
            self, "account.analytic.account", "search_read",
            [[("geo_write_date", "!=", False)]],
            {"fields": ["geo_latitude", "geo_longitude", "geo_write_date", "region_id"]})
        for rem in remotos:
            acc = Account.search([("enterprise_analytic_ref", "=", str(rem["id"]))], limit=1)
            if not acc or acc.geo_sync_state != "ok":
                continue
            theirs = fields.Datetime.to_datetime(rem["geo_write_date"])
            if not acc.geo_write_date or theirs > acc.geo_write_date:
                acc._geo_apply({
                    "region_name": rem["region_id"] and rem["region_id"][1] or False,
                    "latitude": rem["geo_latitude"], "longitude": rem["geo_longitude"],
                    "geo_write_date": rem["geo_write_date"]})
