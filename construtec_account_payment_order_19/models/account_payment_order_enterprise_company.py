from odoo import fields, models


class AccountPaymentOrderEnterpriseCompany(models.Model):
    _name = 'account.payment.order.enterprise.company'
    _description = 'Compañía de la instalación Procesadora (Enterprise)'
    _order = 'name'

    name = fields.Char(required=True, readonly=True)
    enterprise_company_ref = fields.Char(
        string='Referencia en Enterprise', readonly=True, copy=False, index=True,
        help='Id real de esta compañía en la instalación Procesadora - se reenvía tal cual '
             '(nunca por nombre) cuando esta compañía se usa como respaldo en '
             '"Compañía por defecto", para que la Solicitud aterrice en la compañía correcta '
             'incluso si el empleado no se pudo resolver.')
