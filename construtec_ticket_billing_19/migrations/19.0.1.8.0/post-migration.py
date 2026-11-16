# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Aplica la distribución analítica Ubicación + Área (100 % cada plan) del ticket a lo que ya
existe: facturas de venta de tickets, y facturas de proveedor, pagos y asientos de conciliación
de requisiciones con ticket. Solo líneas sin distribución propia (nunca pisa una fijada a mano)."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    ventas = env['account.move'].search([
        ('move_type', '=', 'out_invoice'), ('ticket_mirror_ids', '!=', False)])
    ventas._apply_ticket_analytic_distribution()
    ordenes = env['account.payment.order'].search([('ticket_mirror_id', '!=', False)])
    for orden in ordenes:
        facturas = env['account.move'].search([
            ('payment_order_id', '=', orden.id), ('move_type', '=', 'in_invoice')])
        for factura in facturas:
            orden._apply_ticket_analytic_to_lines(factura.invoice_line_ids)
        for pago in env['account.payment'].search([('payment_order_id', '=', orden.id)]):
            orden._apply_ticket_analytic_to_lines(pago.move_id.line_ids)
        if orden.move_id:
            orden._apply_ticket_analytic_to_lines(orden.move_id.line_ids)
