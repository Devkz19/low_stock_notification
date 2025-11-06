from odoo import api, SUPERUSER_ID
import logging

_logger = logging.getLogger(__name__)

def post_init_hook(env):
    """Create Inventory Alerts mail channel after installation"""
    # The env passed to hooks may be partially loaded.
    MailChannel = env['mail.channel'].with_context(active_test=False)

    # ✅ Try to fetch admin partner safely
    try:
        admin_partner = env.ref('base.partner_admin')
    except Exception:
        admin_partner = False
        _logger.warning("⚠️ base.partner_admin not found during hook execution. Skipping partner link.")

    existing_channel = MailChannel.search([('name', '=', 'Inventory Alerts')], limit=1)

    if existing_channel:
        _logger.info("ℹ️ Inventory Alerts channel already exists.")
        return

    vals = {
        'name': 'Inventory Alerts',
        'description': (
            'This channel automatically receives low stock notifications '
            '(Global, Individual, and Reorder Rules).'
        ),
        'channel_type': 'channel',
        'public': 'private',
    }

    channel = MailChannel.create(vals)
    _logger.info("✅ Inventory Alerts channel created successfully.")

    if admin_partner:
        channel.write({'partner_ids': [(4, admin_partner.id)]})
        _logger.info(f"✅ Added {admin_partner.name} to the Inventory Alerts channel.")
