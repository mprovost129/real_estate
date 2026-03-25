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


def _recent_duplicate_exists(org, recipient, dedupe_prefix):
    cutoff = timezone.now() - timedelta(hours=2)
    return Notification.objects.filter(
        organization=org,
        recipient=recipient,
        title__startswith=dedupe_prefix,
        created_at__gte=cutoff,
    ).exists()


def _consecutive_failed_runs(run: IntegrationSyncRun, limit: int = 6):
    recent = (
        IntegrationSyncRun.objects
        .for_org(run.organization)
        .filter(run_type=run.run_type, command=run.command)
        .order_by("-started_at")[:limit]
    )
    streak = 0
    for item in recent:
        if item.status == IntegrationSyncRun.RunStatus.FAILED:
            streak += 1
        else:
            break
    return streak


def _severity_for_run(run: IntegrationSyncRun):
    if run.total_items <= 0:
        return None, 0.0, 0

    fail_ratio = (run.failed_items / run.total_items) if run.total_items else 0.0
    failed_streak = _consecutive_failed_runs(run)

    # Critical escalation:
    # - high failure ratio, or
    # - 2+ consecutive fully failed runs.
    if run.status == IntegrationSyncRun.RunStatus.FAILED and failed_streak >= 2:
        return "critical", fail_ratio, failed_streak
    if fail_ratio >= 0.5:
        return "critical", fail_ratio, failed_streak

    # Warning tier:
    # - any full failure, or
    # - partial failures above baseline threshold.
    if run.status == IntegrationSyncRun.RunStatus.FAILED:
        return "warning", fail_ratio, failed_streak
    if run.failed_items > 0 and fail_ratio >= 0.3:
        return "warning", fail_ratio, failed_streak

    return None, fail_ratio, failed_streak


def emit_sync_run_alerts(run: IntegrationSyncRun):
    """
    Create in-app alerts for integration sync health with escalation tiers.

    Severity levels:
    - warning: failed run or >=30% failure ratio
    - critical: >=50% failure ratio or 2+ consecutive failed runs
    """
    severity, fail_ratio, failed_streak = _severity_for_run(run)
    if not severity:
        return 0

    severity_label = "CRITICAL" if severity == "critical" else "Warning"
    dedupe_prefix = f"Integration Sync Alert [{severity_label}]"
    title = (
        f"{dedupe_prefix}: {run.get_run_type_display()} "
        f"({run.failed_items}/{run.total_items} failed)"
    )
    body = (
        f"Command: {run.command or 'n/a'}\n"
        f"Started: {run.started_at:%Y-%m-%d %H:%M:%S}\n"
        f"Status: {run.get_status_display()}\n"
        f"Failed: {run.failed_items} / {run.total_items} ({fail_ratio:.0%})\n"
        f"Consecutive failed runs: {failed_streak}\n"
        "Open Integration Settings for details."
    )

    created = 0
    for membership in _alert_recipients(run.organization):
        user = membership.user
        if _recent_duplicate_exists(run.organization, user, dedupe_prefix):
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
