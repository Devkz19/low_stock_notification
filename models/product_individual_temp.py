from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    minimum_quantity = fields.Float(
        string='Minimum Quantity',
        default=0.0,
        help='Set the minimum stock quantity for this product. When stock falls below this level, it will appear in the low stock report.'
    )

class ProductProduct(models.Model):
    _inherit = 'product.product'

    minimum_quantity = fields.Float(
        string='Minimum Quantity',
        related='product_tmpl_id.minimum_quantity',
        readonly=False,
        store=True,
        help='Set the minimum stock quantity for this product variant. When stock falls below this level, it will appear in the low stock report.'
    )