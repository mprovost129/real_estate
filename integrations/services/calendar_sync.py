from datetime import datetime, time, timedelta

from django.db import transaction
from django.utils import timezone

from integrations.models import CalendarSyncState, ExternalCalendarEventMap, IntegrationConnection
from integrations.services.calendar import CalendarEventPayload, get_calendar_provider
from open_houses.models import OpenHouse
from tasks.models import Task
from transactions.models import Transaction


def _window_start_end(days_back: int, days_ahead: int):
    today = timezone.localdate()
    return today - timedelta(days=days_back), today + timedelta(days=days_ahead)


def _aware(dt: datetime) -> datetime:
    if timezone.is_aware(dt):
        return dt
    return timezone.make_aware(dt, timezone.get_current_timezone())


def _task_payload(task: Task) -> CalendarEventPayload:
    if task.due_time:
        start_at = datetime.combine(task.due_date, task.due_time)
        end_at = start_at + timedelta(minutes=30)
        all_day = False
    else:
        start_at = datetime.combine(task.due_date, time(9, 0))
        end_at = datetime.combine(task.due_date, time(9, 30))
        all_day = False

    contact_name = task.contact.full_name if task.contact else ""
    title = task.title
    description = task.description or ""
    if contact_name:
        description = f"Contact: {contact_name}\n\n{description}".strip()
    return CalendarEventPayload(
        title=title,
        start_at=_aware(start_at),
        end_at=_aware(end_at),
        description=description,
        all_day=all_day,
    )


def _open_house_payload(open_house: OpenHouse) -> CalendarEventPayload:
    start_at = datetime.combine(open_house.date, open_house.start_time)
    end_at = datetime.combine(open_house.date, open_house.end_time)
    return CalendarEventPayload(
        title=f"Open House: {open_house.display_title}",
        start_at=_aware(start_at),
        end_at=_aware(end_at),
        description=open_house.notes or "",
        location=open_house.display_address,
        all_day=False,
    )


def _closing_payload(tx: Transaction) -> CalendarEventPayload:
    start_at = datetime.combine(tx.closing_date, time(10, 0))
    end_at = start_at + timedelta(hours=1)
    return CalendarEventPayload(
        title=f"Closing: {tx.display_address}",
        start_at=_aware(start_at),
        end_at=_aware(end_at),
        description=tx.notes or "",
        location=tx.display_address,
        all_day=False,
    )


def _get_default_calendar_state(connection: IntegrationConnection):
    state = (
        CalendarSyncState.objects.for_org(connection.organization)
        .filter(connection=connection, sync_enabled=True)
        .order_by("-is_primary", "id")
        .first()
    )
    if state:
        return state

    provider = get_calendar_provider(connection)
    calendars = list(provider.list_calendars())
    if not calendars:
        return None
    primary = next((c for c in calendars if c.is_primary), calendars[0])
    return CalendarSyncState.objects.create(
        organization=connection.organization,
        connection=connection,
        user=None,
        remote_calendar_id=primary.remote_id,
        remote_calendar_name=primary.name,
        is_primary=True,
        sync_enabled=True,
    )


@transaction.atomic
def sync_calendar_connection(
    connection: IntegrationConnection,
    days_back: int = 7,
    days_ahead: int = 45,
    dry_run: bool = False,
):
    if connection.integration_type != IntegrationConnection.IntegrationType.CALENDAR:
        return {"skipped": "not_calendar_connection"}
    if not connection.is_active:
        return {"skipped": "inactive"}

    state = _get_default_calendar_state(connection)
    if not state:
        return {"skipped": "no_calendar_state"}

    provider = get_calendar_provider(connection)
    window_start, window_end = _window_start_end(days_back=days_back, days_ahead=days_ahead)

    now = timezone.now()
    state.last_sync_started_at = now
    state.last_error = ""
    state.save(update_fields=["last_sync_started_at", "last_error", "updated_at"])

    created = 0
    updated = 0
    failed = 0

    event_rows = []
    task_rows = (
        Task.objects.for_org(connection.organization)
        .filter(
            due_date__gte=window_start,
            due_date__lte=window_end,
            status__in=[Task.Status.PENDING, Task.Status.IN_PROGRESS],
        )
        .select_related("contact")
    )
    for task in task_rows:
        event_rows.append((ExternalCalendarEventMap.EventType.TASK, task.pk, _task_payload(task)))

    open_house_rows = (
        OpenHouse.objects.for_org(connection.organization)
        .filter(
            date__gte=window_start,
            date__lte=window_end,
            status__in=[OpenHouse.Status.SCHEDULED, OpenHouse.Status.ACTIVE],
        )
        .select_related("listing")
    )
    for open_house in open_house_rows:
        event_rows.append(
            (ExternalCalendarEventMap.EventType.OPEN_HOUSE, open_house.pk, _open_house_payload(open_house))
        )

    tx_rows = (
        Transaction.objects.for_org(connection.organization)
        .filter(
            closing_date__isnull=False,
            closing_date__gte=window_start,
            closing_date__lte=window_end,
            status__in=[
                Transaction.Status.ACTIVE,
                Transaction.Status.PENDING,
                Transaction.Status.CLEAR_TO_CLOSE,
            ],
        )
        .select_related("linked_property")
    )
    for tx in tx_rows:
        event_rows.append((ExternalCalendarEventMap.EventType.CLOSING, tx.pk, _closing_payload(tx)))

    for event_type, local_object_id, payload in event_rows:
        event_map = ExternalCalendarEventMap.objects.for_org(connection.organization).filter(
            connection=connection,
            event_type=event_type,
            local_object_id=local_object_id,
        ).first()
        remote_event_id = event_map.remote_event_id if event_map else None
        try:
            if not dry_run:
                remote_event_id = provider.upsert_event(
                    payload=payload,
                    remote_calendar_id=state.remote_calendar_id,
                    remote_event_id=remote_event_id,
                )
            if event_map:
                event_map.remote_calendar_id = state.remote_calendar_id
                event_map.remote_event_id = remote_event_id or event_map.remote_event_id
                event_map.last_pushed_at = timezone.now()
                event_map.sync_error = ""
                event_map.save(
                    update_fields=[
                        "remote_calendar_id",
                        "remote_event_id",
                        "last_pushed_at",
                        "sync_error",
                        "updated_at",
                    ]
                )
                updated += 1
            else:
                ExternalCalendarEventMap.objects.create(
                    organization=connection.organization,
                    connection=connection,
                    event_type=event_type,
                    local_object_id=local_object_id,
                    remote_calendar_id=state.remote_calendar_id,
                    remote_event_id=remote_event_id or f"dry-run-{event_type}-{local_object_id}",
                    last_pushed_at=timezone.now() if not dry_run else None,
                )
                created += 1
        except Exception as exc:
            failed += 1
            if event_map:
                event_map.sync_error = str(exc)
                event_map.save(update_fields=["sync_error", "updated_at"])

    finished = timezone.now()
    state.last_sync_finished_at = finished
    state.last_error = "" if failed == 0 else f"{failed} event(s) failed"
    state.save(update_fields=["last_sync_finished_at", "last_error", "updated_at"])
    connection.last_sync_at = finished
    connection.last_error = state.last_error
    connection.status = (
        IntegrationConnection.Status.CONNECTED if failed == 0 else IntegrationConnection.Status.ERROR
    )
    connection.save(update_fields=["last_sync_at", "last_error", "status", "updated_at"])

    return {
        "created": created,
        "updated": updated,
        "failed": failed,
        "window_start": str(window_start),
        "window_end": str(window_end),
    }
