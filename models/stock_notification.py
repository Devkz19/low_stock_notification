from odoo import api, models
import base64
import logging

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
        _logger.info("📄 STEP 5: GENERATING PDF ATTACHMENT - STARTING NOW")
        _logger.info("=" * 80)
        
        pdf_attachment = None
        
        try:
            _logger.info("   Step 5.1: Getting report by name...")
            report = self.env['ir.actions.report']._get_report_from_name('low_stock_notification.low_stock_report_template')
            _logger.info(f"   ✅ Report object retrieved: {report}")
            
            _logger.info("   Step 5.2: Calling _render_qweb_pdf([])...")
            pdf_result = report._render_qweb_pdf([])
            _logger.info(f"   ✅ _render_qweb_pdf returned: {type(pdf_result)}")
            
            if isinstance(pdf_result, tuple):
                pdf_content = pdf_result[0]
                _logger.info(f"   ✅ Extracted PDF content from tuple: {len(pdf_content)} bytes")
            else:
                pdf_content = pdf_result
                _logger.info(f"   ✅ PDF content (direct): {len(pdf_content)} bytes")
            
            _logger.info("   Step 5.3: Encoding to base64...")
            pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
            _logger.info(f"   ✅ Base64 encoded: {len(pdf_base64)} characters")
            
            attachment_name = f'Low_Stock_Report_{company.name}.pdf'
            _logger.info(f"   Step 5.4: Creating attachment '{attachment_name}'...")

            # Create attachment directly (no search for existing)
            pdf_attachment = self.env['ir.attachment'].create({
                'name': attachment_name,
                'type': 'binary',
                'datas': pdf_base64,
                'res_model': 'res.company',
                'res_id': company.id,
                'mimetype': 'application/pdf',
            })
            _logger.info(f"   ✅ Attachment created successfully!")
            _logger.info(f"      ID: {pdf_attachment.id}")
            _logger.info(f"      Name: {pdf_attachment.name}")
            _logger.info(f"      Exists: {pdf_attachment.exists()}")
            
        except Exception as e:
            _logger.error("   ❌ EXCEPTION IN STEP 5:", exc_info=True)
            _logger.error(f"   Error message: {str(e)}")
            pdf_attachment = None
        
        _logger.info("=" * 80)
        _logger.info(f"📄 STEP 5 COMPLETE: pdf_attachment = {pdf_attachment}")
        _logger.info(f"   Attachment is None: {pdf_attachment is None}")
        if pdf_attachment:
            _logger.info(f"   Attachment ID: {pdf_attachment.id}")
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

        # ✅ 7. Post Discuss Notification
        _logger.info("\n" + "=" * 80)
        _logger.info("💬 STEP 7: POSTING TO DISCUSS CHANNEL")
        _logger.info("=" * 80)
        _logger.info(f"   pdf_attachment = {pdf_attachment}")
        _logger.info(f"   pdf_attachment is None: {pdf_attachment is None}")
        if pdf_attachment:
            _logger.info(f"   Attachment ID: {pdf_attachment.id}")
            _logger.info(f"   Attachment exists: {pdf_attachment.exists()}")

        Partner = self.env['res.partner'].sudo()
        ICP = self.env['ir.config_parameter'].sudo()
        DiscussChannel = self.env['discuss.channel'].sudo()

        if 'discuss.channel' not in self.env:
            _logger.warning("   ⚠️ discuss.channel model not available")
            return mail_ids

        odoobot_id = ICP.get_param('mail.odoobot_partner_id')
        odoobot_partner = False
        if odoobot_id:
            odoobot_partner = Partner.browse(int(odoobot_id)).exists()
        if not odoobot_partner:
            odoobot_partner = Partner.search([('name', '=', 'OdooBot')], limit=1)
        if not odoobot_partner:
            _logger.warning("   ⚠️ OdooBot partner not found")
            return mail_ids

        channel = self.env.ref('low_stock_notification.mail_channel_inventory_alerts', raise_if_not_found=False)
        if not channel:
            channel = DiscussChannel.search([('name', '=', 'Inventory Alerts')], limit=1)
        if not channel:
            _logger.warning("   ⚠️ Inventory Alerts channel not found")
            return mail_ids

        _logger.info(f"   Channel: '{channel.name}' (ID: {channel.id})")

        attachment_ids = []
        if pdf_attachment and pdf_attachment.exists():
            attachment_ids = [(4, pdf_attachment.id)]
            attachment_ids = [pdf_attachment.id]
            _logger.info(f"   ✅ Will attach PDF: ID={pdf_attachment.id}")
        else:
            _logger.warning("   ⚠️ No PDF attachment to attach!")

        try:
            from markupsafe import Markup
            alert_type_label = min_quantity_based_on.replace('_', ' ').title()
            product_count = len(low_stock_products)

            if pdf_attachment and pdf_attachment.exists():
                pdf_html_link = f'<a href="/web/content/{pdf_attachment.id}?download=true" target="_blank">📄 Download Report</a>'
            else:
                pdf_html_link = "<i>(No report attached)</i>"

            body_message = Markup(f"""
                <div style="font-family:'Segoe UI',sans-serif;font-size:14px;">
                    <p><strong>⚠️ Low Stock Alert ({alert_type_label})</strong></p>
                    <p>{product_count} product(s) below minimum stock level.</p>
                    <p>📎 {pdf_html_link}</p>
                </div>
            """)

            _logger.info(f"   Posting message with {len(attachment_ids)} attachment(s)...")
            
            channel.with_context(
                mail_create_nosubscribe=True,
                mail_create_nousermessage=True,
            ).message_post(
                body=body_message,
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                author_id=odoobot_partner.id,
                attachment_ids=attachment_ids,
            )

            _logger.info("=" * 80)
            _logger.info(f"✅ STEP 7 COMPLETE: Posted with {len(attachment_ids)} attachment(s)")
            _logger.info("=" * 80)

        except Exception as e:
            _logger.error(f"   ❌ Failed to post message: {e}", exc_info=True)

        _logger.info("\n🏁 FUNCTION END: check_low_stock_and_send_email\n")
        return mail_ids

                
                
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



      