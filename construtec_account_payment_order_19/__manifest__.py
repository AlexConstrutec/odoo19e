{
    'name': 'Construtec Orden de Pago',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Órdenes de pago (Anticipo / Liquidación / Pago Directo) para conciliar facturas de '
               'varios proveedores contra pagos que no coinciden 1 a 1',
    'author': 'Alex Martínez',
    'website': 'https://www.linkedin.com/in/alex-martinez',
    'license': 'LGPL-3',
    'depends': [
        'account',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'views/account_payment_order_views.xml',
        'views/account_move_views.xml',
        'views/account_payment_views.xml',
        'report/account_payment_order_report.xml',
    ],
    'application': False,
    'installable': True,
}
