from odoo import fields, models


class HrPayslipPrestaciones(models.Model):
    _name = 'hr.payslip.prestaciones'
    _description = 'Prestaciones de Nómina'

    employee_id = fields.Many2one('hr.employee', string='Empleado', readonly=True)
    codigo_colaborador = fields.Char(string='Código Colaborador', readonly=True)
    department_id = fields.Many2one('hr.department', string='Departamento', readonly=True,
                                     related='employee_id.department_id')
    date_start_contract = fields.Date(string='Inicio de Contrato', readonly=True,
                                       related='employee_id.version_id.contract_date_start')
    date_end_contract = fields.Date(string='Fin de Contrato', readonly=True,
                                     related='employee_id.version_id.contract_date_end')
    version_is_current = fields.Boolean(string='Contrato Vigente', readonly=True,
                                         related='employee_id.version_id.is_in_contract')
    empleado = fields.Char(string='Empleado', readonly=True)
    bono14 = fields.Float(string='BONO14', readonly=True)
    aguinaldo = fields.Float(string='AGUINALDO', readonly=True)
    vacaciones = fields.Float(string='VACACIONES', readonly=True)
    indemnizacion = fields.Float(string='INDEMNIZACIÓN', readonly=True)
    date_to = fields.Date(string='Fecha al', readonly=True)


class HrPayslipPrestacionesWizard(models.TransientModel):
    _name = 'hr.payslip.prestaciones.wizard'
    _description = 'Prestaciones de Nómina Wizard'

    date_to = fields.Date(string='Fecha al', required=True)
    company_id = fields.Many2one('res.company', string='Compañía', required=True,
                                  default=lambda self: self.env.company)

    def open_prestaciones_at_date(self):
        self.ensure_one()

        self.env['hr.payslip.prestaciones'].search([]).unlink()

        query = """
            SELECT
                emp.id employee_id,
                emp.barcode codigo_colaborador,
                emp."name" empleado,
                SUM(CASE WHEN hpl.code = 'BONO14' THEN hpl.amount WHEN hpl.code = 'BONO14P' THEN -hpl.amount ELSE 0 END) AS bono14,
                SUM(CASE WHEN hpl.code = 'AGUINALDO' THEN hpl.amount WHEN hpl.code = 'AGUINALDOP' THEN -hpl.amount ELSE 0 END) AS aguinaldo,
                SUM(CASE WHEN hpl.code = 'VACAC' THEN hpl.amount WHEN hpl.code = 'VACACPAG' THEN -hpl.amount ELSE 0 END) AS vacaciones,
                SUM(CASE WHEN hpl.code = 'INDM' THEN hpl.amount WHEN hpl.code = 'INDEMP' THEN -hpl.amount ELSE 0 END) AS indemnizacion
            FROM hr_employee emp
            LEFT JOIN hr_payslip hp ON hp.employee_id = emp.id
            LEFT JOIN hr_payslip_line hpl ON hp.id = hpl.slip_id
            WHERE hp.date_to <= %s AND emp.company_id = %s
            GROUP BY emp.id, emp.barcode, emp."name"
            HAVING
                SUM(CASE WHEN hpl.code = 'BONO14' THEN hpl.amount WHEN hpl.code = 'BONO14P' THEN -hpl.amount ELSE 0 END) != 0 OR
                SUM(CASE WHEN hpl.code = 'AGUINALDO' THEN hpl.amount WHEN hpl.code = 'AGUINALDOP' THEN -hpl.amount ELSE 0 END) != 0 OR
                SUM(CASE WHEN hpl.code = 'VACAC' THEN hpl.amount WHEN hpl.code = 'VACACPAG' THEN -hpl.amount ELSE 0 END) != 0 OR
                SUM(CASE WHEN hpl.code = 'INDM' THEN hpl.amount WHEN hpl.code = 'INDEMP' THEN -hpl.amount ELSE 0 END) != 0
            ORDER BY emp."name"
        """
        self.env.cr.execute(query, (self.date_to, self.company_id.id))
        results = self.env.cr.dictfetchall()

        for result in results:
            result['date_to'] = self.date_to
        self.env['hr.payslip.prestaciones'].create(results)

        return {
            'name': self.env._('Prestaciones de Nómina'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip.prestaciones',
            'view_mode': 'list',
            'target': 'current',
        }
