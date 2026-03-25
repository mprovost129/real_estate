from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from compliance.models import AuditEvent, CompliancePolicy


class Command(BaseCommand):
    help = "Purge audit events older than each organization's retention policy."

    def handle(self, *args, **options):
        now = timezone.now()
        total_deleted = 0
        policy_count = 0

        for policy in CompliancePolicy.objects.select_related("organization").all():
            if not policy.purge_enabled:
                continue
            policy_count += 1
            cutoff = now - timedelta(days=policy.audit_retention_days)
            deleted, _ = AuditEvent.objects.filter(
                organization=policy.organization,
                created_at__lt=cutoff,
            ).delete()
            total_deleted += deleted
            policy.last_purged_at = now
            policy.save(update_fields=["last_purged_at", "updated_at"])
            AuditEvent.objects.create(
                organization=policy.organization,
                actor=None,
                action="compliance.audit_purged",
                entity_type="compliance_policy",
                entity_id=str(policy.pk),
                severity=AuditEvent.Severity.WARNING,
                message=f"Automated purge removed {deleted} event(s).",
                metadata={
                    "deleted": deleted,
                    "retention_days": policy.audit_retention_days,
                    "cutoff": cutoff.isoformat(),
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Purged {total_deleted} audit event(s) across {policy_count} organization policy/policies."
            )
        )
