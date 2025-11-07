from odoo import api, models
import base64
import logging
from markupsafe import Markup

_logger = logging.getLogger(__name__)

class ProductProduct(models.Model):
    _inherit = ['product.product', 'mail.thread', 'mail.activity.mixin']

    @api.model
    def check_low_stock_and_send_email(self):
        _logger.info("🚀 FUNCTION START: check_low_stock_and_send_email")
        company = self.env.company

        # ✅ 1. Check if company has enabled notifications
        if not company.low_stock_notification:
            _logger.info("❌ EARLY EXIT: low_stock_notification disabled")
            return False

        # ✅ 2. Fetch low stock products from report logic
        _logger.info("📊 STEP 2: Fetching low stock products")
        report_model = self.env['report.low_stock_notification.low_stock_report_template']
        report_values = report_model._get_report_values([], {})
        low_stock_products = report_values['docs']
        notification_based_on = report_values.get('notification_based_on') or company.notification_based_on
        _logger.info(f"   Found {len(low_stock_products)} low stock products")

        if not low_stock_products:
            _logger.info("❌ EARLY EXIT: No low stock products found")
            return False

        # ✅ 3. Select correct mail template (from system parameter)
        _logger.info("📧 STEP 3: Selecting mail template")
        icp = self.env['ir.config_parameter'].sudo()
        min_quantity_based_on = icp.get_param('low_stock_notification.min_quantity_based_on', 'global')

        if min_quantity_based_on == 'individual':
            template_xml_id = 'low_stock_notification.mail_template_low_stock_notification_individual'
        elif min_quantity_based_on == 'reorder_rules':
            template_xml_id = 'low_stock_notification.mail_template_low_stock_notification_reorder'
        else:
            template_xml_id = 'low_stock_notification.mail_template_low_stock_notification'

        template = self.env.ref(template_xml_id, raise_if_not_found=False)
        if not template:
            _logger.error(f"❌ EARLY EXIT: Email template {template_xml_id} not found")
            return False
        _logger.info(f"   Template found: {template_xml_id}")

        # ✅ 4. Find notify users
        _logger.info("👥 STEP 4: Finding notify users")
        notify_users = self.env['res.users'].search([
            ('notify_user', '=', True),
            ('email', '!=', False),
            ('company_id', '=', company.id),
        ])
        _logger.info(f"   Found {len(notify_users)} users to notify")
        if not notify_users:
            _logger.warning("❌ EARLY EXIT: No users found with notify_user=True")
            return False

        # ✅ 5. Generate PDF report ONCE for both email and Discuss
        _logger.info("\n" + "=" * 80)
        _logger.info("📄 STEP 5: Generating Low Stock Report PDF")
        _logger.info("=" * 80)

        pdf_attachment = None
        try:
            report_xmlid = 'low_stock_notification.action_low_stock_report'
            report_action = self.env.ref(report_xmlid)
            _logger.info(f"   ✅ Report action found: {report_action.report_name}")

            pdf_bytes, _ = self.env['ir.actions.report']._render_qweb_pdf(
                report_xmlid,
                res_ids=[],
                data={}
            )
            _logger.info(f"   ✅ PDF generated successfully — size: {len(pdf_bytes)} bytes")

            pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
            attachment_name = f"Low_Stock_Report_{company.name or 'Company'}.pdf"

            pdf_attachment = self.env['ir.attachment'].create({
                'name': attachment_name,
                'type': 'binary',
                'datas': pdf_base64,
                'res_model': 'res.company',
                'res_id': company.id,
                'mimetype': 'application/pdf',
            })
            _logger.info(f"   ✅ PDF attachment created (ID={pdf_attachment.id}, Name={pdf_attachment.name})")

        except Exception as e:
            _logger.error("   ❌ PDF generation failed", exc_info=True)
            pdf_attachment = None

        _logger.info("=" * 80)
        _logger.info(f"📄 STEP 5 COMPLETE: pdf_attachment = {pdf_attachment}")
        _logger.info(f"   Attachment is None: {pdf_attachment is None}")
        _logger.info("=" * 80 + "\n")

        # ✅ 6. Send mail to each user
        _logger.info("📧 STEP 6: SENDING EMAILS")
        mail_ids = []
        for user in notify_users:
            try:
                email_context = {
                    'recipient_name': user.name,
                    'company_name': company.name or 'Your Company',
                    'company_email': company.email,
                    'min_quantity_based_on': min_quantity_based_on,
                    'quantity_limit': company.quantity_limit if min_quantity_based_on == 'global' else None,
                    'low_stock_count': len(low_stock_products),
                    'apply_on': company.apply_on,
                    'notification_based_on': notification_based_on,
                    'low_stock_products': low_stock_products,
                }

                _logger.info(f"   Sending email to {user.name} with attachment: {pdf_attachment.id if pdf_attachment else 'NONE'}")

                mail_id = template.with_context(**email_context).send_mail(
                    res_id=company.id,
                    force_send=True,
                    email_values={
                        'email_to': user.email,
                        'email_cc': False,
                        'recipient_ids': [],
                        'attachment_ids': [pdf_attachment.id] if pdf_attachment else [],
                    }
                )
                mail_ids.append(mail_id)
                _logger.info(f"   ✅ Email sent to: {user.name} ({user.email})")
            except Exception as e:
                _logger.error(f"   ❌ Failed to send email to {user.email}: {e}")

        # ✅ 6.5 Remove duplicate mail.message attachments created by Odoo
        if mail_ids and pdf_attachment:
            self.remove_mail_message_duplicate_by_name(mail_ids, pdf_attachment.name)

        # ✅ 7. Post Discuss Notification
        _logger.info("\n" + "=" * 80)
        _logger.info("💬 STEP 7: POSTING TO DISCUSS CHANNEL")
        _logger.info("=" * 80)

        Partner = self.env['res.partner'].sudo()
        ICP = self.env['ir.config_parameter'].sudo()
        DiscussChannel = self.env['discuss.channel'].sudo()

        if 'discuss.channel' not in self.env:
            _logger.warning("⚠️ Discuss module not installed — skipping message post.")
            return mail_ids

        odoobot_partner = False
        odoobot_id = ICP.get_param('mail.odoobot_partner_id')
        if odoobot_id:
            odoobot_partner = Partner.browse(int(odoobot_id)).exists()
        if not odoobot_partner:
            odoobot_partner = Partner.search([('name', '=', 'OdooBot')], limit=1)
        if not odoobot_partner:
            odoobot_partner = self.env.user.partner_id

        channel = self.env.ref('low_stock_notification.mail_channel_inventory_alerts', raise_if_not_found=False)
        if not channel:
            channel = DiscussChannel.search([('name', '=', 'Inventory Alerts')], limit=1)
        if not channel:
            channel = DiscussChannel.create({
                'name': 'Inventory Alerts',
                'description': 'System-generated channel for low stock notifications.',
                'public': 'private',
                'channel_type': 'channel',
            })
            _logger.info(f"✅ Created new channel: {channel.name} (ID: {channel.id})")

        attachment_ids = [pdf_attachment.id] if pdf_attachment and pdf_attachment.exists() else []
        body_message = Markup(f"""
            <div style="font-family:'Segoe UI',sans-serif;font-size:14px;">
                <p><strong>⚠️ Low Stock Alert ({min_quantity_based_on.replace('_', ' ').title()})</strong></p>
                <p>{len(low_stock_products)} product(s) below minimum stock level.</p>
            </div>
        """)

        channel.with_context(mail_create_nosubscribe=True, mail_create_nousermessage=True).message_post(
            body=body_message,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
            author_id=odoobot_partner.id,
            attachment_ids=attachment_ids,
        )

        _logger.info(f"✅ STEP 7 COMPLETE: Posted successfully with {len(attachment_ids)} attachment(s)")
        _logger.info("\n🏁 FUNCTION END: check_low_stock_and_send_email\n")
        return mail_ids

    # ✅ Helper Method: Remove duplicate mail.message attachments
    @api.model
    def remove_mail_message_duplicate_by_name(self, mail_ids, attachment_name):
        """Safely remove duplicate mail.message attachments created by Odoo when sending mail."""
        Attachment = self.env['ir.attachment']
        Mail = self.env['mail.mail']
        deleted_count = 0

        for mail_id in mail_ids:
            mail = Mail.browse(mail_id)
            mail_message = getattr(mail, 'mail_message_id', False) or getattr(mail, 'message_id', False)
            if not mail_message:
                _logger.warning(f"⚠️ No mail.message found for mail.mail id={mail_id}")
                continue

            duplicates = Attachment.search([
                ('res_model', '=', 'mail.message'),
                ('res_id', '=', mail_message.id),
                ('name', '=', attachment_name),
            ])
            if duplicates:
                _logger.info(f"🗑️ Removing {len(duplicates)} duplicate mail.message attachments "
                             f"(mail_message id={mail_message.id}): {duplicates.ids}")
                deleted_count += len(duplicates)
                duplicates.unlink()

        _logger.info(f"✅ Duplicate cleanup complete — {deleted_count} attachments removed.")


                
                
