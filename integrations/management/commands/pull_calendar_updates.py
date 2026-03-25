from django.core.management.base import BaseCommand

from integrations.models import IntegrationConnection, IntegrationSyncRun
from integrations.services.calendar_pull_sync import pull_calendar_connection_updates
from integrations.services.sync_runs import finish_sync_run, start_sync_run


class Command(BaseCommand):
    help = "Pull remote calendar event changes and detect conflicts with local event mappings."

    def add_arguments(self, parser):
        parser.add_argument("--org-id", type=int, default=None)
        parser.add_argument("--connection-id", type=int, default=None)
        parser.add_argument("--days-back", type=int, default=30)
        parser.add_argument("--days-ahead", type=int, default=90)
        parser.add_argument("--retries", type=int, default=1)
        parser.add_argument("--max-failures", type=int, default=0)
        parser.add_argument("--fail-on-error", action="store_true")

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

        failures = 0
        successes = 0
        attempts_used = 0
        run = None
        first = qs.first()
        if first:
            run = start_sync_run(
                first.organization,
                IntegrationSyncRun.RunType.CALENDAR_PULL,
                "pull_calendar_updates",
                details={
                    "org_id": options["org_id"],
                    "connection_id": options["connection_id"],
                    "days_back": options["days_back"],
                    "days_ahead": options["days_ahead"],
                    "retries": options["retries"],
                },
            )

        for connection in qs:
            self.stdout.write(
                f"Pulling connection={connection.pk} org={connection.organization_id} provider={connection.provider}"
            )
            final_exc = None
            for attempt in range(1, max(1, options["retries"]) + 1):
                attempts_used += 1
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
                    successes += 1
                    final_exc = None
                    break
                except NotImplementedError as exc:
                    self.stdout.write(self.style.WARNING(f"skipped: {exc}"))
                    successes += 1
                    final_exc = None
                    break
                except Exception as exc:
                    final_exc = exc
                    if attempt < max(1, options["retries"]):
                        self.stdout.write(self.style.WARNING(f"attempt {attempt} failed, retrying: {exc}"))
                    else:
                        self.stdout.write(self.style.ERROR(f"pull failed: {exc}"))
            if final_exc is not None:
                failures += 1
                if options["max_failures"] and failures >= options["max_failures"]:
                    self.stdout.write(self.style.ERROR("Max failures reached, aborting run."))
                    break

        total = successes + failures
        if run:
            finish_sync_run(
                run,
                total_items=total,
                success_items=successes,
                failed_items=failures,
                details={**(run.details or {}), "attempts_used": attempts_used},
            )

        if failures and options["fail_on_error"]:
            raise SystemExit(1)
