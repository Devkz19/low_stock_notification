from odoo import models, fields, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
    
    low_stock_notification = fields.Boolean(
        related='company_id.low_stock_notification', readonly=False)

    notification_based_on = fields.Selection(
        related='company_id.notification_based_on', readonly=False)

    quantity_limit = fields.Float(
        related='company_id.quantity_limit', readonly=False)

    min_quantity_based_on = fields.Selection(
        related='company_id.min_quantity_based_on', readonly=False)

    apply_on = fields.Selection(
        related='company_id.apply_on', readonly=False)

    # notification_based_on = fields.Selection([
    #     ('on_hand', 'On hand quantity'),
    #     ('forecast', 'Forecast'),
    # ], string="Notification Based On", default='on_hand',
    #    help="Choose whether low stock notifications should be based on on-hand or forecasted quantity.")

    # quantity_limit = fields.Float(
    #     string="Quantity Limit",
    #     help="Set the minimum stock quantity that triggers a notification."
    # )

    # min_quantity_based_on = fields.Selection([
    #     ('global', 'Global for all products'),
    #     ('individual', 'Individual for all products'),
    #     ('reorder_rules', 'Reorder Rules'),
    # ], string="Min Quantity Based On", default='global',
    #    help="Define how the minimum quantity should be applied."
    # )

    # apply_on = fields.Selection([
    #     ('product', 'Product'),
    #     ('variant', 'Product Variant'),
    # ], string="Apply On", default='product',
    #    help="Choose whether to check quantity at the product or product variant level."
    # )

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('low_stock_notification.notification_based_on', self.notification_based_on)
        icp.set_param('low_stock_notification.quantity_limit', self.quantity_limit)
        icp.set_param('low_stock_notification.min_quantity_based_on', self.min_quantity_based_on)
        icp.set_param('low_stock_notification.apply_on', self.apply_on)

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        icp = self.env['ir.config_parameter'].sudo()
        res.update(
            notification_based_on=icp.get_param('low_stock_notification.notification_based_on', default='on_hand'),
            quantity_limit=float(icp.get_param('low_stock_notification.quantity_limit', default=0.0)),
            min_quantity_based_on=icp.get_param('low_stock_notification.min_quantity_based_on', default='global'),
            apply_on=icp.get_param('low_stock_notification.apply_on', default='product')
        )
        return res