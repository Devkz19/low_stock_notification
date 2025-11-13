{
    "name": "Product Low Stock Notification",
    "version": "18.0.0.0",
    "category": "Inventory Management",
    "author": "Wan Buffer",
    "website": "www.odoo.com",
    "license": "AGPL-3",
    "depends": ["base", "mail", "stock", "product"],
    "data": [
            'report/low_stock_report_template.xml',
            'data/ir_cron_data.xml',
            'data/stock_notification_cron.xml',
            'data/stock_notification_individual.xml',
            'data/stock_notification_reorder.xml',
            'data/mail_channel_data.xml',
            'views/res_company_views.xml',
            'views/res_users_view.xml',
            'views/res_config_settings_views.xml',
            'views/product_individual_qty.xml',
         
        ],
    "installable": True,
}
