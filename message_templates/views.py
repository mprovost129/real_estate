from django.contrib import messages
from datetime import timedelta
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.conf import settings
from django.db.models import Count, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.db.models.functions import TruncDate
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from compliance.audit import log_audit_event
from organizations.models import Membership
from organizations.permissions import OrgRoleRequiredMixin, require_org_role
from organizations.utils import get_active_membership
from .forms import DripCampaignForm, DripCampaignStepForm, OneTimeBroadcastForm
from .models import (
    AudienceSegment,
    CampaignEnrollment,
    CampaignSendLog,
    DripCampaign,
    DripCampaignStep,
    MessageTemplate,
    OneTimeBroadcast,
    OneTimeBroadcastDelivery,
)
from .services import get_broadcast_recipients, run_one_time_broadcast
from .services import broadcast_is_approved


def _get_org(request):
    m = get_active_membership(request)
    return m.organization if m else None


class OrgMixin(LoginRequiredMixin):
    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        m = get_active_membership(request)
        self.org = m.organization if m else None

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["org"] = self.org
        return ctx


# ------------------------------------------------------------------ #
# List
# ------------------------------------------------------------------ #

class TemplateListView(OrgMixin, ListView):
    template_name = "message_templates/list.html"
    context_object_name = "templates"

    def get_queryset(self):
        qs = MessageTemplate.objects.for_org(self.org).filter(is_active=True)
        tab = self.request.GET.get("tab", "email")
        qs = qs.filter(template_type=tab)
        cat = self.request.GET.get("category", "")
        if cat:
            qs = qs.filter(category=cat)
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(name__icontains=q)
        return qs.order_by("category", "name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["tab"] = self.request.GET.get("tab", "email")
        ctx["category"] = self.request.GET.get("category", "")
        ctx["q"] = self.request.GET.get("q", "")
        base = MessageTemplate.objects.for_org(self.org).filter(is_active=True)
        ctx["count_email"]       = base.filter(template_type="email").count()
        ctx["count_sms"]         = base.filter(template_type="sms").count()
        ctx["count_call_script"] = base.filter(template_type="call_script").count()
        ctx["categories"]        = MessageTemplate.Category.choices
        return ctx


# ------------------------------------------------------------------ #
# Detail / Preview
# ------------------------------------------------------------------ #

class TemplateDetailView(OrgMixin, DetailView):
    template_name = "message_templates/detail.html"
    context_object_name = "tmpl"

    def get_object(self):
        return get_object_or_404(
            MessageTemplate.objects.for_org(self.org),
            pk=self.kwargs["pk"],
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        tmpl = self.object
        ctx["preview_body"]    = tmpl.preview()
        ctx["preview_subject"] = tmpl.preview_subject()
        return ctx


# ------------------------------------------------------------------ #
# Create / Update
# ------------------------------------------------------------------ #

class TemplateCreateView(OrgRoleRequiredMixin, OrgMixin, CreateView):
    required_role = Membership.Role.ADMIN
    template_name = "message_templates/template_form.html"
    model = MessageTemplate
    fields = ["name", "template_type", "category", "subject", "body"]

    def get_initial(self):
        initial = super().get_initial()
        tab = self.request.GET.get("tab", "email")
        initial["template_type"] = tab
        return initial

    def form_valid(self, form):
        tmpl = form.save(commit=False)
        tmpl.organization = self.org
        tmpl.created_by   = self.request.user
        tmpl.save()
        messages.success(self.request, f'Template "{tmpl.name}" created.')
        return redirect("message_templates:detail", pk=tmpl.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "New Template"
        ctx["merge_fields"] = MERGE_FIELDS
        return ctx


class TemplateUpdateView(OrgRoleRequiredMixin, OrgMixin, UpdateView):
    required_role = Membership.Role.ADMIN
    template_name = "message_templates/template_form.html"
    model = MessageTemplate
    fields = ["name", "template_type", "category", "subject", "body"]

    def get_object(self):
        return get_object_or_404(MessageTemplate.objects.for_org(self.org), pk=self.kwargs["pk"])

    def form_valid(self, form):
        tmpl = form.save()
        messages.success(self.request, f'Template "{tmpl.name}" updated.')
        return redirect("message_templates:detail", pk=tmpl.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Edit Template"
        ctx["merge_fields"] = MERGE_FIELDS
        return ctx


# ------------------------------------------------------------------ #
# Duplicate
# ------------------------------------------------------------------ #

@login_required
@require_org_role(Membership.Role.ADMIN, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def template_duplicate(request, pk):
    org  = _get_org(request)
    tmpl = get_object_or_404(MessageTemplate.objects.for_org(org), pk=pk)
    tmpl.pk   = None
    tmpl.name = f"Copy of {tmpl.name}"
    tmpl.organization = org
    tmpl.created_by   = request.user
    tmpl.save()
    messages.success(request, f'Template duplicated as "{tmpl.name}".')
    return redirect("message_templates:update", pk=tmpl.pk)


# ------------------------------------------------------------------ #
# Delete
# ------------------------------------------------------------------ #

@login_required
@require_org_role(Membership.Role.ADMIN, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def template_delete(request, pk):
    org  = _get_org(request)
    tmpl = get_object_or_404(MessageTemplate.objects.for_org(org), pk=pk)

    if request.method == "POST":
        name = tmpl.name
        tmpl.is_active = False
        tmpl.save(update_fields=["is_active"])
        messages.success(request, f'Template "{name}" deleted.')
        log_audit_event(
            organization=org,
            actor=request.user,
            action="template.deactivated",
            entity_type="message_template",
            entity_id=tmpl.pk,
            severity="warning",
            message=f'Template "{name}" deactivated.',
            request=request,
        )
        return redirect("message_templates:list")

    return render(request, "message_templates/template_confirm_delete.html", {"tmpl": tmpl})


# ------------------------------------------------------------------ #
# AJAX preview
# ------------------------------------------------------------------ #

@login_required
def template_preview_ajax(request, pk):
    """Return rendered preview of body/subject as JSON (for live preview in form)."""
    org  = _get_org(request)
    tmpl = get_object_or_404(MessageTemplate.objects.for_org(org), pk=pk)
    return JsonResponse({
        "subject": tmpl.preview_subject(),
        "body":    tmpl.preview(),
    })


# ------------------------------------------------------------------ #
# Merge field reference
# ------------------------------------------------------------------ #

MERGE_FIELDS = [
    ("{{first_name}}",   "Contact's first name"),
    ("{{last_name}}",    "Contact's last name"),
    ("{{full_name}}",    "Contact's full name"),
    ("{{address}}",      "Property address"),
    ("{{agent_name}}",   "Agent's name"),
    ("{{closing_date}}", "Closing date"),
    ("{{price}}",        "Purchase/listing price"),
]


# ------------------------------------------------------------------ #
# Campaigns
# ------------------------------------------------------------------ #

class CampaignListView(OrgMixin, ListView):
    template_name = "message_templates/campaign_list.html"
    context_object_name = "campaigns"

    def get_queryset(self):
        qs = DripCampaign.objects.for_org(self.org).order_by("name")
        status = self.request.GET.get("status", "")
        if status == "active":
            qs = qs.filter(is_active=True)
        elif status == "inactive":
            qs = qs.filter(is_active=False)
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(name__icontains=q)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        base = DripCampaign.objects.for_org(self.org)
        ctx["q"] = self.request.GET.get("q", "")
        ctx["status"] = self.request.GET.get("status", "")
        ctx["count_active"] = base.filter(is_active=True).count()
        ctx["count_inactive"] = base.filter(is_active=False).count()
        return ctx


class CampaignCreateView(OrgRoleRequiredMixin, OrgMixin, CreateView):
    required_role = Membership.Role.ADMIN
    template_name = "message_templates/campaign_form.html"
    form_class = DripCampaignForm

    def form_valid(self, form):
        campaign = form.save(commit=False)
        campaign.organization = self.org
        campaign.created_by = self.request.user
        campaign.save()
        messages.success(self.request, f'Campaign "{campaign.name}" created.')
        return redirect("message_templates:campaign_detail", pk=campaign.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "New Campaign"
        return ctx


class CampaignUpdateView(OrgRoleRequiredMixin, OrgMixin, UpdateView):
    required_role = Membership.Role.ADMIN
    template_name = "message_templates/campaign_form.html"
    form_class = DripCampaignForm

    def get_object(self):
        return get_object_or_404(DripCampaign.objects.for_org(self.org), pk=self.kwargs["pk"])

    def form_valid(self, form):
        campaign = form.save()
        messages.success(self.request, f'Campaign "{campaign.name}" updated.')
        return redirect("message_templates:campaign_detail", pk=campaign.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Edit Campaign"
        return ctx


@login_required
def campaign_detail(request, pk):
    org = _get_org(request)
    campaign = get_object_or_404(DripCampaign.objects.for_org(org), pk=pk)
    step_form = DripCampaignStepForm(campaign=campaign, org=org)
    steps = campaign.steps.select_related("template").order_by("order")
    enrollments = campaign.enrollments.select_related("contact").order_by("next_run_at", "created_at")[:50]
    logs = CampaignSendLog.objects.for_org(org).filter(enrollment__campaign=campaign).select_related("contact", "step").order_by("-created_at")[:30]

    return render(request, "message_templates/campaign_detail.html", {
        "campaign": campaign,
        "steps": steps,
        "step_form": step_form,
        "enrollments": enrollments,
        "logs": logs,
        "org": org,
        "now": timezone.now(),
    })


@login_required
@require_org_role(Membership.Role.ADMIN, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def campaign_add_step(request, pk):
    org = _get_org(request)
    campaign = get_object_or_404(DripCampaign.objects.for_org(org), pk=pk)
    if request.method != "POST":
        return redirect("message_templates:campaign_detail", pk=pk)

    form = DripCampaignStepForm(request.POST, campaign=campaign, org=org)
    if form.is_valid():
        step = form.save(commit=False)
        step.campaign = campaign
        step.save()
        messages.success(request, f"Added step {step.order}.")
    else:
        messages.error(request, "Could not add campaign step.")
    return redirect("message_templates:campaign_detail", pk=pk)


@login_required
@require_org_role(Membership.Role.ADMIN, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def campaign_delete_step(request, pk, step_pk):
    org = _get_org(request)
    campaign = get_object_or_404(DripCampaign.objects.for_org(org), pk=pk)
    step = get_object_or_404(DripCampaignStep, pk=step_pk, campaign=campaign)
    if request.method == "POST":
        deleted_step_order = step.order
        deleted_step_id = step.pk
        step.delete()
        messages.success(request, "Step deleted.")
        log_audit_event(
            organization=org,
            actor=request.user,
            action="campaign.step_deleted",
            entity_type="campaign_step",
            entity_id=deleted_step_id,
            severity="warning",
            message=f"Deleted step {deleted_step_order} from campaign {campaign.name}.",
            request=request,
        )
    return redirect("message_templates:campaign_detail", pk=pk)


@login_required
@require_org_role(Membership.Role.ADMIN, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def campaign_delete(request, pk):
    org = _get_org(request)
    campaign = get_object_or_404(DripCampaign.objects.for_org(org), pk=pk)
    if request.method == "POST":
        name = campaign.name
        campaign_id = campaign.pk
        campaign.delete()
        messages.success(request, f'Campaign "{name}" deleted.')
        log_audit_event(
            organization=org,
            actor=request.user,
            action="campaign.deleted",
            entity_type="campaign",
            entity_id=campaign_id,
            severity="critical",
            message=f'Campaign "{name}" deleted.',
            request=request,
        )
        return redirect("message_templates:campaign_list")
    return render(request, "message_templates/campaign_confirm_delete.html", {"campaign": campaign, "org": org})


class OneTimeBroadcastListView(OrgRoleRequiredMixin, OrgMixin, ListView):
    required_role = Membership.Role.ADMIN
    template_name = "message_templates/broadcast_list.html"
    context_object_name = "broadcasts"

    def get_queryset(self):
        return (
            OneTimeBroadcast.objects.for_org(self.org)
            .select_related("template", "filter_assigned_to", "created_by", "filter_segment")
            .order_by("-created_at")
        )


@login_required
@require_org_role(Membership.Role.ADMIN, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def one_time_broadcast_create(request):
    org = _get_org(request)
    form = OneTimeBroadcastForm(request.POST or None, org=org)
    preview_count = None
    preview_contacts = []

    if request.method == "POST" and form.is_valid():
        action = request.POST.get("action", "preview")
        selected_segment = form.cleaned_data.get("filter_segment")
        if selected_segment:
            audience_contact_type = selected_segment.contact_type
            audience_assigned_to = selected_segment.assigned_to
            audience_tags = list(selected_segment.tags.all())
            audience_city = selected_segment.city
            audience_state = selected_segment.state
            audience_zip_code = selected_segment.zip_code
            audience_inactive_days = selected_segment.inactive_days
        else:
            audience_contact_type = form.cleaned_data.get("filter_contact_type") or ""
            audience_assigned_to = form.cleaned_data.get("filter_assigned_to")
            audience_tags = list(form.cleaned_data.get("filter_tags") or [])
            audience_city = form.cleaned_data.get("filter_city") or ""
            audience_state = form.cleaned_data.get("filter_state") or ""
            audience_zip_code = form.cleaned_data.get("filter_zip_code") or ""
            audience_inactive_days = form.cleaned_data.get("filter_inactive_days")

        recipients = get_broadcast_recipients(
            org=org,
            channel=form.cleaned_data["channel"],
            contact_type=audience_contact_type,
            assigned_to=audience_assigned_to,
            tags=audience_tags,
            city=audience_city,
            state=audience_state,
            zip_code=audience_zip_code,
            inactive_days=audience_inactive_days,
        )
        preview_count = recipients.count()
        preview_contacts = list(recipients[:10])

        if action == "launch":
            if preview_count == 0:
                messages.error(request, "No eligible recipients match this audience.")
            else:
                broadcast = form.save(commit=False)
                broadcast.organization = org
                broadcast.created_by = request.user
                broadcast.filter_segment = selected_segment
                broadcast.filter_contact_type = audience_contact_type
                broadcast.filter_assigned_to = audience_assigned_to
                broadcast.filter_city = audience_city
                broadcast.filter_state = audience_state
                broadcast.filter_zip_code = audience_zip_code
                broadcast.filter_inactive_days = audience_inactive_days
                should_save_segment = form.cleaned_data.get("save_as_segment")
                segment_name = (form.cleaned_data.get("segment_name") or "").strip()

                def _persist_segment():
                    if not should_save_segment or not segment_name:
                        return
                    segment, _ = AudienceSegment.objects.update_or_create(
                        organization=org,
                        name=segment_name,
                        defaults={
                            "contact_type": audience_contact_type,
                            "assigned_to": audience_assigned_to,
                            "city": audience_city,
                            "state": audience_state,
                            "zip_code": audience_zip_code,
                            "inactive_days": audience_inactive_days,
                            "is_active": True,
                        },
                    )
                    segment.tags.set(audience_tags)

                if broadcast.approval_required:
                    broadcast.approval_status = OneTimeBroadcast.ApprovalStatus.PENDING
                    broadcast.status = OneTimeBroadcast.Status.SCHEDULED if broadcast.scheduled_for else OneTimeBroadcast.Status.DRAFT
                    broadcast.save()
                    if audience_tags:
                        broadcast.filter_tags.set(audience_tags)
                    _persist_segment()
                    messages.success(
                        request,
                        f'Broadcast "{broadcast.name}" is waiting for approval.',
                    )
                    return redirect("message_templates:broadcast_detail", pk=broadcast.pk)

                if broadcast.scheduled_for and broadcast.scheduled_for > timezone.now():
                    broadcast.status = OneTimeBroadcast.Status.SCHEDULED
                    broadcast.approval_status = OneTimeBroadcast.ApprovalStatus.NOT_REQUIRED
                    broadcast.save()
                    if audience_tags:
                        broadcast.filter_tags.set(audience_tags)
                    _persist_segment()
                    messages.success(
                        request,
                        f'Broadcast "{broadcast.name}" scheduled for {broadcast.scheduled_for:%Y-%m-%d %H:%M}.',
                    )
                    return redirect("message_templates:broadcast_detail", pk=broadcast.pk)

                broadcast.launched_at = timezone.now()
                broadcast.approval_status = OneTimeBroadcast.ApprovalStatus.NOT_REQUIRED
                broadcast.save()
                if audience_tags:
                    broadcast.filter_tags.set(audience_tags)
                _persist_segment()
                try:
                    run_one_time_broadcast(broadcast=broadcast)
                    broadcast.completed_at = timezone.now()
                    broadcast.save(
                        update_fields=[
                            "recipient_count",
                            "sent_count",
                            "failed_count",
                            "skipped_count",
                            "status",
                            "completed_at",
                            "updated_at",
                        ]
                    )
                    messages.success(
                        request,
                        f'Broadcast "{broadcast.name}" finished. Sent={broadcast.sent_count}, '
                        f"failed={broadcast.failed_count}, skipped={broadcast.skipped_count}.",
                    )
                    log_audit_event(
                        organization=org,
                        actor=request.user,
                        action="broadcast.sent",
                        entity_type="one_time_broadcast",
                        entity_id=broadcast.pk,
                        severity="info",
                        message=(
                            f'One-time broadcast "{broadcast.name}" sent. '
                            f"sent={broadcast.sent_count}, failed={broadcast.failed_count}, skipped={broadcast.skipped_count}"
                        ),
                        request=request,
                    )
                    return redirect("message_templates:broadcast_list")
                except Exception as exc:  # noqa: BLE001
                    broadcast.status = OneTimeBroadcast.Status.FAILED
                    broadcast.completed_at = timezone.now()
                    broadcast.save(update_fields=["status", "completed_at", "updated_at"])
                    messages.error(request, f"Broadcast failed before sending: {exc}")
        else:
            messages.info(
                request,
                f"Audience preview: {preview_count} eligible recipient(s).",
            )

    return render(
        request,
        "message_templates/broadcast_form.html",
        {
            "form": form,
            "org": org,
            "preview_count": preview_count,
            "preview_contacts": preview_contacts,
            "max_recipients": getattr(settings, "ONE_TIME_BROADCAST_MAX_RECIPIENTS", 300),
        },
    )


@login_required
@require_org_role(Membership.Role.ADMIN, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def one_time_broadcast_detail(request, pk):
    org = _get_org(request)
    broadcast = get_object_or_404(
        OneTimeBroadcast.objects.for_org(org).select_related("template", "filter_assigned_to", "created_by", "filter_segment"),
        pk=pk,
    )
    deliveries = (
        OneTimeBroadcastDelivery.objects.for_org(org)
        .filter(broadcast=broadcast)
        .select_related("contact")
        .order_by("-created_at")[:200]
    )
    has_deliveries = OneTimeBroadcastDelivery.objects.for_org(org).filter(broadcast=broadcast).exists()
    return render(
        request,
        "message_templates/broadcast_detail.html",
        {
            "broadcast": broadcast,
            "deliveries": deliveries,
            "has_deliveries": has_deliveries,
            "org": org,
        },
    )


@login_required
@require_org_role(Membership.Role.ADMIN, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def one_time_broadcast_approve(request, pk):
    org = _get_org(request)
    broadcast = get_object_or_404(OneTimeBroadcast.objects.for_org(org), pk=pk)
    if request.method != "POST":
        return redirect("message_templates:broadcast_detail", pk=pk)

    if not broadcast.approval_required:
        messages.info(request, "Approval is not required for this broadcast.")
        return redirect("message_templates:broadcast_detail", pk=pk)

    second_approver_required = getattr(settings, "BROADCAST_REQUIRE_SECOND_APPROVER", True)
    if second_approver_required and broadcast.created_by_id == request.user.id:
        messages.error(request, "A different admin must approve this broadcast.")
        return redirect("message_templates:broadcast_detail", pk=pk)

    broadcast.approval_status = OneTimeBroadcast.ApprovalStatus.APPROVED
    broadcast.approved_by = request.user
    broadcast.approved_at = timezone.now()
    if broadcast.status == OneTimeBroadcast.Status.DRAFT:
        broadcast.status = OneTimeBroadcast.Status.SCHEDULED if broadcast.scheduled_for else OneTimeBroadcast.Status.DRAFT
    broadcast.save(update_fields=["approval_status", "approved_by", "approved_at", "status", "updated_at"])
    messages.success(request, f'Broadcast "{broadcast.name}" approved.')
    return redirect("message_templates:broadcast_detail", pk=pk)


@login_required
@require_org_role(Membership.Role.ADMIN, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def one_time_broadcast_send_now(request, pk):
    org = _get_org(request)
    broadcast = get_object_or_404(OneTimeBroadcast.objects.for_org(org), pk=pk)
    if request.method != "POST":
        return redirect("message_templates:broadcast_detail", pk=pk)

    if not broadcast_is_approved(broadcast):
        messages.error(request, "Broadcast is not approved yet.")
        return redirect("message_templates:broadcast_detail", pk=pk)

    if broadcast.deliveries.exists():
        messages.info(request, "Broadcast has already been processed.")
        return redirect("message_templates:broadcast_detail", pk=pk)

    try:
        broadcast.launched_at = timezone.now()
        broadcast.save(update_fields=["launched_at", "updated_at"])
        run_one_time_broadcast(broadcast=broadcast)
        broadcast.completed_at = timezone.now()
        broadcast.save(
            update_fields=[
                "recipient_count",
                "sent_count",
                "failed_count",
                "skipped_count",
                "status",
                "completed_at",
                "updated_at",
            ]
        )
        messages.success(
            request,
            f'Broadcast "{broadcast.name}" processed. Sent={broadcast.sent_count}, failed={broadcast.failed_count}.',
        )
    except Exception as exc:  # noqa: BLE001
        broadcast.status = OneTimeBroadcast.Status.FAILED
        broadcast.completed_at = timezone.now()
        broadcast.save(update_fields=["status", "completed_at", "updated_at"])
        messages.error(request, f"Could not process broadcast: {exc}")

    return redirect("message_templates:broadcast_detail", pk=pk)


@login_required
@require_org_role(Membership.Role.ADMIN, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def one_time_broadcast_analytics(request):
    org = _get_org(request)
    lookback_days = 30
    since = timezone.now() - timedelta(days=lookback_days)

    deliveries_qs = OneTimeBroadcastDelivery.objects.for_org(org).filter(created_at__gte=since)
    broadcasts_qs = OneTimeBroadcast.objects.for_org(org)

    # Use filtered querysets for portability across Django versions.
    sent_count = deliveries_qs.filter(status=OneTimeBroadcastDelivery.Status.SENT).count()
    failed_count = deliveries_qs.filter(status=OneTimeBroadcastDelivery.Status.FAILED).count()
    skipped_count = deliveries_qs.filter(status=OneTimeBroadcastDelivery.Status.SKIPPED).count()
    total_count = deliveries_qs.count()

    trend_rows = (
        deliveries_qs
        .annotate(day=TruncDate("created_at"))
        .values("day", "status")
        .annotate(total=Count("id"))
        .order_by("day", "status")
    )
    trend_map = {}
    for row in trend_rows:
        day_key = row["day"].isoformat() if row["day"] else ""
        trend_map.setdefault(day_key, {"sent": 0, "failed": 0, "skipped": 0})
        trend_map[day_key][row["status"]] = row["total"]
    trend = [
        {
            "day": day,
            "sent": values.get("sent", 0),
            "failed": values.get("failed", 0),
            "skipped": values.get("skipped", 0),
        }
        for day, values in sorted(trend_map.items())
    ]

    top_templates = (
        broadcasts_qs
        .values("template__name")
        .annotate(
            broadcasts=Count("id"),
            sent_total=Sum("sent_count"),
            failed_total=Sum("failed_count"),
            skipped_total=Sum("skipped_count"),
        )
        .order_by("-sent_total", "-broadcasts")[:8]
    )
    top_segments = (
        broadcasts_qs
        .filter(filter_segment__isnull=False)
        .values("filter_segment__name")
        .annotate(
            broadcasts=Count("id"),
            sent_total=Sum("sent_count"),
            failed_total=Sum("failed_count"),
            skipped_total=Sum("skipped_count"),
        )
        .order_by("-sent_total", "-broadcasts")[:8]
    )

    return render(
        request,
        "message_templates/broadcast_analytics.html",
        {
            "org": org,
            "lookback_days": lookback_days,
            "total_count": total_count,
            "sent_count": sent_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
            "trend": trend,
            "top_templates": top_templates,
            "top_segments": top_segments,
        },
    )
