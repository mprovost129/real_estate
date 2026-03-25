from .permissions import get_membership_capabilities


def current_org(request):
    """
    Attaches the user's active organization and membership to every
    template context. Views can override by passing their own values.
    """
    if not request.user.is_authenticated:
        return {"current_org": None, "current_membership": None, "org_capabilities": {}}

    membership = (
        request.user.memberships
        .filter(is_active=True)
        .select_related("organization")
        .first()
    )
    if not membership:
        return {"current_org": None, "current_membership": None, "org_capabilities": {}}

    return {
        "current_org": membership.organization,
        "current_membership": membership,
        "org_capabilities": get_membership_capabilities(membership),
    }
