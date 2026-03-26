from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, ListView, UpdateView

from compliance.audit import log_audit_event
from organizations.models import Membership
from organizations.permissions import OrgRoleRequiredMixin, require_org_role
from organizations.utils import get_active_membership
from .models import LeadCaptureForm, LeadFormSubmission


# ------------------------------------------------------------------ #
# Org helpers
# ------------------------------------------------------------------ #

class OrgMixin(LoginRequiredMixin):
    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        m = get_active_membership(request)
        self.org = m.organization if m else None

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["org"] = self.org
        return ctx


def _get_org(request):
    m = get_active_membership(request)
    return m.organization if m else None


def _ensure_lead_pipeline_deal(contact, assigned_user):
    """Create one active lead deal so form submissions enter the pipeline."""
    from pipelines.models import Deal, Pipeline

    if not contact or not contact.organization:
        return None

    existing = (
        Deal.objects.for_org(contact.organization)
        .filter(contact=contact, status=Deal.Status.ACTIVE)
        .first()
    )
    if existing:
        return existing

    pipeline = (
        Pipeline.objects.for_org(contact.organization)
        .filter(pipeline_type=Pipeline.PipelineType.LEAD, is_active=True)
        .prefetch_related("stages")
        .first()
    )
    if not pipeline:
        return None

    first_stage = (
        pipeline.stages
        .filter(is_active=True, is_lost=False)
        .order_by("order")
        .first()
    )
    if not first_stage:
        return None

    return Deal.objects.create(
        organization=contact.organization,
        contact=contact,
        pipeline=pipeline,
        stage=first_stage,
        assigned_to=assigned_user or contact.assigned_to,
        title=f"{contact.full_name} - New Lead",
        status=Deal.Status.ACTIVE,
    )


# ------------------------------------------------------------------ #
# Management views (require login)
# ------------------------------------------------------------------ #

class FormListView(OrgMixin, ListView):
    template_name = "lead_forms/list.html"
    context_object_name = "forms"

    def get_queryset(self):
        return (
            LeadCaptureForm.objects
            .for_org(self.org)
            .prefetch_related("submissions")
            .order_by("-created_at")
        )


