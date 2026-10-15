from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    # Empresas cuyo Libro Mayor puede solicitar el usuario desde /my/libro-mayor.
    # Vacío = sin acceso. Independiente de company_ids: un usuario portal normalmente
    # solo pertenece a la compañía principal, y aquí no se le da acceso a nada del backend.
    ledger_portal_company_ids = fields.Many2many(
        "res.company",
        "construtec_ledger_portal_company_rel",
        "user_id",
        "company_id",
        string="Libro Mayor: empresas autorizadas (portal)",
        groups="base.group_erp_manager",
    )
