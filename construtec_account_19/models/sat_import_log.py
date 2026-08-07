from odoo import fields, models


class ConstructecSatImportLog(models.Model):
    _name = 'construtec.sat.import.log'
    _description = 'Bitácora de Importación SAT (n8n)'
    _order = 'create_date desc'

    numero_autorizacion = fields.Char(string='No. Autorización SAT')
    direction = fields.Selection([
        ('recibida', 'Recibida'),
        ('emitida', 'Emitida'),
    ], string='Dirección')
    state = fields.Selection([
        ('success', 'Éxito'),
        ('error', 'Error'),
        ('skipped_duplicate', 'Duplicado (omitido)'),
        ('nit_no_permitido', 'NIT no permitido (rechazado)'),
    ], string='Resultado', required=True)
    message = fields.Text(string='Mensaje')
    document_id = fields.Many2one('construtec.sat.document', string='Documento SAT')