#         # _logger.info("Starting OdooBot Discuss notifications")

#         # Partner = self.env['res.partner'].sudo()
#         # ICP = self.env['ir.config_parameter'].sudo()
#         # DiscussChannel = self.env['discuss.channel'].sudo()

#         # # --- 1. Ensure Discuss module is available ---
#         # if 'discuss.channel' not in self.env:
#         #     _logger.warning("discuss.channel model not available — skipping Discuss notifications.")
#         #     return

#         # # --- 2. Find or create OdooBot partner ---
#         # odoobot_partner = False
#         # odoobot_id = ICP.get_param('mail.odoobot_partner_id')
#         # if odoobot_id:
#         #     odoobot_partner = Partner.browse(int(odoobot_id)).exists()
#         # if not odoobot_partner:
#         #     odoobot_partner = Partner.search([('name', '=', 'OdooBot')], limit=1)
#         # if not odoobot_partner:
#         #     # Trigger official OdooBot
#         #     bot = self.env.ref('mail.mail_bot_odoobot', raise_if_not_found=False)
#         #     if bot:
#         #         try:
#         #             bot._ensure_odoobot()
#         #             odoobot_id = ICP.get_param('mail.odoobot_partner_id')
#         #             odoobot_partner = Partner.browse(int(odoobot_id)).exists()
#         #             _logger.info(f"OdooBot initialized: {odoobot_partner.name}")
#         #         except Exception as e:
#         #             _logger.error(f"Failed to init OdooBot: {e}")
#         #     if not odoobot_partner:
#         #         odoobot_partner = Partner.create({
#         #             'name': 'OdooBot',
#         #             'email': False,
#         #             'image_1920': self.env.ref('mail.bot_odoobot_image').read()[0]['datas'],
#         #         })
#         #         ICP.set_param('mail.odoobot_partner_id', odoobot_partner.id)
#         #         _logger.info(f"OdooBot partner created: ID {odoobot_partner.id}")