class FormCreateView(OrgRoleRequiredMixin, OrgMixin, CreateView):
    required_role = Membership.Role.ADMIN
    template_name = "lead_forms/form.html"
    model = LeadCaptureForm
    fields = [
        "name", "form_type", "contact_source",
        "headline", "subheadline", "button_text",
        "thank_you_title", "thank_you_body", "redirect_url",
        "show_phone", "show_message", "show_address", "show_budget", "show_timeline",
        "require_phone", "require_message",
        "assigned_to", "is_active",
    ]

    def get_form(self, form_class=None):
        f = super().get_form(form_class)
        # Limit assigned_to to org members
        from django.contrib.auth import get_user_model
        User = get_user_model()
        f.fields["assigned_to"].queryset = User.objects.filter(
            memberships__organization=self.org,
            memberships__is_active=True,
        ).distinct()
        # Style all inputs
        for name, field in f.fields.items():
            from django import forms
            if isinstance(field.widget, (
                forms.TextInput, forms.EmailInput, forms.URLInput,
                forms.Textarea, forms.Select,
            )):
                field.widget.attrs["class"] = "input"
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs.setdefault("rows", 3)
        return f

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.organization = self.org
        obj.save()
        messages.success(self.request, f'Form "{obj.name}" created.')
        return redirect("lead_forms:detail", pk=obj.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "New Lead Form"
        return ctx


class FormUpdateView(OrgRoleRequiredMixin, OrgMixin, UpdateView):
    required_role = Membership.Role.ADMIN
    template_name = "lead_forms/form.html"
    model = LeadCaptureForm
    fields = [
        "name", "form_type", "contact_source",
        "headline", "subheadline", "button_text",
        "thank_you_title", "thank_you_body", "redirect_url",
        "show_phone", "show_message", "show_address", "show_budget", "show_timeline",
        "require_phone", "require_message",
        "assigned_to", "is_active",
    ]

    def get_queryset(self):
        return LeadCaptureForm.objects.for_org(self.org)

    def get_form(self, form_class=None):
        f = super().get_form(form_class)
        from django.contrib.auth import get_user_model
        User = get_user_model()
        f.fields["assigned_to"].queryset = User.objects.filter(
            memberships__organization=self.org,
            memberships__is_active=True,
        ).distinct()
        for name, field in f.fields.items():
            from django import forms
            if isinstance(field.widget, (
                forms.TextInput, forms.EmailInput, forms.URLInput,
                forms.Textarea, forms.Select,
            )):
                field.widget.attrs["class"] = "input"
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs.setdefault("rows", 3)
        return f

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Form updated.")
        return redirect("lead_forms:detail", pk=self.object.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = f"Edit — {self.object.name}"
        return ctx


@login_required
def form_detail(request, pk):
    org  = _get_org(request)
    form = get_object_or_404(LeadCaptureForm, pk=pk, organization=org)
    submissions = form.submissions.select_related("contact").order_by("-submitted_at")[:50]
    public_url  = form.public_url(request)
    embed_code  = f'<iframe src="{public_url}" width="100%" height="600" frameborder="0"></iframe>'
    return render(request, "lead_forms/detail.html", {
        "form":        form,
        "submissions": submissions,
        "public_url":  public_url,
        "embed_code":  embed_code,
        "org":         org,
    })


@login_required
@require_POST
@require_org_role(Membership.Role.ADMIN, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def form_toggle(request, pk):
    org  = _get_org(request)
    lf   = get_object_or_404(LeadCaptureForm, pk=pk, organization=org)
    lf.is_active = not lf.is_active
    lf.save(update_fields=["is_active"])
    status = "activated" if lf.is_active else "deactivated"
    messages.success(request, f'Form "{lf.name}" {status}.')
    log_audit_event(
        organization=org,
        actor=request.user,
        action="lead_form.toggled",
        entity_type="lead_form",
        entity_id=lf.pk,
        severity="warning",
        message=f'Lead form "{lf.name}" {status}.',
        metadata={"is_active": lf.is_active},
        request=request,
    )
    return redirect("lead_forms:detail", pk=pk)


@login_required
@require_POST
@require_org_role(Membership.Role.ADMIN, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def form_delete(request, pk):
    org  = _get_org(request)
    lf   = get_object_or_404(LeadCaptureForm, pk=pk, organization=org)
    name = lf.name
    lf_id = lf.pk
    lf.delete()
    messages.success(request, f'Form "{name}" deleted.')
    log_audit_event(
        organization=org,
        actor=request.user,
        action="lead_form.deleted",
        entity_type="lead_form",
        entity_id=lf_id,
        severity="critical",
        message=f'Lead form "{name}" deleted.',
        request=request,
    )
    return redirect("lead_forms:list")


# ------------------------------------------------------------------ #
# Public form — no login required
# ------------------------------------------------------------------ #

def public_form(request, slug):
    lf = get_object_or_404(LeadCaptureForm, slug=slug, is_active=True)

    if request.method == "POST":
        first_name = request.POST.get("first_name", "").strip()
        last_name  = request.POST.get("last_name",  "").strip()
        email      = request.POST.get("email",      "").strip()
        phone      = request.POST.get("phone",      "").strip()
        message    = request.POST.get("message",    "").strip()
        address    = request.POST.get("address",    "").strip()
        budget     = request.POST.get("budget",     "").strip()
        timeline   = request.POST.get("timeline",   "").strip()

        # Basic validation
        errors = []
        if not first_name:
            errors.append("First name is required.")
        if not last_name:
            errors.append("Last name is required.")
        if not email:
            errors.append("Email is required.")
        if lf.require_phone and not phone:
            errors.append("Phone number is required.")
        if lf.require_message and not message:
            errors.append("Please include a message.")

        timeline_choices = ["ASAP", "1–3 months", "3–6 months", "6–12 months", "Just exploring"]
        if errors:
            return render(request, "lead_forms/public_form.html", {
                "lf":               lf,
                "errors":           errors,
                "post":             request.POST,
                "timeline_choices": timeline_choices,
            })

        # Record submission
        ip = (
            request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR")
        )
        sub = LeadFormSubmission(
            form=lf,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            message=message,
            address=address,
            budget=budget,
            timeline=timeline,
            ip_address=ip or None,
        )

        # Create or update Contact
        contact = None
        try:
            from contacts.models import Contact
            
            # Try to find existing contact in the org by email
            if email:
                contact = Contact.objects.filter(
                    organization=lf.organization,
                    primary_email__iexact=email,
                    is_active=True,
                ).first()

            if contact is None:
                contact = Contact(
                    organization=lf.organization,
                    first_name=first_name,
                    last_name=last_name,
                    primary_email=email,
                    primary_phone=phone,
                    contact_type=Contact.ContactType.LEAD,
                    source=lf.contact_source,
                    assigned_to=lf.assigned_to,
                )
                notes_parts = []
                if message:
                    notes_parts.append(f"Message: {message}")
                if address:
                    notes_parts.append(f"Property of interest: {address}")
                if budget:
                    notes_parts.append(f"Budget: {budget}")
                if timeline:
                    notes_parts.append(f"Timeline: {timeline}")
                if notes_parts:
                    contact.notes = "\n".join(notes_parts)
                contact.save()
            else:
                # Update phone if missing
                if phone and not contact.primary_phone:
                    contact.primary_phone = phone
                    contact.save(update_fields=["primary_phone"])

            _ensure_lead_pipeline_deal(contact, lf.assigned_to)
            try:
                from automations.engine import run_trigger
                from automations.models import AutomationRule

                run_trigger(
                    organization=lf.organization,
                    trigger_type=AutomationRule.TriggerType.LEAD_CREATED,
                    context={
                        "contact": contact,
                        "trigger_user": lf.assigned_to,
                        "source": lf.contact_source,
                    },
                    object_ref=f"contact:{contact.pk}",
                )
            except Exception:
                pass
            sub.contact = contact
            sub.converted = True

            # Create notification for assigned agent
            if lf.assigned_to:
                try:
                    from notifications.models import Notification
                    from django.urls import reverse
                    Notification.objects.create(
                        organization=lf.organization,
                        recipient=lf.assigned_to,
                        notification_type=Notification.Type.CONTACT_ASSIGNED,
                        title=f"New lead from form: {first_name} {last_name}",
                        body=f'Via "{lf.name}" - {email}',
                        link=reverse("contacts:detail", kwargs={"pk": contact.pk}),
                        contact=contact,
                    )
                except Exception:
                    pass

        except Exception:
            pass

        sub.save()

        timeline_choices = ["ASAP", "1–3 months", "3–6 months", "6–12 months", "Just exploring"]

        if lf.redirect_url:
            return redirect(lf.redirect_url)

        return render(request, "lead_forms/thank_you.html", {"lf": lf})

    timeline_choices = ["ASAP", "1–3 months", "3–6 months", "6–12 months", "Just exploring"]
    return render(request, "lead_forms/public_form.html", {
        "lf":               lf,
        "errors":           [],
        "post":             {},
        "timeline_choices": timeline_choices,
    })

