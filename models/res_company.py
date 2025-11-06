from odoo import fields, models

class ResCompany(models.Model):
    _inherit = 'res.company'

    low_stock_notification = fields.Boolean(string='Low Stock Notification',
        help='Enable/Disable low stock notifications for this company')

    notification_based_on = fields.Selection([
        ('on_hand', 'On hand quantity'),
        ('forecast', 'Forecast'),
    ], string="Notification Based On", default='on_hand', help="Choose whether low stock notifications should be based on on-hand or forecasted quantity.")

    quantity_limit = fields.Float(string="Quantity Limit", help="Set the minimum stock quantity that triggers a notification.")

    min_quantity_based_on = fields.Selection([
        ('global', 'Global for all products'),
        ('individual', 'Individual for all products'),
        ('reorder_rules', 'Reorder Rules'),
    ], string="Min Quantity Based On", default='global', help="Define how the minimum quantity should be applied.")

    apply_on = fields.Selection([
        ('product', 'Product'),
        ('variant', 'Product Variant'),
    ], string="Apply On", default='product', help="Choose whether to check quantity at the product or product variant level.")
