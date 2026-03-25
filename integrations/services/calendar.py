import json
from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from integrations.models import IntegrationConnection
from integrations.services.oauth import get_valid_access_token, refresh_connection_tokens


@dataclass
class CalendarDescriptor:
    remote_id: str
    name: str
    is_primary: bool = False


@dataclass
class CalendarEventPayload:
    title: str
    start_at: datetime
    end_at: datetime
    description: str = ""
    location: str = ""
    all_day: bool = False


@dataclass
class RemoteCalendarEvent:
    remote_event_id: str
    remote_calendar_id: str
    etag: str = ""
    updated_at: datetime | None = None
    title: str = ""
    is_cancelled: bool = False


class BaseCalendarProvider:
    """Shared interface for calendar providers."""

    def __init__(self, connection: IntegrationConnection):
        self.connection = connection

    def list_calendars(self) -> Iterable[CalendarDescriptor]:
        raise NotImplementedError

    def upsert_event(
        self,
        payload: CalendarEventPayload,
        remote_calendar_id: str,
        remote_event_id: str | None = None,
    ) -> str:
        raise NotImplementedError

    def delete_event(self, remote_calendar_id: str, remote_event_id: str) -> None:
        raise NotImplementedError

    def list_events(
        self,
        remote_calendar_id: str,
        window_start: datetime,
        window_end: datetime,
    ) -> Iterable[RemoteCalendarEvent]:
        raise NotImplementedError


class ConsoleCalendarProvider(BaseCalendarProvider):
    """
    Safe no-op adapter that lets us exercise sync orchestration
    before wiring real provider APIs.
    """

    def list_calendars(self) -> Iterable[CalendarDescriptor]:
        return [CalendarDescriptor(remote_id="primary", name="Primary", is_primary=True)]

    def upsert_event(
        self,
        payload: CalendarEventPayload,
        remote_calendar_id: str,
        remote_event_id: str | None = None,
    ) -> str:
        return remote_event_id or f"stub-{int(payload.start_at.timestamp())}"

    def delete_event(self, remote_calendar_id: str, remote_event_id: str) -> None:
        return None

    def list_events(
        self,
        remote_calendar_id: str,
        window_start: datetime,
        window_end: datetime,
    ) -> Iterable[RemoteCalendarEvent]:
        return []


