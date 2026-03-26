from django.test import TestCase

from organizations.models import Membership, Organization
from users.models import User

from .models import IntegrationConnection
from .services.listings import MlsIdxProvider


class MlsIdxProviderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="mls@example.com",
            password="StrongPass123!",
            first_name="MLS",
            last_name="Agent",
        )
        self.org = Organization.objects.create(
            name="MLS Org",
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

    def test_parse_mls_grid_odata_payload(self):
        conn = IntegrationConnection.objects.create(
            organization=self.org,
            integration_type=IntegrationConnection.IntegrationType.MLS,
            provider=IntegrationConnection.Provider.MLS_GENERIC,
            status=IntegrationConnection.Status.CONNECTED,
            is_active=True,
            config={"originating_system_name": "actris"},
        )
        provider = MlsIdxProvider(conn)

        provider._fetch_json = lambda url: {
            "value": [
                {
                    "ListingId": "123456",
                    "UnparsedAddress": "123 Main St",
                    "City": "Austin",
                    "StateOrProvince": "TX",
                    "PostalCode": "78701",
                    "StandardStatus": "Active",
                    "ListPrice": 450000,
                    "MlgCanView": True,
                    "MlgCanUse": ["IDX", "VOW"],
                    "Media": [{"MediaURL": "https://example.com/photo1.jpg"}],
                }
            ]
        }
        record = provider.fetch_by_mls("123456")
        self.assertIsNotNone(record)
        self.assertEqual(record.mls_number, "123456")
        self.assertEqual(record.address, "123 Main St")
        self.assertEqual(record.city, "Austin")
        self.assertEqual(record.state, "TX")
        self.assertEqual(record.status, "active")
        self.assertEqual(record.price, 450000)
        self.assertEqual(record.mlg_can_view, True)
        self.assertIn("IDX", record.mlg_can_use)
        self.assertEqual(record.photo_urls, ["https://example.com/photo1.jpg"])

    def test_builds_mls_grid_lookup_url_when_template_missing(self):
        conn = IntegrationConnection.objects.create(
            organization=self.org,
            integration_type=IntegrationConnection.IntegrationType.MLS,
            provider=IntegrationConnection.Provider.MLS_GENERIC,
            status=IntegrationConnection.Status.CONNECTED,
            is_active=True,
            config={"originating_system_name": "actris"},
        )
        provider = MlsIdxProvider(conn)
        url = provider._lookup_url("123456")
        self.assertIn("api.mlsgrid.com/v2/Property", url)
        self.assertIn("OriginatingSystemName", url)
        self.assertIn("actris", url)
        self.assertIn("ListingId", url)
