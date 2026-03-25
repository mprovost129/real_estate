from datetime import timedelta

from django.utils import timezone

from notifications.models import Notification
from organizations.models import Membership

from integrations.models import IntegrationSyncRun


def _alert_recipients(org):
    return (
        Membership.objects
        .filter(
            organization=org,
            is_active=True,
            role__in=[Membership.Role.OWNER, Membership.Role.ADMIN],
            user__is_active=True,
        )
        .select_related("user")
    )


def _recent_duplicate_exists(org, recipient, title):
    cutoff = timezone.now() - timedelta(hours=2)
    return Notification.objects.filter(
        organization=org,
        recipient=recipient,
        title=title,
        created_at__gte=cutoff,
    ).exists()


def emit_sync_run_alerts(run: IntegrationSyncRun):
    """
    Create in-app alerts for integration sync health.
    Alert on:
    - any fully failed run
    - partial runs with non-trivial error ratio
    """
    if run.total_items <= 0:
        return 0

    fail_ratio = (run.failed_items / run.total_items) if run.total_items else 0
    should_alert = (
        run.status == IntegrationSyncRun.RunStatus.FAILED
        or (run.failed_items > 0 and fail_ratio >= 0.3)
    )
    if not should_alert:
        return 0

    severity_label = "failed" if run.status == IntegrationSyncRun.RunStatus.FAILED else "degraded"
    title = (
        f"Integration sync {severity_label}: "
        f"{run.get_run_type_display()} "
        f"({run.failed_items}/{run.total_items} failed)"
    )
    body = (
        f"Command: {run.command or 'n/a'}\n"
        f"Started: {run.started_at:%Y-%m-%d %H:%M:%S}\n"
        f"Failed: {run.failed_items} / {run.total_items}\n"
        "Open Integration Settings for details."
    )

    created = 0
    for membership in _alert_recipients(run.organization):
        user = membership.user
        if _recent_duplicate_exists(run.organization, user, title):
            continue
        Notification.objects.create(
            organization=run.organization,
            recipient=user,
            notification_type=Notification.Type.GENERAL,
            title=title,
            body=body,
            link="/settings/integrations/",
        )
        created += 1
    return created
