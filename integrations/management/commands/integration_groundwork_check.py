from django.core.management.base import BaseCommand

from integrations.models import IntegrationConnection
from integrations.services.calendar import get_calendar_provider
from integrations.services.listings import get_listing_provider


class Command(BaseCommand):
    help = "Validate integration groundwork adapter wiring."

    def add_arguments(self, parser):
        parser.add_argument("--org-id", type=int, default=None)

    def handle(self, *args, **options):
        qs = IntegrationConnection.objects.filter(is_active=True)
        if options["org_id"]:
            qs = qs.filter(organization_id=options["org_id"])
        qs = qs.order_by("organization_id", "integration_type", "provider")

        total = 0
        for conn in qs:
            total += 1
            if conn.integration_type == IntegrationConnection.IntegrationType.CALENDAR:
                provider = get_calendar_provider(conn)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"[calendar] org={conn.organization_id} provider={conn.provider} adapter={provider.__class__.__name__}"
                    )
                )
            elif conn.integration_type in [
                IntegrationConnection.IntegrationType.MLS,
                IntegrationConnection.IntegrationType.ZILLOW,
            ]:
                provider = get_listing_provider(conn)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"[listing] org={conn.organization_id} provider={conn.provider} adapter={provider.__class__.__name__}"
                    )
                )
            else:
                self.stdout.write(
                    f"[skip] org={conn.organization_id} type={conn.integration_type} provider={conn.provider}"
                )

        if total == 0:
            self.stdout.write("No active integration connections found.")
