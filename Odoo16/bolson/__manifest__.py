# -*- encoding: utf-8 -*-

{
    'name' : 'Bolson',
    'version' : '2.0',
    'category': 'Custom',
    'description': """Manejo de cajas chicas y liquidaciones""",
    'author': 'aquíH',
    'website': 'http://www.aquih.com/',
    'depends' : [ 'account' ],
    'data' : [
        'views/report.xml',
        'views/bolson_view.xml',
        'views/reporte_bolson.xml',
        'security/ir.model.access.csv',
        'security/bolson_security.xml',
        'views/payment_view.xml',
        'views/invoice_view.xml',
        #'wizard/factura_selection_wizard.xml',
    ],
    'installable': True,
    'certificate': '',
}
