from django.test import TestCase
from django.urls import reverse

from contacts.models import Contact, ContactNote
from organizations.models import Membership, Organization
from tasks.models import Task

from .models import AgentPublicProfile, PublicListingCard, User


class PublicAgentPageTests(TestCase):
    def setUp(self):
        self.password = "StrongPass123!"
        self.user = User.objects.create_user(
            email="agent@example.com",
            password=self.password,
            first_name="Ava",
            last_name="Agent",
        )
        self.org = Organization.objects.create(
            name="Heritage Realty",
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

    def test_public_page_settings_creates_profile(self):
        self.client.login(username=self.user.email, password=self.password)
        response = self.client.get(reverse("public_page_settings"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(AgentPublicProfile.objects.filter(organization=self.org, user=self.user).exists())

    def test_public_agent_page_shows_active_listing_cards_only(self):
        profile = AgentPublicProfile.objects.create(
            organization=self.org,
            user=self.user,
            is_published=True,
            agent_display_name="Ava Agent",
            broker_name="Heritage Realty",
        )
        PublicListingCard.objects.create(
            profile=profile,
            mls_id="123",
            address="1 Main St",
            is_active=True,
        )
        PublicListingCard.objects.create(
            profile=profile,
            mls_id="999",
            address="9 Hidden St",
            is_active=False,
            status=PublicListingCard.ListingStatus.CLOSED,
        )

        response = self.client.get(reverse("public_agent_page", kwargs={"slug": profile.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1 Main St")
        self.assertNotContains(response, "9 Hidden St")

    def test_unpublished_public_page_requires_preview_access(self):
        profile = AgentPublicProfile.objects.create(
            organization=self.org,
            user=self.user,
            is_published=False,
            agent_display_name="Ava Agent",
            broker_name="Heritage Realty",
        )
        public_response = self.client.get(reverse("public_agent_page", kwargs={"slug": profile.slug}))
        self.assertEqual(public_response.status_code, 404)

        self.client.login(username=self.user.email, password=self.password)
        preview_response = self.client.get(reverse("public_agent_page", kwargs={"slug": profile.slug}) + "?preview=1")
        self.assertEqual(preview_response.status_code, 200)
        self.assertContains(preview_response, "Preview mode")

    def test_public_agent_page_inquiry_creates_contact_note_and_task(self):
        profile = AgentPublicProfile.objects.create(
            organization=self.org,
            user=self.user,
            is_published=True,
            agent_display_name="Ava Agent",
            broker_name="Heritage Realty",
        )
        PublicListingCard.objects.create(
            profile=profile,
            mls_id="123456",
            address="10 Test Ln",
            is_active=True,
        )
        response = self.client.post(
            reverse("public_agent_page", kwargs={"slug": profile.slug}),
            data={
                "full_name": "Casey Buyer",
                "email": "casey@example.com",
                "phone": "",
                "target_mls_id": "123456",
                "message": "I want to schedule a showing this week.",
                "company": "",
            },
        )
        self.assertEqual(response.status_code, 302)

        contact = Contact.objects.get(primary_email="casey@example.com")
        self.assertEqual(contact.organization, self.org)
        self.assertEqual(contact.assigned_to, self.user)
        self.assertEqual(contact.source, Contact.Source.WEBSITE)

        note = ContactNote.objects.filter(contact=contact).first()
        self.assertIsNotNone(note)
        self.assertIn("Listing MLS 123456", note.body)

        task = Task.objects.filter(contact=contact).first()
        self.assertIsNotNone(task)
        self.assertEqual(task.assigned_to, self.user)
        self.assertEqual(task.organization, self.org)

    def test_dashboard_contact_count_only_counts_active_contacts(self):
        Contact.objects.create(
            organization=self.org,
            first_name="Active",
            last_name="Contact",
            contact_type=Contact.ContactType.LEAD,
            source=Contact.Source.WEBSITE,
            is_active=True,
        )
        Contact.objects.create(
            organization=self.org,
            first_name="Inactive",
            last_name="Contact",
            contact_type=Contact.ContactType.LEAD,
            source=Contact.Source.WEBSITE,
            is_active=False,
        )
        self.client.login(username=self.user.email, password=self.password)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["contact_count"], 1)

    def test_public_page_settings_manual_listing_fallback_update(self):
        self.client.login(username=self.user.email, password=self.password)
        profile = AgentPublicProfile.objects.create(
            organization=self.org,
            user=self.user,
            is_published=False,
            agent_display_name="Ava Agent",
            broker_name="Heritage Realty",
        )
        card = PublicListingCard.objects.create(
            profile=profile,
            mls_id="MLS001",
            status=PublicListingCard.ListingStatus.ACTIVE,
            is_active=True,
        )
        response = self.client.post(
            reverse("public_page_settings"),
            data={
                "action": "save_listing_card",
                "card_id": card.pk,
                "card-mls_id": "MLS001",
                "card-status": PublicListingCard.ListingStatus.ACTIVE,
                "card-is_active": "on",
                "card-is_featured": "on",
                "card-title": "Fallback Title",
                "card-address": "123 Manual St",
                "card-city": "Boston",
                "card-state": "MA",
                "card-postal_code": "02108",
                "card-price": "750000",
                "card-beds": "3",
                "card-baths": "2",
                "card-sqft": "1500",
                "card-photo_url": "https://example.com/photo.jpg",
                "card-details_url": "https://example.com/listing",
                "card-short_description": "Manual fallback details",
            },
        )
        self.assertEqual(response.status_code, 302)
        card.refresh_from_db()
        self.assertEqual(card.address, "123 Manual St")
        self.assertEqual(card.city, "Boston")
        self.assertEqual(str(card.price), "750000.00")
