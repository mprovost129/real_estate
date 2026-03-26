from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch

from users.models import User

from .models import Membership, Organization
from .utils import ACTIVE_ORG_SESSION_KEY, get_active_membership


class WorkspaceSwitchTests(TestCase):
    def setUp(self):
        self.password = "StrongPass123!"
        self.user = User.objects.create_user(
            email="owner@example.com",
            password=self.password,
            first_name="Owner",
            last_name="User",
        )
        self.org_a = Organization.objects.create(
            name="Org A",
            owner=self.user,
            org_type=Organization.OrgType.INDIVIDUAL,
            plan=Organization.Plan.FREE,
        )
        self.org_b = Organization.objects.create(
            name="Org B",
            owner=self.user,
            org_type=Organization.OrgType.INDIVIDUAL,
            plan=Organization.Plan.FREE,
        )
        Membership.objects.create(user=self.user, organization=self.org_a, role=Membership.Role.OWNER, is_active=True)
        Membership.objects.create(user=self.user, organization=self.org_b, role=Membership.Role.OWNER, is_active=True)
        self.client.login(username=self.user.email, password=self.password)

    def test_switch_workspace_sets_active_org_in_session(self):
        response = self.client.post(
            reverse("switch_workspace"),
            {"organization_id": str(self.org_b.pk), "next": reverse("dashboard")},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session.get(ACTIVE_ORG_SESSION_KEY), self.org_b.pk)

    def test_invalid_workspace_switch_does_not_change_session(self):
        self.client.session[ACTIVE_ORG_SESSION_KEY] = self.org_a.pk
        self.client.session.save()

        outsider_org = Organization.objects.create(
            name="Outsider Org",
            owner=self.user,
            org_type=Organization.OrgType.INDIVIDUAL,
            plan=Organization.Plan.FREE,
        )
        response = self.client.post(
            reverse("switch_workspace"),
            {"organization_id": str(outsider_org.pk), "next": reverse("dashboard")},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session.get(ACTIVE_ORG_SESSION_KEY), self.org_a.pk)

    def test_get_active_membership_uses_session_selection(self):
        session = self.client.session
        session[ACTIVE_ORG_SESSION_KEY] = self.org_b.pk
        session.save()

        request = self.client.get(reverse("dashboard")).wsgi_request
        membership = get_active_membership(request)
        self.assertIsNotNone(membership)
        self.assertEqual(membership.organization_id, self.org_b.pk)

    def test_switch_workspace_rejects_external_next_url(self):
        response = self.client.post(
            reverse("switch_workspace"),
            {"organization_id": str(self.org_b.pk), "next": "https://evil.example/phish"},
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard"))

    def test_switch_workspace_keeps_safe_relative_next_url(self):
        response = self.client.post(
            reverse("switch_workspace"),
            {"organization_id": str(self.org_b.pk), "next": reverse("contacts:list")},
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("contacts:list"))

    def test_ops_center_renders_for_authorized_user(self):
        response = self.client.get(reverse("ops_center"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ops Center")

    @patch("organizations.views.run_ops_health_check")
    def test_ops_center_post_runs_health_suite(self, mock_run):
        mock_run.return_value = {
            "overall": "pass",
            "counts": {"pass": 5, "warn": 0, "fail": 0, "total": 5},
            "results": [],
            "ran_at": None,
        }
        response = self.client.post(reverse("ops_center"), follow=True)
        self.assertEqual(response.status_code, 200)
        mock_run.assert_called_once()
