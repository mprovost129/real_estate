from datetime import datetime, time, timedelta

from django.utils import timezone

from integrations.models import CalendarSyncState, ExternalCalendarEventMap, IntegrationConnection
from integrations.services.calendar import get_calendar_provider


def _window_bounds(days_back: int, days_ahead: int):
    today = timezone.localdate()
    start = datetime.combine(today - timedelta(days=days_back), time.min)
    end = datetime.combine(today + timedelta(days=days_ahead), time.max)
    return timezone.make_aware(start), timezone.make_aware(end)


def pull_calendar_connection_updates(
    connection: IntegrationConnection,
    days_back: int = 30,
    days_ahead: int = 90,
):
    if connection.integration_type != IntegrationConnection.IntegrationType.CALENDAR:
        return {"skipped": "not_calendar_connection"}
    if not connection.is_active:
        return {"skipped": "inactive"}
    if connection.status != IntegrationConnection.Status.CONNECTED:
        return {"skipped": "not_connected"}

    provider = get_calendar_provider(connection)
    window_start, window_end = _window_bounds(days_back=days_back, days_ahead=days_ahead)

    states = CalendarSyncState.objects.for_org(connection.organization).filter(
        connection=connection,
        sync_enabled=True,
    )
    if not states.exists():
        return {"skipped": "no_calendar_state"}

    inspected = 0
    conflicts = 0
    updated_maps = 0
    unmatched_remote = 0

    for state in states:
        remote_events = provider.list_events(
            remote_calendar_id=state.remote_calendar_id,
            window_start=window_start,
            window_end=window_end,
        )
        for remote_event in remote_events:
            inspected += 1
            event_map = (
                ExternalCalendarEventMap.objects.for_org(connection.organization)
                .filter(connection=connection, remote_event_id=remote_event.remote_event_id)
                .first()
            )
            if not event_map:
                unmatched_remote += 1
                continue

            has_conflict = False
            if (
                remote_event.updated_at
                and event_map.last_pushed_at
                and remote_event.updated_at > (event_map.last_pushed_at + timedelta(minutes=1))
            ):
                has_conflict = True
                conflicts += 1
                event_map.sync_error = (
                    "Remote calendar event changed after last local push. "
                    "Review and resolve manually."
                )
            elif not remote_event.is_cancelled:
                event_map.sync_error = ""

            changed = False
            if remote_event.etag and remote_event.etag != event_map.remote_etag:
                event_map.remote_etag = remote_event.etag
                changed = True
            if has_conflict or changed:
                event_map.save(update_fields=["remote_etag", "sync_error", "updated_at"])
                updated_maps += 1

    connection.config = {
        **(connection.config or {}),
        "pull_last_run_at": timezone.now().isoformat(),
        "pull_last_inspected": inspected,
        "pull_last_conflicts": conflicts,
        "pull_last_unmatched_remote": unmatched_remote,
    }
    connection.last_error = "" if conflicts == 0 else f"{conflicts} conflict(s) detected"
    connection.save(update_fields=["config", "last_error", "updated_at"])

    return {
        "inspected": inspected,
        "conflicts": conflicts,
        "updated_maps": updated_maps,
        "unmatched_remote": unmatched_remote,
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
    }
