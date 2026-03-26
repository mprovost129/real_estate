from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

from .models import Membership
from .utils import get_active_membership as resolve_active_membership


ROLE_RANK = {
    Membership.Role.VIEWER: 1,
    Membership.Role.MEMBER: 2,
    Membership.Role.ADMIN: 3,
    Membership.Role.OWNER: 4,
}

ROLE_CAPABILITIES = {
    Membership.Role.VIEWER: {
        "edit_crm_data": False,
        "manage_workspace_config": False,
        "manage_automations": False,
        "manage_message_templates": False,
        "manage_lead_forms": False,
        "manage_organization_settings": False,
        "manage_team": False,
        "manage_compliance": False,
    },
    Membership.Role.MEMBER: {
        "edit_crm_data": True,
        "manage_workspace_config": False,
        "manage_automations": False,
        "manage_message_templates": False,
        "manage_lead_forms": False,
        "manage_organization_settings": False,
        "manage_team": False,
        "manage_compliance": False,
    },
    Membership.Role.ADMIN: {
        "edit_crm_data": True,
        "manage_workspace_config": True,
        "manage_automations": True,
        "manage_message_templates": True,
        "manage_lead_forms": True,
        "manage_organization_settings": True,
        "manage_team": True,
        "manage_compliance": True,
    },
    Membership.Role.OWNER: {
        "edit_crm_data": True,
        "manage_workspace_config": True,
        "manage_automations": True,
        "manage_message_templates": True,
        "manage_lead_forms": True,
        "manage_organization_settings": True,
        "manage_team": True,
        "manage_compliance": True,
    },
}

CAPABILITY_LABELS = {
    "edit_crm_data": "Create/update CRM and transaction data",
    "manage_workspace_config": "Manage workspace configuration",
    "manage_automations": "Manage automations",
    "manage_message_templates": "Manage templates and campaigns",
    "manage_lead_forms": "Manage public lead forms",
    "manage_organization_settings": "Edit organization settings",
    "manage_team": "Invite/remove team members and change roles",
    "manage_compliance": "Manage audit/compliance policies and logs",
}


def get_active_membership(request, organization=None):
    return resolve_active_membership(request, organization=organization)


def has_min_role(membership, min_role):
    if not membership:
        return False
    return ROLE_RANK.get(membership.role, 0) >= ROLE_RANK.get(min_role, 99)


def get_role_capabilities(role):
    return ROLE_CAPABILITIES.get(role, ROLE_CAPABILITIES[Membership.Role.VIEWER]).copy()


def get_membership_capabilities(membership):
    if not membership:
        return ROLE_CAPABILITIES[Membership.Role.VIEWER].copy()
    return get_role_capabilities(membership.role)


def has_capability(membership, capability):
    return bool(get_membership_capabilities(membership).get(capability, False))


def require_org_role(min_role=Membership.Role.MEMBER, org_resolver=None):
    """
    Decorator for function views that require a minimum org membership role.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            org = org_resolver(request, *args, **kwargs) if org_resolver else None
            membership = get_active_membership(request, org)
            if not has_min_role(membership, min_role):
                messages.error(request, "You do not have permission to perform this action.")
                return redirect("dashboard")
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator


class OrgRoleRequiredMixin:
    """
    Mixin for CBVs. Enforces minimum role on mutating requests.
    """
    required_role = Membership.Role.MEMBER
    enforce_methods = {"POST", "PUT", "PATCH", "DELETE"}

    def dispatch(self, request, *args, **kwargs):
        if request.method in self.enforce_methods:
            org = getattr(self, "org", None)
            membership = getattr(self, "membership", None)
            if membership is None:
                membership = get_active_membership(request, org)
            if not has_min_role(membership, self.required_role):
                messages.error(request, "You do not have permission to perform this action.")
                return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)
