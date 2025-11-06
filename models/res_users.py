from odoo import fields, models

class ResUsers(models.Model):
    _inherit = 'res.users'

    notify_user = fields.Boolean(
        string="Notify User",
        help="Enable to receive notifications about low stock or system alerts."
    )