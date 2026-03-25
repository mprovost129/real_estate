from django.core.management.base import BaseCommand

from integrations.models import IntegrationConnection, IntegrationSyncRun
from integrations.services.alerts import emit_sync_run_alerts
from integrations.services.calendar_sync import sync_calendar_connection
from integrations.services.retry import sleep_with_backoff
from integrations.services.sync_runs import finish_sync_run, start_sync_run


class Command(BaseCommand):
    help = "Push local tasks/open houses/closings into configured calendar integrations."

    def add_arguments(self, parser):
        parser.add_argument("--org-id", type=int, default=None)
        parser.add_argument("--connection-id", type=int, default=None)
        parser.add_argument("--days-back", type=int, default=7)
        parser.add_argument("--days-ahead", type=int, default=45)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--include-connecting", action="store_true")
        parser.add_argument("--retries", type=int, default=1)
        parser.add_argument("--retry-backoff-seconds", type=float, default=1.0)
        parser.add_argument("--retry-backoff-factor", type=float, default=2.0)
        parser.add_argument("--retry-backoff-max-seconds", type=float, default=30.0)
        parser.add_argument("--max-failures", type=int, default=0)
        parser.add_argument("--fail-on-error", action="store_true")

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

        failures = 0
        successes = 0
        attempts_used = 0
        run = None
        first = qs.first()
        if first:
            run = start_sync_run(
                first.organization,
                IntegrationSyncRun.RunType.CALENDAR_PUSH,
                "sync_calendar_events",
                details={
                    "org_id": options["org_id"],
                    "connection_id": options["connection_id"],
                    "days_back": options["days_back"],
                    "days_ahead": options["days_ahead"],
                    "dry_run": options["dry_run"],
                    "include_connecting": options["include_connecting"],
                    "retries": options["retries"],
                    "retry_backoff_seconds": options["retry_backoff_seconds"],
                    "retry_backoff_factor": options["retry_backoff_factor"],
                    "retry_backoff_max_seconds": options["retry_backoff_max_seconds"],
                },
            )

        for connection in qs:
            self.stdout.write(
                f"Syncing connection={connection.pk} org={connection.organization_id} provider={connection.provider}"
            )
            final_exc = None
            for attempt in range(1, max(1, options["retries"]) + 1):
                attempts_used += 1
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
                    successes += 1
                    final_exc = None
                    break
                except NotImplementedError as exc:
                    self.stdout.write(self.style.WARNING(f"skipped provider implementation pending: {exc}"))
                    successes += 1
                    final_exc = None
                    break
                except Exception as exc:
                    final_exc = exc
                    if attempt < max(1, options["retries"]):
                        delay = sleep_with_backoff(
                            attempt=attempt,
                            base_seconds=options["retry_backoff_seconds"],
                            factor=options["retry_backoff_factor"],
                            max_seconds=options["retry_backoff_max_seconds"],
                        )
                        self.stdout.write(
                            self.style.WARNING(
                                f"attempt {attempt} failed, retrying in {delay:.2f}s: {exc}"
                            )
                        )
                    else:
                        self.stdout.write(self.style.ERROR(f"sync failed: {exc}"))
            if final_exc is not None:
                failures += 1
                if options["max_failures"] and failures >= options["max_failures"]:
                    self.stdout.write(self.style.ERROR("Max failures reached, aborting run."))
                    break

        total = successes + failures
        if run:
            finished = finish_sync_run(
                run,
                total_items=total,
                success_items=successes,
                failed_items=failures,
                details={**(run.details or {}), "attempts_used": attempts_used},
            )
            alert_count = emit_sync_run_alerts(finished)
            if alert_count:
                self.stdout.write(
                    self.style.WARNING(f"Created {alert_count} integration alert notification(s).")
                )

        if failures and options["fail_on_error"]:
            raise SystemExit(1)
