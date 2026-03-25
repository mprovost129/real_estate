from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from organizations.models import Membership
from organizations.permissions import require_org_role

from .forms import IntegrationConnectionForm
from .models import IntegrationConnection
from .services.oauth import (
    apply_token_payload,
    exchange_code_for_tokens,
    get_oauth_start_url,
    validate_oauth_state,
)


def _get_org(request):
    membership = (
        request.user.memberships
        .filter(is_active=True)
        .select_related("organization")
        .first()
    )
    return membership.organization if membership else None


@login_required
@require_org_role(Membership.Role.ADMIN, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def integration_settings(request):
    org = _get_org(request)
    connections = IntegrationConnection.objects.for_org(org).order_by("integration_type", "provider", "display_name")

    if request.method == "POST":
        form = IntegrationConnectionForm(request.POST)
        if form.is_valid():
            conn = form.save(commit=False)
            conn.organization = org
            if not conn.status:
                conn.status = IntegrationConnection.Status.DISCONNECTED
            conn.save()
            messages.success(request, f'Integration "{conn}" saved.')
            return redirect("integrations:settings")
    else:
        form = IntegrationConnectionForm()

    return render(
        request,
        "settings/integrations.html",
        {
            "active_section": "integrations",
            "form": form,
            "connections": connections,
        },
    )


@login_required
@require_org_role(Membership.Role.ADMIN, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def integration_toggle_active(request, pk):
    org = _get_org(request)
    conn = get_object_or_404(IntegrationConnection.objects.for_org(org), pk=pk)
    if request.method == "POST":
        conn.is_active = not conn.is_active
        conn.save(update_fields=["is_active", "updated_at"])
        state = "enabled" if conn.is_active else "disabled"
        messages.success(request, f'Integration "{conn}" {state}.')
    return redirect("integrations:settings")


@login_required
@require_org_role(Membership.Role.ADMIN, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def oauth_start(request, provider):
    if provider not in [IntegrationConnection.Provider.GOOGLE, IntegrationConnection.Provider.OUTLOOK]:
        messages.error(request, "Unsupported provider.")
        return redirect("integrations:settings")

    try:
        url = get_oauth_start_url(request, provider=provider)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("integrations:settings")
    return redirect(url)


@login_required
@require_org_role(Membership.Role.ADMIN, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def oauth_callback(request, provider):
    org = _get_org(request)
    error = request.GET.get("error", "")
    if error:
        messages.error(request, f"OAuth error from provider: {error}")
        return redirect("integrations:settings")

    state = request.GET.get("state", "")
    code = request.GET.get("code", "")
    if not validate_oauth_state(request, provider=provider, state=state):
        messages.error(request, "Invalid OAuth state. Please retry connecting.")
        return redirect("integrations:settings")
    request.session.pop(f"integration_oauth_state_{provider}", None)
    if not code:
        messages.error(request, "Provider did not return an authorization code.")
        return redirect("integrations:settings")

    conn, _ = IntegrationConnection.objects.for_org(org).get_or_create(
        integration_type=IntegrationConnection.IntegrationType.CALENDAR,
        provider=provider,
        defaults={
            "organization": org,
            "display_name": f"{provider.title()} Calendar",
            "status": IntegrationConnection.Status.CONNECTING,
            "is_active": True,
        },
    )
    config = dict(conn.config or {})
    config["oauth_callback_received"] = True
    conn.config = config
    conn.status = IntegrationConnection.Status.CONNECTING
    conn.is_active = True
    conn.save(update_fields=["config", "status", "is_active", "updated_at"])

    try:
        token_payload = exchange_code_for_tokens(request, provider=provider, code=code)
        apply_token_payload(conn, token_payload)
        messages.success(request, "Integration connected and tokens saved.")
    except ValueError as exc:
        conn.status = IntegrationConnection.Status.ERROR
        conn.last_error = str(exc)
        conn.save(update_fields=["status", "last_error", "updated_at"])
        messages.error(request, f"OAuth code received, but token exchange failed: {exc}")

    return redirect("integrations:settings")
