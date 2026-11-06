# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import fields, models


class ConstrutecRegion(models.Model):
    _name = "construtec.region"
    _description = "Región"
    _order = "name"

    name = fields.Char(required=True, translate=False)
    code = fields.Char()
    active = fields.Boolean(default=True)
    analytic_account_ids = fields.One2many(
        "account.analytic.account", "region_id", string="Cuentas analíticas")
    analytic_account_count = fields.Integer(compute="_compute_analytic_account_count")

    _name_uniq = models.Constraint(
        "unique(name)",
        "Ya existe una región con ese nombre (las regiones se emparejan por nombre entre "
        "Community y Enterprise).")

    def _compute_analytic_account_count(self):
        data = self.env["account.analytic.account"]._read_group(
            [("region_id", "in", self.ids)], ["region_id"], ["__count"])
        counts = {region.id: count for region, count in data}
        for rec in self:
            rec.analytic_account_count = counts.get(rec.id, 0)

    def _find_or_create_by_name(self, name):
        """Las regiones se emparejan por NOMBRE entre bases (nunca por id)."""
        name = (name or "").strip()
        if not name:
            return self.browse()
        region = self.sudo().with_context(active_test=False).search(
            [("name", "=ilike", name)], limit=1)
        return region or self.sudo().create({"name": name})
