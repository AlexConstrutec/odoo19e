# -*- coding: utf-8 -*-
{
    'name': "GTH Reports",

    'summary': """ Reports GTH """,

    'description': """
        Adiciones a modulo empleados para reportes
    """,

    'author': "Alex Martínez",
    'website': "",

    'version': '0.1',
    'category': 'Human Resources/Employees',
    'sequence': 95,

    'depends': [
        'base',
        'hr',
        'hr_contract',
    ],
    'data': [
        "security/ir.model.access.csv",
        "report/report_constancia_laboral.xml",
        "views/constancia_laboral.xml",
        "views/res_company_views.xml",
        "views/solicitud_irtra.xml",
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}