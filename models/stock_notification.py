from odoo import api, models
import base64
import logging

_logger = logging.getLogger(__name__)


class ProductProduct(models.Model):
    _inherit = 'product.product'

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

        # ✅ 3. Select correct mail template
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
        notify_users = self.env['res.users'].search([
            ('notify_user', '=', True),
            ('email', '!=', False),
            ('company_id', '=', company.id),
        ])
        _logger.info(f"   Found {len(notify_users)} users to notify")
        if not notify_users:
            _logger.warning("❌ EARLY EXIT: No users found with notify_user=True")
            return False

        # ✅ 5. Generate PDF once
        _logger.info("\n" + "=" * 80)
        _logger.info("📄 STEP 5: Generating Low Stock Report PDF")
        _logger.info("=" * 80)

        pdf_attachment = None
        try:
            report_ref = self.env.ref('low_stock_notification.action_low_stock_report')
            pdf_bytes, _ = self.env['ir.actions.report']._render_qweb_pdf(
                report_ref.id,  # Odoo 18 expects report ID
                res_ids=[],
                data={}
            )
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
            _logger.info(f"   ✅ PDF created (ID={pdf_attachment.id}, Name={pdf_attachment.name})")

        except Exception as e:
            _logger.error("   ❌ PDF generation failed", exc_info=True)
            pdf_attachment = None

        # ✅ 6. Send Emails
        mail_ids = []
        for user in notify_users:
            try:
                # Provide the low_stock_products list (as produced by the report) in the
                # template context so the mail template can render the products table.
                ctx = {
                    'recipient_name': user.name,
                    'company_name': company.name,
                    'low_stock_count': len(low_stock_products),
                    'notification_based_on': notification_based_on,
                    'low_stock_products': low_stock_products,
                }

                mail_id = template.with_context(**ctx).send_mail(
                    res_id=company.id,
                    force_send=True,
                    email_values={
                        'email_to': user.email,
                        'attachment_ids': [pdf_attachment.id] if pdf_attachment else [],
                    }
                )
                mail_ids.append(mail_id)
                _logger.info(f"✅ Sent to {user.email}")

            except Exception as e:
                _logger.error(f"❌ Failed to send to {user.email}: {e}")

        # ✅ 6.5 Remove duplicate mail.message attachments
        if mail_ids and pdf_attachment:
            self._remove_duplicate_mail_attachments(mail_ids, pdf_attachment.name)

        # ✅ 7. Post to Discuss
        _logger.info("💬 STEP 7: Posting to Discuss")
        Partner = self.env['res.partner'].sudo()
        ICP = self.env['ir.config_parameter'].sudo()
        DiscussChannel = self.env['discuss.channel'].sudo()

        if 'discuss.channel' not in self.env:
            _logger.warning("⚠️ Discuss not installed.")
            return mail_ids

        odoobot_partner = None
        odoobot_id = ICP.get_param('mail.odoobot_partner_id')
        if odoobot_id:
            odoobot_partner = Partner.browse(int(odoobot_id)).exists()
        if not odoobot_partner:
            odoobot_partner = Partner.search([('name', '=', 'OdooBot')], limit=1) or self.env.user.partner_id

        channel = self.env.ref('low_stock_notification.mail_channel_inventory_alerts', raise_if_not_found=False)
        if not channel:
            channel = DiscussChannel.search([('name', '=', 'Inventory Alerts')], limit=1)
        if not channel:
            channel = DiscussChannel.create({
                'name': 'Inventory Alerts',
                'description': 'System-generated low stock alerts.',
                'public': 'private',
                'channel_type': 'channel',
            })

        attachment_ids = [pdf_attachment.id] if pdf_attachment else []
        from markupsafe import Markup

        body = Markup(f"""
            <div style="font-family:'Segoe UI',sans-serif;font-size:14px;">
                <p><strong>⚠️ Low Stock Alert ({min_quantity_based_on.replace('_', ' ').title()})</strong></p>
                <p>{len(low_stock_products)} product(s) below minimum stock level on basis of {(notification_based_on.replace('_', ' ').title())} quantity .</p>
            </div>
        """)

        channel.message_post(
            body=body,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
            author_id=odoobot_partner.id,
            attachment_ids=attachment_ids,
        )

        _logger.info("✅ Posted to Discuss successfully.")
        return mail_ids

    # ✅ Utility to remove duplicate attachments
    def _remove_duplicate_mail_attachments(self, mail_ids, attachment_name):
        Attachment = self.env['ir.attachment']
        Mail = self.env['mail.mail']
        removed = 0
        for mail_id in mail_ids:
            mail = Mail.browse(mail_id)
            mail_msg = getattr(mail, 'mail_message_id', False) or getattr(mail, 'message_id', False)
            if not mail_msg:
                continue
            dups = Attachment.search([
                ('res_model', '=', 'mail.message'),
                ('res_id', '=', mail_msg.id),
                ('name', '=', attachment_name),
            ])
            if dups:
                _logger.info(f"🗑 Removing {len(dups)} duplicate attachment(s): {dups.ids}")
                dups.unlink()
                removed += len(dups)
        _logger.info(f"✅ Duplicate cleanup complete — {removed} removed.")


  