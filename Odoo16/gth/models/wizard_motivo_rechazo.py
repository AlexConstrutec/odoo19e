from odoo import models, fields

class WizardMotivoRechazo(models.TransientModel):
    _name = 'wizard.motivo.rechazo'
    _description = 'Wizard para motivo de rechazo'

    motivo_rechazo = fields.Text(string='Motivo de Rechazo')
    def action_wizard_rechazo(self):
        active_id = self.env.context.get('active_id')
        if active_id:
            request_employee = self.env['hr.request.employee'].browse(active_id)
            if self.motivo_rechazo:
                request_employee.message_post(body='Solicitud rechazada por el siguiente motivo: ' + self.motivo_rechazo)
                request_employee.write({'state': 'rechazado', 'motivo_rechazo': self.motivo_rechazo})
        return True

