# -*- coding: utf-8 -*-
##############################################################################
#
# Copyright 2023 SIESA
#
##############################################################################

{
    'name': "Reportes Financieros Guatemala",
    'category': 'Account',
    'version': '13.0.1.1',
    'author': 'SIESA',
    'description': """
        Reportes Financieros Xelapan XLSX.
    """,
    'summary': """Libro Diario, Mayor, Balance General, Estado de Resultados, Estado de Cambios en el Patrimonio Neto, Estado de Flujo de Efectivo, Estado de Flujo de Efectivo""",
    'depends': ['base', 'stock_account'],
    'price': 500,
    'currency': 'EUR',
    'license': 'OPL-1',
    'website': "",
    'data': [
        'wizard/wizard_report_financial_view.xml',
        'report/report.xml',
        'report/report_financial.xml',
        'security/ir.model.access.csv'
    ],
    'images': ['static/description/main_screenshot.png'],
    'installable': True,
    'auto_install': False,
    'application': False,
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
