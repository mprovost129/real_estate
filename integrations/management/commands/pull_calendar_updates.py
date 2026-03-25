from django.core.management.base import BaseCommand

from integrations.models import IntegrationConnection
from integrations.services.calendar_pull_sync import pull_calendar_connection_updates


class Command(BaseCommand):
    help = "Pull remote calendar event changes and detect conflicts with local event mappings."

    def add_arguments(self, parser):
        parser.add_argument("--org-id", type=int, default=None)
        parser.add_argument("--connection-id", type=int, default=None)
        parser.add_argument("--days-back", type=int, default=30)
        parser.add_argument("--days-ahead", type=int, default=90)

    def handle(self, *args, **options):
        qs = IntegrationConnection.objects.filter(
            integration_type=IntegrationConnection.IntegrationType.CALENDAR,
            is_active=True,
            status=IntegrationConnection.Status.CONNECTED,
        )
        if options["org_id"]:
            qs = qs.filter(organization_id=options["org_id"])
        if options["connection_id"]:
            qs = qs.filter(pk=options["connection_id"])
        qs = qs.order_by("organization_id", "provider", "id")

        if not qs.exists():
            self.stdout.write("No connected calendar integrations found.")
            return

        for connection in qs:
            self.stdout.write(
                f"Pulling connection={connection.pk} org={connection.organization_id} provider={connection.provider}"
            )
            try:
                result = pull_calendar_connection_updates(
                    connection=connection,
                    days_back=options["days_back"],
                    days_ahead=options["days_ahead"],
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f"result inspected={result.get('inspected', 0)} "
                        f"conflicts={result.get('conflicts', 0)} "
                        f"updated_maps={result.get('updated_maps', 0)} "
                        f"unmatched_remote={result.get('unmatched_remote', 0)}"
                    )
                )
            except NotImplementedError as exc:
                self.stdout.write(self.style.WARNING(f"skipped: {exc}"))
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"pull failed: {exc}"))
