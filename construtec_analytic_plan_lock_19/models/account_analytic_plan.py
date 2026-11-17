from odoo import api, models
from odoo.exceptions import UserError


class AccountAnalyticPlan(models.Model):
    _inherit = 'account.analytic.plan'

    @api.model_create_multi
    def create(self, vals_list):
        """Bloquea la creación de planes analíticos para TODOS, incluido el administrador
        (2026-11-16, pedido de Alex). Excepciones:
        - `install_mode`: Odoo carga datos de módulos (instalar/actualizar) y algunos crean planes.
        - contexto `construtec_allow_plan_create`: para levantar el bloqueo a propósito
          (por ejemplo desde un shell) cuando el responsable lo autorice."""
        ctx = self.env.context
        if not (ctx.get('install_mode') or ctx.get('construtec_allow_plan_create')):
            raise UserError(self.env._(
                "La creación de planes analíticos está bloqueada. Solicite la autorización "
                "al responsable de Tecnología."))
        return super().create(vals_list)
