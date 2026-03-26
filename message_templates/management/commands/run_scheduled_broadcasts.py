from django.core.management.base import BaseCommand
from django.utils import timezone

from message_templates.models import OneTimeBroadcast
from message_templates.services import broadcast_is_approved, broadcast_is_due, run_one_time_broadcast


class Command(BaseCommand):
    help = "Process due one-time broadcasts that are scheduled and approved."

    def handle(self, *args, **options):
        due = (
            OneTimeBroadcast.objects
            .filter(status=OneTimeBroadcast.Status.SCHEDULED)
            .order_by("scheduled_for", "id")
        )
        processed = 0
        failed = 0
        for broadcast in due.iterator():
            if not broadcast_is_due(broadcast):
                continue
            if not broadcast_is_approved(broadcast):
                continue
            if broadcast.deliveries.exists():
                continue
            try:
                broadcast.launched_at = timezone.now()
                broadcast.save(update_fields=["launched_at", "updated_at"])
                run_one_time_broadcast(broadcast=broadcast)
                broadcast.completed_at = timezone.now()
                broadcast.save(
                    update_fields=[
                        "recipient_count",
                        "sent_count",
                        "failed_count",
                        "skipped_count",
                        "status",
                        "completed_at",
                        "updated_at",
                    ]
                )
                processed += 1
            except Exception:  # noqa: BLE001
                broadcast.status = OneTimeBroadcast.Status.FAILED
                broadcast.completed_at = timezone.now()
                broadcast.save(update_fields=["status", "completed_at", "updated_at"])
                failed += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Scheduled broadcasts run complete. processed={processed}, failed={failed}"
            )
        )
