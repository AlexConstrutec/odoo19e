from odoo import fields, models


class AccountPaymentOrderExportTransferenciaWizard(models.TransientModel):
    _name = 'account.payment.order.export.transferencia.wizard'
    _description = (
        'Contenedor desechable del Excel de transferencia bancaria masiva generado por '
        '`account.payment.order.action_generar_excel_transferencia()` - existe únicamente '
        'para exponer el archivo ya armado como un Binary descargable vía `/web/content/`, sin '
        'crear un `ir.attachment` permanente (el archivo es un reporte de un momento dado, no '
        'un documento que valga la pena conservar en el chatter de ninguna Orden).'
    )

    data = fields.Binary(string='Archivo', readonly=True)
    name = fields.Char(string='Nombre del Archivo', readonly=True)
