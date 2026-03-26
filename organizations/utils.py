from .models import Membership


ACTIVE_ORG_SESSION_KEY = "active_org_id"


def get_active_membership(request, organization=None):
    """
    Resolve the user's active membership.
    - If organization is provided, returns membership for that org.
    - Otherwise uses the session-selected org when available.
    """
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return None

    qs = (
        request.user.memberships
        .filter(is_active=True)
        .select_related("organization")
        .order_by("organization__name", "organization_id", "id")
    )

    if organization is not None:
        org_id = getattr(organization, "pk", organization)
        return qs.filter(organization_id=org_id).first()

    cached = getattr(request, "_active_membership_cache", None)
    if cached is not None:
        return cached

    selected_org_id = request.session.get(ACTIVE_ORG_SESSION_KEY)
    if selected_org_id:
        membership = qs.filter(organization_id=selected_org_id).first()
        if membership:
            request._active_membership_cache = membership
            request._current_org = membership.organization
            return membership
        request.session.pop(ACTIVE_ORG_SESSION_KEY, None)

    membership = qs.first()
    if membership:
        request.session[ACTIVE_ORG_SESSION_KEY] = membership.organization_id
        request._active_membership_cache = membership
        request._current_org = membership.organization
    return membership


def get_active_org(request):
    membership = get_active_membership(request)
    return membership.organization if membership else None


def set_active_org(request, organization_id):
    membership = get_active_membership(request, organization=organization_id)
    if not membership:
        return None
    request.session[ACTIVE_ORG_SESSION_KEY] = membership.organization_id
    request._active_membership_cache = membership
    request._current_org = membership.organization
    return membership
