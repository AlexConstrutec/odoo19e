from datetime import timedelta
import logging
from odoo import models, fields, api
from odoo.exceptions import UserError


class HrWorkEntry(models.Model):
    _inherit = 'hr.work.entry'

    dias = fields.Float('Días', store=True)
    duration = fields.Float('Horas', store=True)
    fecha_inicio = fields.Date('Fecha inicio', store=True)
    fecha_fin = fields.Date('Fecha fin', store=True)
    descripcion = fields.Char('Descripción', store=True)
    contract_id = fields.Many2one('hr.contract', string='Contrato', store=True, default=lambda self: self.employee_id.contract_id.id, readonly=False)
    contract_state = fields.Selection(related='contract_id.state', string='Estado contrato', store=True)
    date_start = fields.Datetime('Fecha Aplicar', store=True, required=True, default=fields.Datetime.now)
    date_stop = fields.Datetime(string='Fecha Fin Aplicar', store=True, readonly=False, compute='_compute_date_stop')
    frecuencia_pago = fields.Many2one('hr.contract.payment.frequency', string='Frecuencia de pago', store=True, related='contract_id.frecuencia_pago')
    _sql_constraints = [
        ('_work_entry_has_end', 'check (date_stop IS NOT NULL)',
         'Work entry must end. Please define an end date or a duration.'),
        ('_work_entry_start_before_end', 'check (date_stop > date_start)', 'Starting time should be before end time.'),
        (
            '_work_entries_no_validated_conflict',
            """
                EXCLUDE USING GIST (
                    tsrange(date_start, date_stop, '()') WITH &&,
                    int4range(employee_id, employee_id, '[]') WITH =,
                    int4range(work_entry_type_id, work_entry_type_id, '[]') WITH =
                )
                WHERE (state = 'validated' AND active = TRUE)
            """,
            'Validated work entries cannot overlap for the same employee and work entry type'
        ),
    ]
    # @api.onchange('date_start', 'work_entry_type_id', 'dias', 'date_stop')
    # def _compute_time_days(self):
    #     if self.work_entry_type_id.round_days == 'FULL' and self.dias > 0 and self.date_start:
    #         self.write({
    #             'duration': self.dias * 24,
    #             'date_stop': self.date_start + timedelta(days=self.dias -1)
    #         })
    #
    # @api.onchange('date_start', 'work_entry_type_id', 'duration', 'date_stop')
    # def _compute_time_hours(self):
    #     if self.work_entry_type_id.round_days == 'NO' and self.duration > 0 and self.date_start:
    #         self.write({
    #             'dias': 0,
    #             'date_stop': self.date_start + timedelta(hours=self.duration)
    #         })

    @api.onchange('employee_id')
    def _compute_contrato(self):
        self.contract_id = self.employee_id.contract_id.id

    # calcluar dias respescto fecha inicio y fin
    #Elminado el 13 11 2024
    # @api.onchange('fecha_inicio', 'fecha_fin', 'date_start', 'work_entry_type_id')
    # def _compute_days_day(self):
    #     if self.fecha_inicio and self.fecha_fin:
    #         if self.fecha_fin < self.fecha_inicio:
    #             raise ValueError('La fecha fin no puede ser menor a la fecha inicio')
    #         self.dias = (self.fecha_fin - self.fecha_inicio).days + 1
    #         if self.work_entry_type_id.round_days == 'FULL':
    #             if self.fecha_fin == self.fecha_inicio:
    #                 aux_date = self.date_start + timedelta(hours=24)
    #             else:
    #                 aux_date = self.date_start + timedelta(hours=int((self.dias-1) * 24))
    #             aux_duration = self.dias * 24
    #             self.write({
    #                 'date_stop': aux_date,
    #                 'duration': aux_duration
    #             })
    def _compute_date_stop(self):
        for record in self:
            if record.date_start and record.date_stop and record.work_entry_type_id.round_days == 'FULL' and record.date_stop == record.date_start:
                record.date_stop = record.date_start + timedelta(seconds=1)
        pass

    @api.onchange('date_stop')
    def _compute_hours_day(self):
        aux_date_stop = None
        if self.date_stop and not self.duration:
            aux_date_stop = self.date_stop
        if self.date_start and aux_date_stop and not self.duration:
            #self.duration en horas
            secondss = (aux_date_stop - self.date_start).total_seconds()
            self.duration = (secondss / 3600)+24
            self.dias = (self.duration / 24)

    @api.model
    def create(self, vals_list):
        if 'date_stop' in vals_list and 'duration' not in vals_list:
            aux_date_stop = fields.Datetime.from_string(vals_list['date_stop'])
            if 'date_start' in vals_list:
                #convertir vals_list['date_start'] a datetime
                secondss = (aux_date_stop - fields.Datetime.from_string(vals_list['date_start'])).total_seconds()
                vals_list['duration'] = (secondss / 3600)+24
                vals_list['dias'] = (vals_list['duration'] / 24)

        vals_list['state'] = 'validated'
        res = super(HrWorkEntry, self).create(vals_list)
        return res

    @api.model
    def write(self, vals_list):
        if 'date_stop' in vals_list and 'duration' not in vals_list:
            aux_date_stop = vals_list['date_stop']
            if 'date_start' in vals_list:
                secondss = (aux_date_stop - fields.Datetime.from_string(vals_list['date_start'])).total_seconds()
                vals_list['duration'] = (secondss / 3600)+24
                vals_list['dias'] = (vals_list['duration'] / 24)
        vals_list['state'] = 'validated'
        res = super(HrWorkEntry, self).write(vals_list)
        return res
    # @api.model
    # def create(self, vals_list):
    #     # agregar a vals_list date_stop y duration
    #     try:
    #             logging.error('vals_list create: %s', vals_list)
    #         #for val in vals_list:
    #             if 'dias' in vals_list and 'date_start' in vals_list:
    #                 if vals_list['fecha_fin'] == vals_list['fecha_inicio']:
    #                     aux_date = fields.Datetime.from_string(vals_list['date_start']) + timedelta(hours=24)
    #                 else:
    #                     if int(vals_list['dias']) == 0:
    #                         aux_date = fields.Datetime.from_string(vals_list['date_start']) + timedelta(seconds=1)
    #                     else:
    #                         aux_date = fields.Datetime.from_string(vals_list['date_start']) + timedelta(hours=int((vals_list['dias']-1) * 24))
    #                 if 'Hora Extra' in vals_list['name']:
    #                     aux_duration = int(vals_list['duration'])
    #                 else:
    #                     if int(vals_list['dias']) == 0:
    #                         aux_duration = 0
    #                     else:
    #                         aux_duration = int(vals_list['dias']) * 24
    #                 vals_list.update({
    #                     'duration': aux_duration,
    #                     'date_stop': aux_date,
    #                     'state': 'validated'
    #                 })
    #     except Exception as e:
    #         raise ValueError('Error al crear la entrada de trabajo '+str(e))
    #     res = super(HrWorkEntry, self).create(vals_list)
    #     return res

    # #@api.model
    # def write(self, vals_list):
    #     try:
    #         #agregar un log con los vals_list
    #         logging.error('vals_list: %s', vals_list)
    #         if 'dias' in vals_list and 'duration' in vals_list:
    #             auxduration = 0
    #             if vals_list['dias'] == 1:
    #                 aux_date = self.date_start + timedelta(hours=24)
    #             else:
    #                 if vals_list['dias'] == 0:
    #                     aux_date = self.date_start + timedelta(seconds=1)
    #                 else:
    #                     aux_date = self.date_start + timedelta(hours=int((vals_list['dias'] - 1) * 24))
    #             if 'Hora Extra' in self.name:
    #                 aux_duration = int(vals_list['duration'])
    #             else:
    #                 if int(vals_list['dias']) == 0:
    #                     aux_duration = 0
    #                 else:
    #                     aux_duration = int(vals_list['dias']) * 24
    #                 # aux_duration = int(vals_list['dias']) * 24
    #             vals_list.update({
    #                 'duration': aux_duration,
    #                 'date_stop': aux_date,
    #                 'state': 'validated'
    #             })
    #         elif 'state' in vals_list and vals_list['state'] == 'conflict':
    #             vals_list.update({
    #                 'state': 'validated'
    #             })
    #         res = super(HrWorkEntry, self).write(vals_list)
    #     except Exception as e:
    #         raise UserError('Error al escribir la entrada de trabajo '+str(e))
    #         # raise ValueError('Error al escribir la entrada de trabajo '+str(e))
    #     return res



        # for record in self:
        #     if record.dias and record.date_start:
        #         if record.fecha_fin == record.fecha_inicio:
        #             aux_date = record.date_start + timedelta(hours=24)
        #         else:
        #             aux_date = record.date_start + timedelta(hours=int((record.dias-1) * 24))
        #         if 'Hora Extra' in record.name:
        #             aux_duration = int(record.duration)
        #         else:
        #             aux_duration = int(record.dias) * 24
        #         record.duration = aux_duration
        #         record.date_stop = aux_date

        # Asegurarse de que vals_list es un diccionario
        # if self.dias and self.date_start:
        #     if self.fecha_fin == self.fecha_inicio:
        #         aux_date = self.date_start + timedelta(hours=24)
        #     else:
        #         aux_date = self.date_start + timedelta(hours=int((self.dias - 1) * 24))
        #
        # if isinstance(vals_list, dict):
        #     # Agregar o modificar los campos en el diccionario existente
        #     vals_list.update({
        #         'fecha_fin': self.fecha_fin,
        #         'date_start': self.date_start,
        #         'work_entry_type_id': self.work_entry_type_id.id,
        #         'date_stop': aux_date,
        #     })
        # elif isinstance(vals_list, list):
        #     # Si es una lista de diccionarios, actualizar cada uno
        #     for vals in vals_list:
        #         vals.update({
        #             'fecha_fin': self.fecha_fin,
        #             'date_start': self.date_start,
        #             'work_entry_type_id': self.work_entry_type_id.id,
        #             'date_stop': aux_date,
        #         })

        # Llamada al método 'write' de la superclase para aplicar los cambios
        # def create(self, vals_list):
        #     # agregar a vals_list date_stop y duration
        #     for val in vals_list:
        #         if 'dias' in val and 'date_start' in val:
        #             if val['fecha_fin'] == val['fecha_inicio']:
        #                 aux_date = fields.Datetime.from_string(val['date_start']) + timedelta(hours=24)
        #             else:
        #                 aux_date = fields.Datetime.from_string(val['date_start']) + timedelta(hours=int((val['dias']-1) * 24))
        #             aux_duration = int(val['dias']) * 24
        #             val.update({
        #                 'duration': aux_duration,
        #                 'date_stop': aux_date
        #             })




    # @api.onchange('date_start', 'work_entry_type_id', 'dias')
    # def _compute_time_days(self):
    #     if self.work_entry_type_id.round_days == 'FULL' and self.dias > 0 and self.date_start:
    #         aux_date = self.date_start + timedelta(hours=int(self.dias * 24))
    #         self.date_stop = aux_date
            # aux_duration = self.dias * 24
            # self.duration = aux_duration

            # if self.dias > 1:
            #     self.date_stop = self.date_start + timedelta(days=self.dias -1)
            # else:
            #     self.date_stop = self.date_start + timedelta(days=1)
            #commit
            # if self.fecha_inicio:
            #     self.fecha_fin = self.fecha_inicio + timedelta(days=self.dias -1)

    # @api.onchange('date_start', 'work_entry_type_id')
    # def _compute_time_hours(self):
    #     if self.work_entry_type_id.round_days == 'NO' and self.duration > 0 and self.date_start:
    #         self.date_stop = self.date_start + timedelta(hours=self.duration)


