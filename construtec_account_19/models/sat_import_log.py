from odoo import fields, models


class ConstructecSatImportLog(models.Model):
    _name = 'construtec.sat.import.log'
    _description = 'Bitácora de Importación SAT (n8n)'
    _order = 'create_date desc'

    company_id = fields.Many2one(
        'res.company', string='Compañía', default=lambda self: self.env.company.id,
        help='Igual que el resto del módulo (construtec.sat.document, etc.) - fija la '
             'compañía activa al crear el registro, para que un cliente nuevo que comparta '
             'esta misma base de Odoo (varias compañías) no vea la bitácora de otro (ver '
             'security/sat_multicompany_rules.xml).')
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
        ('no_encontrado', 'Documento no encontrado'),
    ], string='Resultado', required=True)
    message = fields.Text(string='Mensaje')
    document_id = fields.Many2one('construtec.sat.document', string='Documento SAT')
