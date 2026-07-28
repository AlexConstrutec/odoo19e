import logging

from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta  # Importar datetime y timedelta

class HolidaysRequest(models.Model):
    _inherit = 'hr.leave'

    @api.onchange('request_date_from', 'number_of_days')
    def _compute_number_of_days(self):
        if self.request_date_from and self.number_of_days:
            self.request_date_to = self.request_date_from + timedelta(days=self.number_of_days - 1)
        else:
            self.request_date_to = self.request_date_from

    def _generate_work_entries(self):
        work_entry_vals = []
        for leave in self:
            if leave.holiday_status_id.request_unit == 'day':
                start_date = fields.Datetime.from_string(leave.date_from)
                end_date = fields.Datetime.from_string(leave.date_to)
                duration = (end_date - start_date).days + 1

                for day in range(duration):
                    date = start_date + timedelta(days=day)
                    ini = date.replace(hour=14, minute=0, second=0)
                    fin = date.replace(hour=22, minute=0, second=0)
                    work_entry_vals.append({
                        'name': leave.name,
                        'employee_id': leave.employee_id.id,
                        'date_start': date.replace(hour=14, minute=0, second=0),
                        'date_stop': date.replace(hour=22, minute=0, second=0),
                        'work_entry_type_id': leave.holiday_status_id.work_entry_type_id.id,
                        'leave_id': leave.id,
                        'company_id': leave.employee_company_id.id,
                        'state': 'validated',
                        'duration': 8.0
                    })
                    logging.warning('---------------------------> work_entry_vals: %s', work_entry_vals)
                self.env['hr.work.entry'].create(work_entry_vals)

    # @api.model
    # def create(self, vals):
    #     leave = super(HolidaysRequest, self).create(vals)
    #     leave._generate_work_entries()
    #     return leave

    def write(self, vals):
        result = super(HolidaysRequest, self).write(vals)
        self._generate_work_entries()
        return result

    def unlink(self):
        self.env['hr.work.entry'].search([('leave_id', 'in', self.ids)]).unlink()
        return super(HolidaysRequest, self).unlink()