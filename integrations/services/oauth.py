import json
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import get_random_string

from integrations.models import IntegrationConnection


def _build_redirect_uri(request, provider: str):
    return request.build_absolute_uri(
        reverse("integrations:oauth_callback", kwargs={"provider": provider})
    )


def _post_form(url: str, data: dict):
    payload = urlencode(data).encode("utf-8")
    req = Request(
        url,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise ValueError(f"OAuth token exchange failed ({exc.code}): {body}") from exc
    except URLError as exc:
        raise ValueError(f"OAuth token exchange failed: {exc}") from exc


def get_oauth_start_url(request, provider: str):
    state = get_random_string(32)
    request.session[f"integration_oauth_state_{provider}"] = state
    redirect_uri = _build_redirect_uri(request, provider)

    if provider == IntegrationConnection.Provider.GOOGLE:
        if not settings.GOOGLE_CLIENT_ID:
            raise ValueError("GOOGLE_CLIENT_ID is not configured.")
        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/calendar",
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

    if provider == IntegrationConnection.Provider.OUTLOOK:
        if not settings.MICROSOFT_CLIENT_ID:
            raise ValueError("MICROSOFT_CLIENT_ID is not configured.")
        params = {
            "client_id": settings.MICROSOFT_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "response_mode": "query",
            "scope": "offline_access Calendars.ReadWrite",
            "state": state,
        }
        return f"https://login.microsoftonline.com/common/oauth2/v2.0/authorize?{urlencode(params)}"

    raise ValueError(f"Unsupported provider: {provider}")


def validate_oauth_state(request, provider: str, state: str):
    expected = request.session.get(f"integration_oauth_state_{provider}", "")
    return bool(expected and state and expected == state)


def exchange_code_for_tokens(request, provider: str, code: str):
    redirect_uri = _build_redirect_uri(request, provider)

    if provider == IntegrationConnection.Provider.GOOGLE:
        if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
            raise ValueError("Google OAuth client settings are incomplete.")
        return _post_form(
            "https://oauth2.googleapis.com/token",
            {
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )

    if provider == IntegrationConnection.Provider.OUTLOOK:
        if not settings.MICROSOFT_CLIENT_ID or not settings.MICROSOFT_CLIENT_SECRET:
            raise ValueError("Microsoft OAuth client settings are incomplete.")
        return _post_form(
            "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            {
                "code": code,
                "client_id": settings.MICROSOFT_CLIENT_ID,
                "client_secret": settings.MICROSOFT_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "scope": "offline_access Calendars.ReadWrite",
            },
        )

    raise ValueError(f"Unsupported provider: {provider}")


def refresh_connection_tokens(connection: IntegrationConnection):
    if not connection.refresh_token_encrypted:
        raise ValueError("No refresh token is stored for this connection.")

    if connection.provider == IntegrationConnection.Provider.GOOGLE:
        if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
            raise ValueError("Google OAuth client settings are incomplete.")
        data = _post_form(
            "https://oauth2.googleapis.com/token",
            {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "refresh_token": connection.refresh_token_encrypted,
                "grant_type": "refresh_token",
            },
        )
    elif connection.provider == IntegrationConnection.Provider.OUTLOOK:
        if not settings.MICROSOFT_CLIENT_ID or not settings.MICROSOFT_CLIENT_SECRET:
            raise ValueError("Microsoft OAuth client settings are incomplete.")
        data = _post_form(
            "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            {
                "client_id": settings.MICROSOFT_CLIENT_ID,
                "client_secret": settings.MICROSOFT_CLIENT_SECRET,
                "refresh_token": connection.refresh_token_encrypted,
                "grant_type": "refresh_token",
                "scope": "offline_access Calendars.ReadWrite",
            },
        )
    else:
        raise ValueError(f"Unsupported provider: {connection.provider}")

    apply_token_payload(connection, data, keep_existing_refresh=True)
    return data


def apply_token_payload(connection: IntegrationConnection, token_payload: dict, keep_existing_refresh: bool = False):
    access_token = token_payload.get("access_token", "")
    refresh_token = token_payload.get("refresh_token", "")
    expires_in = int(token_payload.get("expires_in", 0) or 0)

    if not access_token:
        raise ValueError("OAuth response did not include access_token.")

    connection.access_token_encrypted = access_token
    if refresh_token or not keep_existing_refresh:
        connection.refresh_token_encrypted = refresh_token
    connection.token_expires_at = (
        timezone.now() + timedelta(seconds=expires_in)
        if expires_in > 0
        else None
    )
    connection.status = IntegrationConnection.Status.CONNECTED
    connection.last_error = ""
    connection.config = {
        **(connection.config or {}),
        "oauth_callback_received": True,
    }
    connection.save(
        update_fields=[
            "access_token_encrypted",
            "refresh_token_encrypted",
            "token_expires_at",
            "status",
            "last_error",
            "config",
            "updated_at",
        ]
    )


def get_valid_access_token(connection: IntegrationConnection):
    now = timezone.now()
    if connection.access_token_encrypted and (
        not connection.token_expires_at or connection.token_expires_at > now + timedelta(minutes=1)
    ):
        return connection.access_token_encrypted

    refresh_connection_tokens(connection)
    return connection.access_token_encrypted
