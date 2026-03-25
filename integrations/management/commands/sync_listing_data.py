from django.core.management.base import BaseCommand

from integrations.models import IntegrationConnection, IntegrationSyncRun
from integrations.services.alerts import emit_sync_run_alerts
from integrations.services.listing_sync import sync_listing_for_property
from integrations.services.retry import sleep_with_backoff
from integrations.services.sync_runs import finish_sync_run, start_sync_run
from properties.models import Property


class Command(BaseCommand):
    help = "Sync MLS/Zillow listing data into listing sync state and optional property fields/photos."

    def add_arguments(self, parser):
        parser.add_argument("--org-id", type=int, default=None)
        parser.add_argument("--connection-id", type=int, default=None)
        parser.add_argument("--property-id", type=int, default=None)
        parser.add_argument("--mls", type=str, default="")
        parser.add_argument("--overwrite", action="store_true")
        parser.add_argument("--import-photos", action="store_true")
        parser.add_argument("--photo-limit", type=int, default=5)
        parser.add_argument("--retries", type=int, default=1)
        parser.add_argument("--retry-backoff-seconds", type=float, default=1.0)
        parser.add_argument("--retry-backoff-factor", type=float, default=2.0)
        parser.add_argument("--retry-backoff-max-seconds", type=float, default=30.0)
        parser.add_argument("--max-failures", type=int, default=0)
        parser.add_argument("--fail-on-error", action="store_true")

    def handle(self, *args, **options):
        connections = IntegrationConnection.objects.filter(
            integration_type__in=[
                IntegrationConnection.IntegrationType.MLS,
                IntegrationConnection.IntegrationType.ZILLOW,
            ],
            is_active=True,
        ).order_by("organization_id", "provider", "id")
        if options["org_id"]:
            connections = connections.filter(organization_id=options["org_id"])
        if options["connection_id"]:
            connections = connections.filter(pk=options["connection_id"])

        if not connections.exists():
            self.stdout.write("No active MLS/Zillow integration connections found.")
            return

        global_failures = 0
        for conn in connections:
            props = Property.objects.for_org(conn.organization).filter(is_active=True).exclude(mls_number="")
            if options["property_id"]:
                props = props.filter(pk=options["property_id"])
            if options["mls"]:
                props = props.filter(mls_number__iexact=options["mls"].strip())

            self.stdout.write(
                f"Syncing listings for connection={conn.pk} org={conn.organization_id} provider={conn.provider}"
            )
            if not props.exists():
                self.stdout.write("No matching properties for this connection.")
                continue

            run = start_sync_run(
                conn.organization,
                IntegrationSyncRun.RunType.LISTING_SYNC,
                "sync_listing_data",
                details={
                    "org_id": options["org_id"],
                    "connection_id": conn.pk,
                    "property_id": options["property_id"],
                    "mls": options["mls"],
                    "overwrite": options["overwrite"],
                    "import_photos": options["import_photos"],
                    "photo_limit": options["photo_limit"],
                    "retries": options["retries"],
                    "retry_backoff_seconds": options["retry_backoff_seconds"],
                    "retry_backoff_factor": options["retry_backoff_factor"],
                    "retry_backoff_max_seconds": options["retry_backoff_max_seconds"],
                },
            )
            successes = 0
            failures = 0
            attempts_used = 0

            for prop in props:
                final_exc = None
                for attempt in range(1, max(1, options["retries"]) + 1):
                    attempts_used += 1
                    try:
                        result = sync_listing_for_property(
                            connection=conn,
                            prop=prop,
                            overwrite=options["overwrite"],
                            import_photos=options["import_photos"],
                            photo_limit=options["photo_limit"],
                        )
                        if result.get("status") == "synced":
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"property={prop.pk} mls={prop.mls_number} "
                                    f"changed={result.get('property_changed')} "
                                    f"photos+={result.get('photos_imported', 0)} "
                                    f"photos_failed={result.get('photos_failed', 0)}"
                                )
                            )
                            successes += 1
                        else:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"property={prop.pk} mls={prop.mls_number} result={result}"
                                )
                            )
                            failures += 1
                            global_failures += 1
                        final_exc = None
                        break
                    except NotImplementedError as exc:
                        self.stdout.write(self.style.WARNING(f"property={prop.pk} skipped: {exc}"))
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
                                    f"property={prop.pk} attempt {attempt} failed, retrying in {delay:.2f}s: {exc}"
                                )
                            )
                        else:
                            self.stdout.write(self.style.ERROR(f"property={prop.pk} sync failed: {exc}"))
                if final_exc is not None:
                    failures += 1
                    global_failures += 1
                    if options["max_failures"] and global_failures >= options["max_failures"]:
                        self.stdout.write(self.style.ERROR("Max failures reached, aborting run."))
                        break

            total = successes + failures
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

            if options["max_failures"] and global_failures >= options["max_failures"]:
                break

        if global_failures and options["fail_on_error"]:
            raise SystemExit(1)