class GoogleCalendarProvider(BaseCalendarProvider):
    api_base = "https://www.googleapis.com/calendar/v3"

    def _request(self, method: str, path: str, params=None, payload=None, retry_on_auth=True):
        token = get_valid_access_token(self.connection)
        url = f"{self.api_base}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"

        data = None
        headers = {"Authorization": f"Bearer {token}"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
                if not body:
                    return {}
                return json.loads(body)
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            if exc.code == 401 and retry_on_auth:
                # Token may be expired; refresh and retry once.
                refresh_connection_tokens(self.connection)
                return self._request(method, path, params=params, payload=payload, retry_on_auth=False)
            raise ValueError(f"Google Calendar API error ({exc.code}): {body}") from exc
        except URLError as exc:
            raise ValueError(f"Google Calendar API connection failed: {exc}") from exc

    def _event_payload(self, payload: CalendarEventPayload):
        data = {
            "summary": payload.title,
            "description": payload.description,
            "location": payload.location,
        }
        if payload.all_day:
            data["start"] = {"date": payload.start_at.date().isoformat()}
            data["end"] = {"date": payload.end_at.date().isoformat()}
        else:
            data["start"] = {"dateTime": payload.start_at.isoformat()}
            data["end"] = {"dateTime": payload.end_at.isoformat()}
        return data

    def list_calendars(self) -> Iterable[CalendarDescriptor]:
        data = self._request("GET", "/users/me/calendarList")
        rows = []
        for item in data.get("items", []):
            rows.append(
                CalendarDescriptor(
                    remote_id=item.get("id", ""),
                    name=item.get("summary", item.get("id", "Calendar")),
                    is_primary=bool(item.get("primary")),
                )
            )
        return rows

    def upsert_event(
        self,
        payload: CalendarEventPayload,
        remote_calendar_id: str,
        remote_event_id: str | None = None,
    ) -> str:
        calendar_id = quote(remote_calendar_id, safe="")
        body = self._event_payload(payload)

        if remote_event_id:
            event_id = quote(remote_event_id, safe="")
            data = self._request(
                "PUT",
                f"/calendars/{calendar_id}/events/{event_id}",
                payload=body,
            )
        else:
            data = self._request(
                "POST",
                f"/calendars/{calendar_id}/events",
                payload=body,
            )

        event_id = data.get("id", "")
        if not event_id:
            raise ValueError("Google Calendar API did not return an event id.")
        return event_id

    def delete_event(self, remote_calendar_id: str, remote_event_id: str) -> None:
        calendar_id = quote(remote_calendar_id, safe="")
        event_id = quote(remote_event_id, safe="")
        self._request("DELETE", f"/calendars/{calendar_id}/events/{event_id}")

    def list_events(
        self,
        remote_calendar_id: str,
        window_start: datetime,
        window_end: datetime,
    ) -> Iterable[RemoteCalendarEvent]:
        calendar_id = quote(remote_calendar_id, safe="")
        data = self._request(
            "GET",
            f"/calendars/{calendar_id}/events",
            params={
                "timeMin": window_start.astimezone(dt_timezone.utc).isoformat(),
                "timeMax": window_end.astimezone(dt_timezone.utc).isoformat(),
                "singleEvents": "true",
                "showDeleted": "true",
            },
        )
        rows = []
        for item in data.get("items", []):
            event_id = item.get("id", "")
            if not event_id:
                continue
            updated_raw = item.get("updated", "")
            updated_at = None
            if updated_raw:
                updated_at = datetime.fromisoformat(updated_raw.replace("Z", "+00:00"))
            rows.append(
                RemoteCalendarEvent(
                    remote_event_id=event_id,
                    remote_calendar_id=remote_calendar_id,
                    etag=item.get("etag", ""),
                    updated_at=updated_at,
                    title=item.get("summary", ""),
                    is_cancelled=item.get("status") == "cancelled",
                )
            )
        return rows


class OutlookCalendarProvider(BaseCalendarProvider):
    api_base = "https://graph.microsoft.com/v1.0"

    def _request(self, method: str, path: str, params=None, payload=None, retry_on_auth=True):
        token = get_valid_access_token(self.connection)
        url = f"{self.api_base}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"

        data = None
        headers = {"Authorization": f"Bearer {token}"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
                if not body:
                    return {}
                return json.loads(body)
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            if exc.code == 401 and retry_on_auth:
                refresh_connection_tokens(self.connection)
                return self._request(method, path, params=params, payload=payload, retry_on_auth=False)
            raise ValueError(f"Microsoft Graph Calendar API error ({exc.code}): {body}") from exc
        except URLError as exc:
            raise ValueError(f"Microsoft Graph Calendar API connection failed: {exc}") from exc

    @staticmethod
    def _to_graph_datetime(value: datetime):
        as_utc = value.astimezone(dt_timezone.utc)
        return {
            "dateTime": as_utc.strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": "UTC",
        }

    def _event_payload(self, payload: CalendarEventPayload):
        body = {
            "subject": payload.title,
            "body": {
                "contentType": "Text",
                "content": payload.description or "",
            },
            "location": {
                "displayName": payload.location or "",
            },
            "start": self._to_graph_datetime(payload.start_at),
            "end": self._to_graph_datetime(payload.end_at),
            "isAllDay": bool(payload.all_day),
        }
        return body

    def list_calendars(self) -> Iterable[CalendarDescriptor]:
        data = self._request(
            "GET",
            "/me/calendars",
            params={"$select": "id,name,isDefaultCalendar"},
        )
        rows = []
        for item in data.get("value", []):
            rows.append(
                CalendarDescriptor(
                    remote_id=item.get("id", ""),
                    name=item.get("name", "Calendar"),
                    is_primary=bool(item.get("isDefaultCalendar")),
                )
            )
        return rows

    def upsert_event(
        self,
        payload: CalendarEventPayload,
        remote_calendar_id: str,
        remote_event_id: str | None = None,
    ) -> str:
        calendar_id = quote(remote_calendar_id, safe="")
        body = self._event_payload(payload)

        if remote_event_id:
            event_id = quote(remote_event_id, safe="")
            data = self._request(
                "PATCH",
                f"/me/calendars/{calendar_id}/events/{event_id}",
                payload=body,
            )
            return data.get("id", remote_event_id)

        data = self._request(
            "POST",
            f"/me/calendars/{calendar_id}/events",
            payload=body,
        )
        event_id = data.get("id", "")
        if not event_id:
            raise ValueError("Microsoft Graph Calendar API did not return an event id.")
        return event_id

    def delete_event(self, remote_calendar_id: str, remote_event_id: str) -> None:
        calendar_id = quote(remote_calendar_id, safe="")
        event_id = quote(remote_event_id, safe="")
        self._request("DELETE", f"/me/calendars/{calendar_id}/events/{event_id}")

    def list_events(
        self,
        remote_calendar_id: str,
        window_start: datetime,
        window_end: datetime,
    ) -> Iterable[RemoteCalendarEvent]:
        calendar_id = quote(remote_calendar_id, safe="")
        data = self._request(
            "GET",
            f"/me/calendars/{calendar_id}/calendarView",
            params={
                "startDateTime": window_start.astimezone(dt_timezone.utc).isoformat(),
                "endDateTime": window_end.astimezone(dt_timezone.utc).isoformat(),
                "$select": "id,subject,lastModifiedDateTime,isCancelled,@odata.etag",
            },
        )
        rows = []
        for item in data.get("value", []):
            event_id = item.get("id", "")
            if not event_id:
                continue
            updated_raw = item.get("lastModifiedDateTime", "")
            updated_at = None
            if updated_raw:
                updated_at = datetime.fromisoformat(updated_raw.replace("Z", "+00:00"))
            rows.append(
                RemoteCalendarEvent(
                    remote_event_id=event_id,
                    remote_calendar_id=remote_calendar_id,
                    etag=item.get("@odata.etag", ""),
                    updated_at=updated_at,
                    title=item.get("subject", ""),
                    is_cancelled=bool(item.get("isCancelled")),
                )
            )
        return rows


CALENDAR_PROVIDER_MAP = {
    IntegrationConnection.Provider.GOOGLE: GoogleCalendarProvider,
    IntegrationConnection.Provider.OUTLOOK: OutlookCalendarProvider,
    IntegrationConnection.Provider.GENERIC: ConsoleCalendarProvider,
}


def get_calendar_provider(connection: IntegrationConnection) -> BaseCalendarProvider:
    provider_cls = CALENDAR_PROVIDER_MAP.get(connection.provider, ConsoleCalendarProvider)
    return provider_cls(connection)
