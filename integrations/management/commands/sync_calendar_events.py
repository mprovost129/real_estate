from django.core.management.base import BaseCommand

from integrations.models import IntegrationConnection
from integrations.services.calendar_sync import sync_calendar_connection


class Command(BaseCommand):
    help = "Push local tasks/open houses/closings into configured calendar integrations."

    def add_arguments(self, parser):
        parser.add_argument("--org-id", type=int, default=None)
        parser.add_argument("--connection-id", type=int, default=None)
        parser.add_argument("--days-back", type=int, default=7)
        parser.add_argument("--days-ahead", type=int, default=45)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--include-connecting", action="store_true")

    def handle(self, *args, **options):
        qs = IntegrationConnection.objects.filter(
            integration_type=IntegrationConnection.IntegrationType.CALENDAR,
            is_active=True,
            status=IntegrationConnection.Status.CONNECTED,
        )
        if options["include_connecting"]:
            qs = IntegrationConnection.objects.filter(
                integration_type=IntegrationConnection.IntegrationType.CALENDAR,
                is_active=True,
                status__in=[
                    IntegrationConnection.Status.CONNECTED,
                    IntegrationConnection.Status.CONNECTING,
                ],
            )
        if options["org_id"]:
            qs = qs.filter(organization_id=options["org_id"])
        if options["connection_id"]:
            qs = qs.filter(pk=options["connection_id"])
        qs = qs.order_by("organization_id", "provider", "id")

        if not qs.exists():
            self.stdout.write("No active calendar integration connections found.")
            return

        for connection in qs:
            self.stdout.write(
                f"Syncing connection={connection.pk} org={connection.organization_id} provider={connection.provider}"
            )
            try:
                result = sync_calendar_connection(
                    connection=connection,
                    days_back=options["days_back"],
                    days_ahead=options["days_ahead"],
                    dry_run=options["dry_run"],
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f"result created={result.get('created', 0)} "
                        f"updated={result.get('updated', 0)} failed={result.get('failed', 0)} "
                        f"window={result.get('window_start')}..{result.get('window_end')}"
                    )
                )
            except NotImplementedError as exc:
                self.stdout.write(
                    self.style.WARNING(
                        f"skipped provider implementation pending: {exc}"
                    )
                )
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"sync failed: {exc}"))
