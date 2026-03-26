from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from organizations.models import Membership, Organization
from organizations.utils import ACTIVE_ORG_SESSION_KEY
from users.models import User

from .models import Contact


class ContactCreateViewTests(TestCase):
    def setUp(self):
        self.password = "StrongPass123!"
        self.user = User.objects.create_user(
            email="agent@example.com",
            password=self.password,
            first_name="Agent",
            last_name="User",
        )
        self.org = Organization.objects.create(
            name="Test Org",
            owner=self.user,
            org_type=Organization.OrgType.INDIVIDUAL,
            plan=Organization.Plan.FREE,
        )
        Membership.objects.create(
            user=self.user,
            organization=self.org,
            role=Membership.Role.MEMBER,
            is_active=True,
        )
        self.client.login(username=self.user.email, password=self.password)

    def test_create_contact_saves_and_shows_success_message(self):
        response = self.client.post(
            reverse("contacts:create"),
            data={
                "first_name": "Jane",
                "last_name": "Doe",
                "primary_email": "jane@example.com",
                "primary_phone": "5551112222",
                "contact_type": Contact.ContactType.LEAD,
                "source": Contact.Source.WEBSITE,
                "country": "US",
                "timezone": "America/New_York",
                "language_preference": "en",
                "preferred_contact_method": "email",
                "financing_status": Contact.FinancingStatus.UNKNOWN,
                "timeline_urgency": Contact.TimelineUrgency.UNKNOWN,
            },
            follow=True,
        )

        self.assertEqual(Contact.objects.count(), 1)
        contact = Contact.objects.first()
        self.assertEqual(contact.organization, self.org)
        self.assertEqual(contact.first_name, "Jane")
        self.assertEqual(contact.primary_email, "jane@example.com")
        self.assertTrue(contact.is_active)

        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn('Contact "Jane Doe" was saved.', messages)
        self.assertEqual(response.status_code, 200)

    def test_create_contact_invalid_shows_error_and_does_not_save(self):
        response = self.client.post(
            reverse("contacts:create"),
            data={
                "first_name": "",
                "last_name": "Doe",
            },
            follow=True,
        )

        self.assertEqual(Contact.objects.count(), 0)
        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn(
            "Contact was not saved. Please fix the highlighted fields and try again.",
            messages,
        )
        self.assertContains(response, "Could not save this contact yet.")

    def test_contact_detail_missing_redirects_with_message(self):
        response = self.client.get(reverse("contacts:detail", kwargs={"pk": 99999}), follow=True)
        self.assertRedirects(response, reverse("contacts:list"))
        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn("That contact was not found in your current workspace.", messages)

    def test_create_contact_uses_selected_workspace(self):
        other_org = Organization.objects.create(
            name="Second Org",
            owner=self.user,
            org_type=Organization.OrgType.INDIVIDUAL,
            plan=Organization.Plan.FREE,
        )
        Membership.objects.create(
            user=self.user,
            organization=other_org,
            role=Membership.Role.MEMBER,
            is_active=True,
        )
        session = self.client.session
        session[ACTIVE_ORG_SESSION_KEY] = other_org.pk
        session.save()

        self.client.post(
            reverse("contacts:create"),
            data={
                "first_name": "Workspace",
                "last_name": "Scoped",
                "primary_email": "workspace@example.com",
                "contact_type": Contact.ContactType.LEAD,
                "source": Contact.Source.WEBSITE,
                "timezone": "America/New_York",
                "preferred_contact_method": "email",
                "financing_status": Contact.FinancingStatus.UNKNOWN,
                "timeline_urgency": Contact.TimelineUrgency.UNKNOWN,
            },
            follow=True,
        )

        created = Contact.objects.get(primary_email="workspace@example.com")
        self.assertEqual(created.organization_id, other_org.pk)

        list_response = self.client.get(reverse("contacts:list"))
        self.assertContains(list_response, "Workspace Scoped")
