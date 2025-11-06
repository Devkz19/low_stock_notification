from odoo import models, api
import logging

_logger = logging.getLogger(__name__)

class ReportLowStock(models.AbstractModel):
    _name = "report.low_stock_notification.low_stock_report_template"
    _description = "Low Stock Report"

    @api.model
    def _get_report_values(self, docids, data=None):
        icp = self.env['ir.config_parameter'].sudo()

        # Load configuration parameters
        notification_based_on = icp.get_param('low_stock_notification.notification_based_on', 'on_hand')
        quantity_limit = float(icp.get_param('low_stock_notification.quantity_limit', 0.0) or 0.0)
        min_quantity_based_on = icp.get_param('low_stock_notification.min_quantity_based_on', 'global')
        apply_on = icp.get_param('low_stock_notification.apply_on', 'product')

        company = self.env.company
        low_stock_products = []

        # Choose quantity field based on notification setting
        qty_field = 'qty_available' if notification_based_on == 'on_hand' else 'virtual_available'

        # ====================================================
        # 1. Global Minimum Quantity Logic
        # ====================================================
        if min_quantity_based_on == 'global' and quantity_limit > 0:
            _logger.info(f"Global min quantity check started | Apply on: {apply_on} | Limit: {quantity_limit}")

            low_stock_products = []

            # ------------------------------------------------
            # Apply on Product (aggregate all variants)
            # ------------------------------------------------
            if apply_on == 'product':
                templates = self.env['product.template'].search([('active', '=', True)])
                _logger.info(f"Fetched {len(templates)} active product templates for global product check")

                for p in templates:
                    active_variants = p.product_variant_ids.filtered(lambda v: v.active)
                    qty_available = sum(active_variants.mapped('qty_available'))
                    virtual_available = sum(active_variants.mapped('virtual_available'))

                    qty_to_check = qty_available if notification_based_on == 'on_hand' else virtual_available

                    # ✅ Only include products whose total (on hand / forecast) is below the global limit
                    if qty_to_check < quantity_limit:
                        internal_ref = p.default_code or ''
                        display_name = f"[{internal_ref}] {p.name}" if internal_ref else p.name

                        product_data = {
                            'name': display_name,
                            'quantity_limit': quantity_limit,
                            'qty_available': round(qty_available, 2),
                            'forecast_qty': round(virtual_available, 2),
                            'required_qty': round(quantity_limit - qty_to_check, 2),
                        }
                        low_stock_products.append(product_data)

                        _logger.info(
                            f"[PRODUCT] {display_name} | On hand: {qty_available} | "
                            f"Forecast: {virtual_available} | Limit: {quantity_limit}"
                        )

            # ------------------------------------------------
            # Apply on Variant (check each product variant)
            # ------------------------------------------------
            else:
                domain = [
                    ('active', '=', True),
                    (qty_field, '<', quantity_limit),
                ]
                products = self.env['product.product'].search(domain)
                _logger.info(f"Found {len(products)} variants below global limit {quantity_limit}")

                for p in products:
                    qty_available = p.qty_available
                    virtual_available = p.virtual_available
                    qty_to_check = qty_available if notification_based_on == 'on_hand' else virtual_available

                    internal_ref = p.default_code or ''
                    display_name = f"[{internal_ref}] {p.name}" if internal_ref else p.name

                    product_data = {
                        'name': display_name,
                        'quantity_limit': quantity_limit,
                        'qty_available': round(qty_available, 2),
                        'forecast_qty': round(virtual_available, 2),
                        'required_qty': round(quantity_limit - qty_to_check, 2),
                    }
                    low_stock_products.append(product_data)

                    _logger.info(
                        f"[VARIANT] {display_name} | On hand: {qty_available} | "
                        f"Forecast: {virtual_available} | Limit: {quantity_limit}"
                    )

            _logger.info(f"✅ Total low stock products found: {len(low_stock_products)}")


        # ====================================================
        # 2 Individual Minimum Quantity Logic
        # ====================================================
        elif min_quantity_based_on == 'individual':
            if apply_on == 'product':
                domain = [
                    ('active', '=', True),
                    ('minimum_quantity', '>', 0),
                ]
                products = self.env['product.template'].search(domain)
            else:  # variant
                domain = [
                    ('active', '=', True),
                    ('minimum_quantity', '>', 0),
                ]
                products = self.env['product.product'].search(domain)

            _logger.info(f"Found {len(products)} items with individual minimum quantity")

            for p in products:
                if apply_on == 'product' and hasattr(p, 'product_variant_ids'):
                    active_variants = p.product_variant_ids.filtered(lambda v: v.active)
                    qty_available = sum(active_variants.mapped('qty_available'))
                    virtual_available = sum(active_variants.mapped('virtual_available'))
                else:
                    qty_available = p.qty_available
                    virtual_available = p.virtual_available

                qty_to_check = qty_available if notification_based_on == 'on_hand' else virtual_available
                min_qty = p.minimum_quantity

                if qty_to_check < min_qty:
                    internal_ref = p.default_code or ''
                    display_name = f"[{internal_ref}] {p.name}" if internal_ref else p.name
                    product_data = {
                        'name': display_name,
                        'quantity_limit': min_qty,
                        'qty_available': round(qty_available, 2),
                        'forecast_qty': round(virtual_available, 2),
                        'required_qty': round(min_qty - qty_to_check, 2),
                    }
                    low_stock_products.append(product_data)
                    _logger.info(
                        f"Low stock product: {display_name} | On Hand: {qty_available} | Forecast: {virtual_available} ||Min Qty: {min_qty}")

        # ====================================================
        # 3 Reorder Rule Logic
        # ====================================================
        elif min_quantity_based_on == 'reorder_rules':
            reorder_rules = self.env['stock.warehouse.orderpoint'].search([('active', '=', True)])
            _logger.info(f"Found {len(reorder_rules)} reordering rules for evaluation")

            for rule in reorder_rules:
                product = rule.product_id
                if not product or not product.active:
                    continue

                # ✅ Use rule-level quantities (warehouse-specific)
                qty_on_hand = rule.qty_on_hand
                qty_forecast = rule.qty_forecast
                qty_to_check = qty_on_hand if notification_based_on == 'on_hand' else qty_forecast

                min_qty = rule.product_min_qty or 0.0

                if qty_to_check < min_qty:
                    internal_ref = product.default_code or ''
                    display_name = f"[{internal_ref}] {product.display_name}" if internal_ref else product.display_name
                    product_data = {
                        'name': display_name,
                        'quantity_limit': round(min_qty, 2),
                        'qty_available': round(qty_on_hand, 2),
                        'forecast_qty': round(qty_forecast, 2),
                        'required_qty': round(min_qty - qty_to_check, 2),
                    }
                    low_stock_products.append(product_data)

                    _logger.info(
                        f"Low stock (Reorder Rule): {display_name} | On Hand: {qty_on_hand} | "
                        f"Forecast: {qty_forecast} | Min Qty: {min_qty}"
                    )

        # ====================================================
        # Finalization
        # ====================================================
        low_stock_products = sorted(low_stock_products, key=lambda x: x['name'])
        _logger.info(f"Total low stock products found: {len(low_stock_products)}")

        return {
            'doc_ids': docids,
            'doc_model': 'product.product',
            'docs': low_stock_products,
            'company': company,
            'notification_based_on': notification_based_on,
            'quantity_limit': quantity_limit,
            'apply_on': apply_on,
            'min_quantity_based_on': min_quantity_based_on,
        }
