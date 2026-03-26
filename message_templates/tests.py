from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from contacts.models import Contact
from contacts.models import Tag
from django.core import mail
from organizations.models import Membership, Organization
from users.models import User

from .models import AudienceSegment, MessageTemplate, OneTimeBroadcast, OneTimeBroadcastDelivery


@override_settings(
    ONE_TIME_BROADCAST_MAX_RECIPIENTS=100,
    BROADCAST_QUIET_HOURS_ENABLED=False,
)
class OneTimeBroadcastTests(TestCase):
    def setUp(self):
        self.password = "StrongPass123!"
        self.user = User.objects.create_user(
            email="owner@example.com",
            password=self.password,
            first_name="Owner",
            last_name="User",
        )
        self.org = Organization.objects.create(
            name="Acme Realty",
            owner=self.user,
            org_type=Organization.OrgType.INDIVIDUAL,
            plan=Organization.Plan.FREE,
        )
        Membership.objects.create(
            user=self.user,
            organization=self.org,
            role=Membership.Role.OWNER,
            is_active=True,
        )
        self.template = MessageTemplate.objects.create(
            organization=self.org,
            created_by=self.user,
            name="Quick Update",
            template_type=MessageTemplate.TemplateType.EMAIL,
            category=MessageTemplate.Category.GENERAL,
            subject="Hello {{first_name}}",
            body="Market update for {{full_name}}",
        )
        Contact.objects.create(
            organization=self.org,
            first_name="Ava",
            last_name="Buyer",
            primary_email="ava@example.com",
            contact_type=Contact.ContactType.LEAD,
            source=Contact.Source.WEBSITE,
            assigned_to=self.user,
            is_active=True,
        )
        Contact.objects.create(
            organization=self.org,
            first_name="Ben",
            last_name="Seller",
            primary_email="ben@example.com",
            contact_type=Contact.ContactType.LEAD,
            source=Contact.Source.WEBSITE,
            assigned_to=self.user,
            is_active=True,
        )
        self.approver = User.objects.create_user(
            email="approver@example.com",
            password=self.password,
            first_name="Approver",
            last_name="Admin",
        )
        Membership.objects.create(
            user=self.approver,
            organization=self.org,
            role=Membership.Role.ADMIN,
            is_active=True,
        )

    def test_broadcast_launch_creates_delivery_logs(self):
        self.client.login(username=self.user.email, password=self.password)
        response = self.client.post(
            reverse("message_templates:broadcast_create"),
            data={
                "name": "March Blast",
                "channel": "email",
                "template": self.template.pk,
                "filter_contact_type": "",
                "filter_assigned_to": "",
                "confirm_consent": "on",
                "action": "launch",
            },
        )
        self.assertEqual(response.status_code, 302)
        broadcast = OneTimeBroadcast.objects.get(name="March Blast")
        self.assertEqual(broadcast.organization, self.org)
        self.assertEqual(broadcast.recipient_count, 1)
        self.assertEqual(broadcast.sent_count, 1)
        self.assertEqual(OneTimeBroadcastDelivery.objects.filter(broadcast=broadcast).count(), 1)

    def test_broadcast_requires_approval_then_can_be_processed(self):
        self.client.login(username=self.user.email, password=self.password)
        create_response = self.client.post(
            reverse("message_templates:broadcast_create"),
            data={
                "name": "Needs Approval",
                "channel": "email",
                "template": self.template.pk,
                "filter_contact_type": "",
                "filter_assigned_to": "",
                "approval_required": "on",
                "confirm_consent": "on",
                "action": "launch",
            },
        )
        self.assertEqual(create_response.status_code, 302)
        broadcast = OneTimeBroadcast.objects.get(name="Needs Approval")
        self.assertEqual(broadcast.approval_status, OneTimeBroadcast.ApprovalStatus.PENDING)

        self.client.logout()
        self.client.login(username=self.approver.email, password=self.password)
        approve_response = self.client.post(reverse("message_templates:broadcast_approve", kwargs={"pk": broadcast.pk}))
        self.assertEqual(approve_response.status_code, 302)
        broadcast.refresh_from_db()
        self.assertEqual(broadcast.approval_status, OneTimeBroadcast.ApprovalStatus.APPROVED)

        send_response = self.client.post(reverse("message_templates:broadcast_send_now", kwargs={"pk": broadcast.pk}))
        self.assertEqual(send_response.status_code, 302)
        broadcast.refresh_from_db()
        self.assertEqual(broadcast.sent_count, 1)

    def test_scheduled_broadcast_command_processes_due_items(self):
        broadcast = OneTimeBroadcast.objects.create(
            organization=self.org,
            created_by=self.user,
            name="Scheduled Blast",
            channel=OneTimeBroadcast.Channel.EMAIL,
            template=self.template,
            status=OneTimeBroadcast.Status.SCHEDULED,
            scheduled_for=timezone.now() - timedelta(minutes=1),
            approval_required=False,
            approval_status=OneTimeBroadcast.ApprovalStatus.NOT_REQUIRED,
        )
        call_command("run_scheduled_broadcasts")
        broadcast.refresh_from_db()
        self.assertEqual(broadcast.sent_count, 1)

    def test_broadcast_form_rejects_mismatched_template_type(self):
        sms_template = MessageTemplate.objects.create(
            organization=self.org,
            created_by=self.user,
            name="SMS Template",
            template_type=MessageTemplate.TemplateType.SMS,
            category=MessageTemplate.Category.GENERAL,
            body="SMS body",
        )
        self.client.login(username=self.user.email, password=self.password)
        response = self.client.post(
            reverse("message_templates:broadcast_create"),
            data={
                "name": "Invalid Blast",
                "channel": "email",
                "template": sms_template.pk,
                "filter_contact_type": "",
                "filter_assigned_to": "",
                "confirm_consent": "on",
                "action": "preview",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Template type must match the selected channel.")

    def test_segment_filter_limits_broadcast_recipients(self):
        tag = Tag.objects.create(
            organization=self.org,
            name="VIP",
            color="#111111",
        )
        tagged_contact = Contact.objects.get(primary_email="ava@example.com")
        tagged_contact.tags.add(tag)
        segment = AudienceSegment.objects.create(
            organization=self.org,
            name="VIP Segment",
            contact_type=Contact.ContactType.LEAD,
            assigned_to=self.user,
            city="",
            state="",
            zip_code="",
        )
        segment.tags.add(tag)

        self.client.login(username=self.user.email, password=self.password)
        response = self.client.post(
            reverse("message_templates:broadcast_create"),
            data={
                "name": "Segment Blast",
                "channel": "email",
                "template": self.template.pk,
                "filter_segment": segment.pk,
                "filter_contact_type": "",
                "filter_assigned_to": "",
                "confirm_consent": "on",
                "action": "launch",
            },
        )
        self.assertEqual(response.status_code, 302)
        broadcast = OneTimeBroadcast.objects.get(name="Segment Blast")
        self.assertEqual(broadcast.recipient_count, 1)

    def test_save_as_segment_creates_reusable_segment(self):
        tag = Tag.objects.create(
            organization=self.org,
            name="Investors",
            color="#222222",
        )
        self.client.login(username=self.user.email, password=self.password)
        response = self.client.post(
            reverse("message_templates:broadcast_create"),
            data={
                "name": "Save Segment Blast",
                "channel": "email",
                "template": self.template.pk,
                "filter_contact_type": Contact.ContactType.LEAD,
                "filter_assigned_to": self.user.pk,
                "filter_tags": [tag.pk],
                "filter_city": "",
                "filter_state": "",
                "filter_zip_code": "",
                "filter_inactive_days": "",
                "save_as_segment": "on",
                "segment_name": "Investor Leads",
                "confirm_consent": "on",
                "action": "launch",
            },
        )
        self.assertEqual(response.status_code, 302)
        segment = AudienceSegment.objects.get(name="Investor Leads")
        self.assertEqual(segment.organization, self.org)
        self.assertEqual(segment.contact_type, Contact.ContactType.LEAD)
        self.assertEqual(segment.assigned_to, self.user)
        self.assertEqual(segment.tags.count(), 1)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        BROADCAST_REQUIRE_LEGAL_FOOTER=True,
        BROADCAST_EMAIL_LEGAL_FOOTER="LEGAL FOOTER TEST",
    )
    def test_broadcast_appends_legal_footer(self):
        self.client.login(username=self.user.email, password=self.password)
        response = self.client.post(
            reverse("message_templates:broadcast_create"),
            data={
                "name": "Footer Blast",
                "channel": "email",
                "template": self.template.pk,
                "confirm_consent": "on",
                "action": "launch",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(mail.outbox)
        self.assertIn("LEGAL FOOTER TEST", mail.outbox[0].body)

    @override_settings(
        BROADCAST_QUIET_HOURS_ENABLED=True,
        BROADCAST_QUIET_HOURS_START=0,
        BROADCAST_QUIET_HOURS_END=23,
    )
    def test_broadcast_skips_during_quiet_hours(self):
        self.client.login(username=self.user.email, password=self.password)
        response = self.client.post(
            reverse("message_templates:broadcast_create"),
            data={
                "name": "Quiet Hours Blast",
                "channel": "email",
                "template": self.template.pk,
                "confirm_consent": "on",
                "action": "launch",
            },
        )
        self.assertEqual(response.status_code, 302)
        broadcast = OneTimeBroadcast.objects.get(name="Quiet Hours Blast")
        self.assertEqual(broadcast.skipped_count, 2)
        self.assertEqual(broadcast.sent_count, 0)

    def test_broadcast_analytics_view_renders(self):
        broadcast = OneTimeBroadcast.objects.create(
            organization=self.org,
            created_by=self.user,
            name="Analytics Blast",
            channel=OneTimeBroadcast.Channel.EMAIL,
            template=self.template,
            status=OneTimeBroadcast.Status.COMPLETED,
            recipient_count=2,
            sent_count=1,
            failed_count=1,
            skipped_count=0,
        )
        contact = Contact.objects.filter(organization=self.org).first()
        OneTimeBroadcastDelivery.objects.create(
            organization=self.org,
            broadcast=broadcast,
            contact=contact,
            status=OneTimeBroadcastDelivery.Status.SENT,
            detail="sent",
        )
        self.client.login(username=self.user.email, password=self.password)
        response = self.client.get(reverse("message_templates:broadcast_analytics"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Broadcast Analytics")
        self.assertContains(response, "Total Deliveries")
