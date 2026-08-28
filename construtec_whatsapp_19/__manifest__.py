# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'Construtec WhatsApp - Órdenes de Pago',
    'summary': 'Notifica por WhatsApp (Meta Cloud API) los eventos de una Orden de Pago '
               '(Enviado/Aprobado/Aplicado/Liquidado)',
    'version': '19.0.2.0.0',
    'license': 'AGPL-3',
    'category': 'Accounting',
    'author': 'Alex Martinez',
    'depends': ['construtec_account_payment_order_19'],
    'external_dependencies': {'python': ['requests']},
    'data': [
        'security/whatsapp_security.xml',
        'security/ir.model.access.csv',
        'views/whatsapp_template_views.xml',
        'views/whatsapp_recipient_group_views.xml',
        'views/whatsapp_payment_order_notification_views.xml',
        'views/whatsapp_log_views.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
}
