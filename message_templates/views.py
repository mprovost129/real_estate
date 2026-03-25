from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from compliance.audit import log_audit_event
from organizations.models import Membership
from organizations.permissions import OrgRoleRequiredMixin, require_org_role
from .forms import DripCampaignForm, DripCampaignStepForm
from .models import CampaignEnrollment, CampaignSendLog, DripCampaign, DripCampaignStep, MessageTemplate


def _get_org(request):
    m = request.user.memberships.filter(is_active=True).select_related("organization").first()
    return m.organization if m else None


class OrgMixin(LoginRequiredMixin):
    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        m = request.user.memberships.filter(is_active=True).select_related("organization").first()
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
