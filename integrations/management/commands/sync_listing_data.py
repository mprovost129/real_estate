from django.core.management.base import BaseCommand

from integrations.models import IntegrationConnection
from integrations.services.listing_sync import sync_listing_for_property
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

            for prop in props:
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
                    else:
                        self.stdout.write(
                            self.style.WARNING(
                                f"property={prop.pk} mls={prop.mls_number} result={result}"
                            )
                        )
                except NotImplementedError as exc:
                    self.stdout.write(self.style.WARNING(f"property={prop.pk} skipped: {exc}"))
                except Exception as exc:
                    self.stdout.write(self.style.ERROR(f"property={prop.pk} sync failed: {exc}"))
