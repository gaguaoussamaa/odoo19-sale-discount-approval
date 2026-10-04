{
    'name': "Validation des remises sur devis",
    'version': '19.0.1.0.0',
    'summary': "Un devis dont la remise dépasse un seuil doit être validé "
               "par un responsable avant confirmation",
    'category': 'Sales/Sales',
    'author': "Oussama Gagua (module d'entraînement)",
    'license': 'LGPL-3',
    'depends': ['sale'],
    'data': [
        'security/sale_discount_approval_security.xml',
        'views/res_config_settings_views.xml',
        'views/sale_order_views.xml',
    ],
    'installable': True,
}
