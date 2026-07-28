# -*- coding: utf-8 -*-
{
    'name': "NOMINAS Empleados",

    'summary': """ Empleados NOMINAS """,

    'description': """
        Adiciones a modulo de nominas
    """,

    'author': "Alex Martínez",
    'website': "https://odoocorporativo.xelapan.com",

    'version': '0.1',
    'category': 'Human Resources/Employees',
    'sequence': 95,

    'depends': [
        'hr',
        'base_setup',
        'mail',
        'resource',
        'web',
        'hr_contract',
        'hr_payroll',
        'ent_ohrms_salary_advance',
        'ent_ohrms_loan',
        'hr_work_entry',
    ],
    'data': [
        "data/hr_qualification_data.xml",
        "views/hr_contract_views.xml",
        "views/hr_work_entry_views.xml",
        "views/hr_qualification_views.xml",
        "security/ir.model.access.csv",
        "views/hr_payslip_worked_days_wizard_views.xml",
        "views/hr_leave_views.xml",
        "views/account_payment_views.xml",
        "views/account_move_views.xml",
        "views/hr_payslips_prestaciones_views.xml",
        "views/hr_payslips_prestaciones_wizard_views.xml",
    ],
        'assets': {
            'web.assets_backend': [
                'nomina/static/src/js/hr_payslip_prestaciones_button.js',
            ],
        },
    'application': False,
}