# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HelpdeskMaterialRequisitionMirror(models.Model):
    _name = "helpdesk.material.requisition.mirror"
    _description = (
        "Espejo de solo lectura de una Solicitud de Materiales enviada "
        "desde Odoo Community, vía API, cuando esta se marca como Enviada."
    )
    _order = "create_date desc"

    name = fields.Char(string="Referencia", required=True)
    source_system = fields.Char(string="Sistema de Origen")
    ticket_reference = fields.Char(string="Ticket")
    team_name = fields.Char(string="Equipo")
    requested_by_name = fields.Char(string="Solicitado por")
    request_date = fields.Date(string="Fecha de Solicitud")
    submit_date = fields.Datetime(string="Fecha de Envío (Community)")
    reason = fields.Text(string="Motivo")
    received_date = fields.Datetime(
        string="Fecha de Recepción", default=fields.Datetime.now, readonly=True
    )
    line_ids = fields.One2many(
        comodel_name="helpdesk.material.requisition.mirror.line",
        inverse_name="mirror_id",
        string="Líneas",
    )
    line_count = fields.Integer(compute="_compute_line_count")

    @api.depends("line_ids")
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)


class HelpdeskMaterialRequisitionMirrorLine(models.Model):
    _name = "helpdesk.material.requisition.mirror.line"
    _description = "Línea de un espejo de Solicitud de Materiales"

    mirror_id = fields.Many2one(
        comodel_name="helpdesk.material.requisition.mirror",
        required=True,
        ondelete="cascade",
    )
    product_name = fields.Char(string="Producto")
    description = fields.Char(string="Descripción")
    qty = fields.Float(string="Cantidad")
    uom_name = fields.Char(string="Unidad de Medida")
    requisition_type = fields.Char(string="Origen")
    vendor_name = fields.Char(string="Proveedor")
    estimated_price = fields.Float(string="Precio Estimado")
    subtotal = fields.Float(string="Subtotal")
