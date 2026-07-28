##############################################################################
#
# Copyright 2023 SIESA
#
##############################################################################
{
    'name': 'Nomina Report',
    'category': 'Account',
    'version': '16.0.1.0.0',
    'author': 'SIESA',
    'description': 'Reportes Nominas Xelpan XLSX.',
    'summary': '01 Reporte de Facturación, 02 Libro de Sueldos y Salarios,'
               ' 03 Reporte de Prestaciones Laborales, 04 Reporte de Planilla IGSS, '
               '05 Informe del empleador',
    'depends': ['base', 'hr_payroll', 'web', 'gth_reports'],
    'price': 500,
    'currency': 'EUR',
    'license': 'AGPL-3',
    'website': '',
    'data': [
        'wizard/wizard_report_nomina_view.xml',
        'security/ir.model.access.csv',
        'views/voucher_template.xml',
        'report/voucher_report.xml',
        'data/voucher_email_template.xml',
    ],
    'images': ['static/description/icon.png'],
    'installable': True,
    'auto_install': False,
    'application': False,
}