#         # if not odoobot_partner:
#         #     _logger.warning("OdooBot not available — skipping Discuss")
#         #     return

#         # # --- 3. Send DM to each user ---
#         # for user in notify_users:
#         #     try:
#         #         user_partner = user.partner_id
#         #         if not user_partner:
#         #             _logger.warning(f"User {user.name} has no partner — skipping DM")
#         #             continue

#         #         alert_type_label = min_quantity_based_on.replace('_', ' ').title()
#         #         body_message = f"""
#         #             <p><strong>Low Stock Alert ({alert_type_label})</strong></p>
#         #             <p>Hi {user.name},</p>
#         #             <p>{len(low_stock_products)} product(s) are below the minimum stock level.</p>
#         #             <p>Attached is the detailed report for your review.</p>
#         #         """

#         #         # 1. Search for existing DM by name pattern
#         #         channel_name = f"OdooBot ↔ {user.name}"
#         #         channel = DiscussChannel.search([
#         #             ('channel_type', '=', 'chat'),
#         #             ('name', '=', channel_name),
#         #         ], limit=1)

#         #         # 2. Create DM with REQUIRED name
#         #         if not channel:
#         #             channel = DiscussChannel.create({
#         #                 'name': channel_name,
#         #                 'channel_type': 'chat',
#         #                 'channel_partner_ids': [(4, odoobot_partner.id), (4, user_partner.id)],
#         #             })
#         #             _logger.info(f"Created DM: {channel_name}")

#         #         # 3. Post message + PDF
#         #         channel.with_context(mail_create_nosubscribe=True).message_post(
#         #             body=body_message,
#         #             message_type='notification',
#         #             subtype_xmlid='mail.mt_comment',
#         #             author_id=odoobot_partner.id,
#         #             partner_ids=[user_partner.id],
#         #             attachment_ids=[(4, attachment.id)] if attachment else [],
#         #         )
#         #         _logger.info(f"OdooBot DM sent to {user.name}")

#         #     except Exception as e:
#         #         _logger.error(f"Failed to send OdooBot DM to {user.name}: {e}")



      