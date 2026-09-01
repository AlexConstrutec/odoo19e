# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'Construtec Catálogo SAT (Sync)',
    'summary': 'Catálogo de productos de proveedor derivado de los Documentos SAT - mismo modelo en Enterprise y Community',
    'version': '19.0.1.0.0',
    'license': 'AGPL-3',
    'category': 'Inventory',
    'author': 'Alex Martinez',
    'depends': ['base'],
    'data': [
        'security/sat_catalog_sync_security.xml',
        'security/ir.model.access.csv',
        'views/sat_product_catalog_mirror_views.xml',
    ],
    'installable': True,
    'application': False,
}
