from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from compliance.audit import log_audit_event
from .models import Membership, Organization
from .permissions import CAPABILITY_LABELS, ROLE_CAPABILITIES, has_capability
from .ops import run_ops_health_check
from .utils import get_active_membership, set_active_org


def _get_membership(request):
    return get_active_membership(request)


# ------------------------------------------------------------------ #
# Organization settings
# ------------------------------------------------------------------ #

@login_required
def org_settings(request):
    membership = _get_membership(request)
    if not membership:
        messages.error(request, "You are not part of an organization.")
        return redirect("dashboard")

    org = membership.organization

    # Only owner / admin can edit
    can_edit = has_capability(membership, "manage_organization_settings")

    from .forms import OrganizationSettingsForm
    form = OrganizationSettingsForm(
        request.POST or None,
        request.FILES or None,
        instance=org,
    )

    if request.method == "POST" and can_edit:
        if form.is_valid():
            form.save()
            messages.success(request, "Organization settings saved.")
            log_audit_event(
                organization=org,
                actor=request.user,
                action="organization.settings_updated",
                entity_type="organization",
                entity_id=org.pk,
                message="Organization settings updated.",
                metadata={"name": org.name},
                request=request,
            )
            return redirect("org_settings")
        # fall through to render with errors

    return render(request, "settings/organization.html", {
        "org": org,
        "membership": membership,
        "form": form,
        "can_edit": can_edit,
        "active_section": "organization",
    })


# ------------------------------------------------------------------ #
# Team management
# ------------------------------------------------------------------ #

@login_required
def team_settings(request):
    membership = _get_membership(request)
    if not membership:
        return redirect("dashboard")

    org = membership.organization
    can_manage = has_capability(membership, "manage_team")

    members = (
        Membership.objects
        .filter(organization=org, is_active=True)
        .select_related("user", "invited_by")
        .order_by("role", "user__last_name", "user__first_name")
    )

    from .forms import InviteMemberForm
    invite_form = InviteMemberForm(request.POST or None) if can_manage else None
    capability_matrix_rows = [
        {
            "role_value": role_value,
            "role_label": role_label,
            "capabilities": ROLE_CAPABILITIES.get(role_value, {}),
        }
        for role_value, role_label in Membership.Role.choices
    ]

    if request.method == "POST" and can_manage and invite_form:
        if invite_form.is_valid():
            email = invite_form.cleaned_data["email"].lower()
            role  = invite_form.cleaned_data["role"]
            first = invite_form.cleaned_data["first_name"]
            last  = invite_form.cleaned_data["last_name"]

            from django.contrib.auth import get_user_model
            User = get_user_model()

            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "is_active": True,
                },
            )

            mem, mem_created = Membership.objects.get_or_create(
                user=user,
                organization=org,
                defaults={
                    "role": role,
                    "is_active": True,
                    "invited_by": request.user,
                },
            )
            if not mem_created:
                # Re-activate if previously removed
                mem.is_active = True
                mem.role = role
                mem.save(update_fields=["is_active", "role"])

            action = "invited" if created else "added"
            messages.success(
                request,
                f'{user.full_name or email} {action} as {mem.get_role_display()}.'
            )
            log_audit_event(
                organization=org,
                actor=request.user,
                action="team.member_added",
                entity_type="membership",
                entity_id=mem.pk,
                message=f'{user.full_name or email} added as {mem.role}.',
                severity="warning",
                metadata={"user_id": user.pk, "email": email, "role": mem.role},
                request=request,
            )
            return redirect("team_settings")

    return render(request, "settings/team.html", {
        "org": org,
        "membership": membership,
        "members": members,
        "invite_form": invite_form,
        "can_manage": can_manage,
        "role_choices": Membership.Role.choices,
        "capability_labels": CAPABILITY_LABELS,
        "capability_matrix_rows": capability_matrix_rows,
        "active_section": "team",
    })


@login_required
def team_member_role(request, pk):
    """Change a member's role (POST only)."""
    membership = _get_membership(request)
    if not membership or not has_capability(membership, "manage_team"):
        messages.error(request, "You don't have permission to do that.")
        return redirect("team_settings")

    target = get_object_or_404(Membership, pk=pk, organization=membership.organization)

    # Cannot demote the org owner
    if target.role == Membership.Role.OWNER and membership.role != Membership.Role.OWNER:
        messages.error(request, "Only the owner can change another owner's role.")
        return redirect("team_settings")

    if request.method == "POST":
        new_role = request.POST.get("role")
        if new_role in dict(Membership.Role.choices):
            target.role = new_role
            target.save(update_fields=["role"])
            messages.success(
                request,
                f'{target.user.full_name} role updated to {target.get_role_display()}.'
            )
            log_audit_event(
                organization=membership.organization,
                actor=request.user,
                action="team.member_role_changed",
                entity_type="membership",
                entity_id=target.pk,
                message=f"{target.user.full_name} role set to {new_role}.",
                severity="warning",
                metadata={"target_user_id": target.user_id, "new_role": new_role},
                request=request,
            )

    return redirect("team_settings")


@login_required
def team_member_remove(request, pk):
    """Deactivate a team member (POST only)."""
    membership = _get_membership(request)
    if not membership or not has_capability(membership, "manage_team"):
        messages.error(request, "You don't have permission to do that.")
        return redirect("team_settings")

    target = get_object_or_404(Membership, pk=pk, organization=membership.organization)

    # Cannot remove yourself or the org owner
    if target.user == request.user:
        messages.error(request, "You cannot remove yourself.")
        return redirect("team_settings")
    if target.role == Membership.Role.OWNER:
        messages.error(request, "The organization owner cannot be removed.")
        return redirect("team_settings")

    if request.method == "POST":
        name = target.user.full_name or target.user.email
        target.is_active = False
        target.save(update_fields=["is_active"])
        messages.success(request, f'{name} removed from the team.')
        log_audit_event(
            organization=membership.organization,
            actor=request.user,
            action="team.member_removed",
            entity_type="membership",
            entity_id=target.pk,
            message=f"{name} removed from team.",
            severity="critical",
            metadata={"target_user_id": target.user_id},
            request=request,
        )

    return redirect("team_settings")


@login_required
def switch_workspace(request):
    if request.method != "POST":
        return redirect("dashboard")

    org_id = request.POST.get("organization_id")
    candidate_next = request.POST.get("next") or request.META.get("HTTP_REFERER")
    next_url = "dashboard"
    if candidate_next and url_has_allowed_host_and_scheme(
        url=candidate_next,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_url = candidate_next

    membership = set_active_org(request, organization_id=org_id)
    if not membership:
        messages.error(request, "Could not switch workspace. You are not a member of that organization.")
        return redirect(next_url)

    messages.success(request, f'Workspace switched to "{membership.organization.name}".')
    return redirect(next_url)


@login_required
def ops_center(request):
    membership = _get_membership(request)
    if not membership:
        return redirect("dashboard")
    if not has_capability(membership, "manage_organization_settings"):
        messages.error(request, "You do not have permission to access Ops Center.")
        return redirect("dashboard")

    org = membership.organization
    report = None
    if request.method == "POST":
        report = run_ops_health_check(organization=org)
        if report["overall"] == "pass":
            messages.success(request, "Ops health check passed.")
        elif report["overall"] == "warn":
            messages.warning(request, "Ops health check completed with warnings.")
        else:
            messages.error(request, "Ops health check found failures.")

    return render(request, "settings/ops_center.html", {
        "org": org,
        "membership": membership,
        "active_section": "ops",
        "report": report,
    })
