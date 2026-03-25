import json
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from compliance.models import AuditEvent, CompliancePolicy


class Command(BaseCommand):
    help = "Monitor retention purge freshness and backlog per organization."

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-stale-days",
            type=int,
            default=14,
            help="Maximum allowed days since last purge before warning/failure.",
        )
        parser.add_argument(
            "--fail-on-warning",
            action="store_true",
            help="Exit non-zero when stale retention is detected.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Output machine-readable JSON.",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        max_stale_days = options["max_stale_days"]
        fail_on_warning = options["fail_on_warning"]
        as_json = options["json"]

        results = []
        stale_count = 0
        for policy in CompliancePolicy.objects.select_related("organization").all():
            cutoff = now - timedelta(days=policy.audit_retention_days)
            purgeable_now = AuditEvent.objects.filter(
                organization=policy.organization,
                created_at__lt=cutoff,
            ).count()
            days_since = None
            if policy.last_purged_at:
                days_since = (now - policy.last_purged_at).days
            is_stale = bool(
                policy.purge_enabled
                and (days_since is None or days_since > max_stale_days)
            )
            if is_stale:
                stale_count += 1
            results.append(
                {
                    "organization_id": policy.organization_id,
                    "organization_name": policy.organization.name,
                    "purge_enabled": policy.purge_enabled,
                    "retention_days": policy.audit_retention_days,
                    "last_purged_at": policy.last_purged_at.isoformat() if policy.last_purged_at else None,
                    "days_since_last_purge": days_since,
                    "purgeable_now": purgeable_now,
                    "is_stale": is_stale,
                }
            )

        summary = {
            "checked_policies": len(results),
            "stale_policies": stale_count,
            "max_stale_days": max_stale_days,
            "results": results,
        }

        if as_json:
            self.stdout.write(json.dumps(summary, indent=2))
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"Checked {len(results)} retention policy/policies; stale={stale_count}."
                )
            )
            for row in results:
                self.stdout.write(
                    f"- {row['organization_name']} | enabled={row['purge_enabled']} | "
                    f"days_since={row['days_since_last_purge']} | purgeable={row['purgeable_now']} | stale={row['is_stale']}"
                )

        if fail_on_warning and stale_count > 0:
            raise CommandError(
                f"Retention monitoring found {stale_count} stale policy/policies."
            )
