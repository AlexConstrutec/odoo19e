from odoo import models, fields, api

class HrPayslipPrestacionesWizard(models.TransientModel):
    _name = 'hr.payslip.prestaciones.wizard'
    _description = 'Prestaciones de Nómina Wizard'

    date_to = fields.Date(string='Fecha al', required=True)
    company_id = fields.Many2one('res.company', string='Compañía', required=True, default=lambda self: self.env.company)

    def open_prestaciones_at_date(self):
        self.ensure_one()
        date_to = self.date_to

        # Eliminar datos anteriores para no duplicar
        self.env['hr.payslip.prestaciones'].search([]).unlink()

        # Calcular prestaciones
        query = """
            select 
                emp.id employee_id,
                emp.codigo_empleado codigo_colaborador,
                emp."name" empleado,
                SUM(CASE WHEN hpl.code = 'BONO14' THEN hpl.amount WHEN hpl.code = 'BONO14P' THEN -hpl.amount ELSE 0 END) AS bono14,
                SUM(CASE WHEN hpl.code = 'AGUINALDO' THEN hpl.amount WHEN hpl.code = 'AGUINALDOP' THEN -hpl.amount ELSE 0 END) AS aguinaldo,
                SUM(CASE WHEN hpl.code = 'VACAC' THEN hpl.amount WHEN hpl.code = 'VACACPAG' THEN -hpl.amount ELSE 0 END) AS vacaciones,
                SUM(CASE WHEN hpl.code = 'INDM' THEN hpl.amount WHEN hpl.code = 'INDEMP' THEN -hpl.amount ELSE 0 END) AS indemnizacion
            from hr_employee emp
            left join hr_payslip hp on hp.employee_id = emp.id
            left join hr_payslip_line hpl on hp.id = hpl.slip_id
            where hp.date_to <= %s and emp.company_id = %s
            group by emp.id, emp.codigo_empleado, emp."name"
            having 
                SUM(CASE WHEN hpl.code = 'BONO14' THEN hpl.amount WHEN hpl.code = 'BONO14P' THEN -hpl.amount ELSE 0 END) != 0 or
                SUM(CASE WHEN hpl.code = 'AGUINALDO' THEN hpl.amount WHEN hpl.code = 'AGUINALDOP' THEN -hpl.amount ELSE 0 END) != 0 or
                SUM(CASE WHEN hpl.code = 'VACAC' THEN hpl.amount WHEN hpl.code = 'VACACPAG' THEN -hpl.amount ELSE 0 END) != 0 or
                SUM(CASE WHEN hpl.code = 'INDM' THEN hpl.amount WHEN hpl.code = 'INDEMP' THEN -hpl.amount ELSE 0 END) != 0
            order by emp."name";
        """
        self.env.cr.execute(query, (date_to, self.company_id.id))
        #self.env.cr.execute(query, (date_to,))
        results = self.env.cr.dictfetchall()

        prestaciones_obj = self.env['hr.payslip.prestaciones']
        for result in results:
            prestaciones_obj.create({
                'employee_id': result['employee_id'],
                'codigo_colaborador': result['codigo_colaborador'],
                'empleado': result['empleado'],
                'bono14': result['bono14'],
                'aguinaldo': result['aguinaldo'],
                'vacaciones': result['vacaciones'],
                'indemnizacion': result['indemnizacion'],
                'date_to': str(date_to),
            })

        return {
            'name': 'Prestaciones de Nómina',
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip.prestaciones',
            'view_mode': 'tree',
            'target': 'current',
        }
