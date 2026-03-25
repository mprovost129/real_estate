from django.utils import timezone

from integrations.models import IntegrationSyncRun


def start_sync_run(org, run_type: str, command: str, details: dict | None = None):
    return IntegrationSyncRun.objects.create(
        organization=org,
        run_type=run_type,
        command=command,
        started_at=timezone.now(),
        details=details or {},
    )


def finish_sync_run(
    run: IntegrationSyncRun,
    *,
    total_items: int,
    success_items: int,
    failed_items: int,
    details: dict | None = None,
):
    if failed_items == 0:
        status = IntegrationSyncRun.RunStatus.SUCCESS
    elif success_items > 0:
        status = IntegrationSyncRun.RunStatus.PARTIAL
    else:
        status = IntegrationSyncRun.RunStatus.FAILED

    run.status = status
    run.finished_at = timezone.now()
    run.total_items = total_items
    run.success_items = success_items
    run.failed_items = failed_items
    run.details = details or run.details
    run.save(
        update_fields=[
            "status",
            "finished_at",
            "total_items",
            "success_items",
            "failed_items",
            "details",
            "updated_at",
        ]
    )
    return run
