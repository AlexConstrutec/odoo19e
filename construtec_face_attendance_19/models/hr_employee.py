# -*- coding: utf-8 -*-
from odoo import models, fields, api


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    face_image_front = fields.Image(string="Rostro de Frente", max_width=512, max_height=512)
    face_image_left = fields.Image(string="Rostro - Perfil Izquierdo", max_width=512, max_height=512)
    face_image_right = fields.Image(string="Rostro - Perfil Derecho", max_width=512, max_height=512)

    # Huella facial (128 números) calculada en el navegador con face-api.js a
    # partir de cada foto de referencia. Es lo único que se usa para comparar
    # contra la cámara en vivo — nunca se manda la foto completa al comparar.
    face_descriptor_front = fields.Json(string="Huella Facial - Frente")
    face_descriptor_left = fields.Json(string="Huella Facial - Perfil Izquierdo")
    face_descriptor_right = fields.Json(string="Huella Facial - Perfil Derecho")

    face_enrolled = fields.Boolean(
        string="Rostro Registrado", compute="_compute_face_enrolled", store=True,
    )

    @api.depends('face_descriptor_front', 'face_descriptor_left', 'face_descriptor_right')
    def _compute_face_enrolled(self):
        for employee in self:
            employee.face_enrolled = bool(
                employee.face_descriptor_front
                and employee.face_descriptor_left
                and employee.face_descriptor_right
            )

    def _construtec_face_reference_descriptors(self):
        """Huellas de referencia disponibles para comparar, en orden frente/izq/der."""
        self.ensure_one()
        return [
            descriptor
            for descriptor in (
                self.face_descriptor_front,
                self.face_descriptor_left,
                self.face_descriptor_right,
            )
            if descriptor
        ]
