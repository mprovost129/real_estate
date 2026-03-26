import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from compliance.audit import log_audit_event
from organizations.models import Membership
from organizations.permissions import OrgRoleRequiredMixin, require_org_role
from organizations.utils import get_active_membership
from .forms import OpenHouseForm, VisitorSignInForm
from .models import OpenHouse, OpenHouseVisitor


def _get_org(request):
    m = get_active_membership(request)
    return m.organization if m else None


def _ensure_lead_pipeline_deal(contact, assigned_user):
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
        title=f"{contact.full_name} - Open House Lead",
        status=Deal.Status.ACTIVE,
    )


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

class OpenHouseListView(OrgMixin, ListView):
    template_name = "open_houses/list.html"
    context_object_name = "open_houses"
    paginate_by = 20

    def get_queryset(self):
        qs = (
            OpenHouse.objects.for_org(self.org)
            .select_related("listing", "host")
            .prefetch_related("visitors")
        )
        tab   = self.request.GET.get("tab", "upcoming")
        today = timezone.localdate()
        if tab == "upcoming":
            qs = qs.filter(date__gte=today).order_by("date", "start_time")
        elif tab == "past":
            qs = qs.filter(date__lt=today).order_by("-date", "-start_time")
        return qs

    def get_context_data(self, **kwargs):
        ctx   = super().get_context_data(**kwargs)
        ctx["tab"] = self.request.GET.get("tab", "upcoming")
        today = timezone.localdate()
        base  = OpenHouse.objects.for_org(self.org)
        ctx["count_upcoming"] = base.filter(date__gte=today).count()
        ctx["count_past"]     = base.filter(date__lt=today).count()
        return ctx


# ------------------------------------------------------------------ #
# Detail
# ------------------------------------------------------------------ #

class OpenHouseDetailView(OrgMixin, DetailView):
    template_name = "open_houses/detail.html"
    context_object_name = "oh"

    def get_object(self):
        return get_object_or_404(
            OpenHouse.objects.for_org(self.org).select_related("listing", "host"),
            pk=self.kwargs["pk"],
        )

    def get_context_data(self, **kwargs):
        ctx  = super().get_context_data(**kwargs)
        oh   = self.object
        ctx["visitors"]        = oh.visitors.select_related("contact").order_by("signed_in_at")
        ctx["visitor_form"]    = VisitorSignInForm()
        ctx["sign_in_url"]     = self.request.build_absolute_uri(
            f"/open-houses/sign-in/{oh.public_token}/"
        )
        ctx["total_visitors"]  = oh.visitors.count()
        ctx["buyers"]          = oh.visitors.filter(visitor_type="buyer").count()
        ctx["pre_approved"]    = oh.visitors.filter(is_pre_approved=True).count()
        ctx["not_followed_up"] = oh.visitors.filter(followed_up=False).count()
        return ctx


# ------------------------------------------------------------------ #
# Create / Update
# ------------------------------------------------------------------ #

class OpenHouseCreateView(OrgRoleRequiredMixin, OrgMixin, CreateView):
    template_name = "open_houses/open_house_form.html"
    form_class = OpenHouseForm

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["org"] = self.org
        return kw

    def get_initial(self):
        initial = super().get_initial()
        initial["host"] = self.request.user
        initial["date"] = timezone.localdate()
        return initial

    def form_valid(self, form):
        oh = form.save(commit=False)
        oh.organization = self.org
        oh.save()
        messages.success(self.request, f'Open house for "{oh.display_title}" created.')
        return redirect("open_houses:detail", pk=oh.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "New Open House"
        return ctx


class OpenHouseUpdateView(OrgRoleRequiredMixin, OrgMixin, UpdateView):
    template_name = "open_houses/open_house_form.html"
    form_class = OpenHouseForm

    def get_object(self):
        return get_object_or_404(OpenHouse.objects.for_org(self.org), pk=self.kwargs["pk"])

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["org"] = self.org
        return kw

    def form_valid(self, form):
        oh = form.save()
        messages.success(self.request, "Open house updated.")
        return redirect("open_houses:detail", pk=oh.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Edit Open House"
        return ctx


# ------------------------------------------------------------------ #
# Public sign-in (no auth — accessed via QR code)
# ------------------------------------------------------------------ #

def sign_in_view(request, token):
    oh = get_object_or_404(OpenHouse, public_token=token)

    if oh.status == OpenHouse.Status.CANCELLED:
        return render(request, "open_houses/sign_in_closed.html", {"oh": oh})

    form = VisitorSignInForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        visitor            = form.save(commit=False)
        visitor.open_house = oh
        visitor.save()
        return render(request, "open_houses/sign_in_thanks.html", {
            "oh": oh, "visitor": visitor,
        })

    return render(request, "open_houses/sign_in.html", {"oh": oh, "form": form})


# ------------------------------------------------------------------ #
# Add visitor from staff detail page
# ------------------------------------------------------------------ #

@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def add_visitor(request, pk):
    org = _get_org(request)
    oh  = get_object_or_404(OpenHouse.objects.for_org(org), pk=pk)

    if request.method == "POST":
        form = VisitorSignInForm(request.POST)
        if form.is_valid():
            visitor            = form.save(commit=False)
            visitor.open_house = oh
            visitor.save()
            messages.success(request, f"{visitor.full_name} added.")
        else:
            messages.error(request, "Could not add visitor — check the form.")

    return redirect("open_houses:detail", pk=pk)


# ------------------------------------------------------------------ #
# Convert visitor to Contact
# ------------------------------------------------------------------ #

@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def convert_visitor(request, pk, visitor_pk):
    org     = _get_org(request)
    oh      = get_object_or_404(OpenHouse.objects.for_org(org), pk=pk)
    visitor = get_object_or_404(OpenHouseVisitor, pk=visitor_pk, open_house=oh)

    if visitor.contact:
        messages.info(request, "Visitor is already linked to a contact.")
        return redirect("open_houses:detail", pk=pk)

    if request.method == "POST":
        from contacts.models import Contact, ContactNote

        contact = Contact.objects.create(
            organization=org,
            first_name=visitor.first_name,
            last_name=visitor.last_name or "",
            primary_email=visitor.email,
            primary_phone=visitor.phone,
            contact_type=Contact.ContactType.LEAD,
            source=Contact.Source.OPEN_HOUSE,
            assigned_to=request.user,
        )
        visitor.contact = contact
        visitor.save(update_fields=["contact"])

        # Auto-log the visit as a note on the new contact
        note_body = (
            f"Attended open house at {oh.display_address} on {oh.date}. "
            f"Visitor type: {visitor.get_visitor_type_display()}."
        )
        if visitor.pre_approval_amount:
            note_body += f" Pre-approved: ${visitor.pre_approval_amount:,.0f}."
        if visitor.notes:
            note_body += f" Notes: {visitor.notes}"

        ContactNote.objects.create(
            organization=org,
            contact=contact,
            author=request.user,
            note_type=ContactNote.NoteType.OPEN_HOUSE,
            body=note_body,
        )
        _ensure_lead_pipeline_deal(contact, request.user)
        try:
            from automations.engine import run_trigger
            from automations.models import AutomationRule

            run_trigger(
                organization=org,
                trigger_type=AutomationRule.TriggerType.LEAD_CREATED,
                context={
                    "contact": contact,
                    "trigger_user": request.user,
                    "source": "open_house",
                },
                object_ref=f"contact:{contact.pk}",
            )
        except Exception:
            pass

        from tasks.models import Task
        Task.objects.get_or_create(
            organization=org,
            contact=contact,
            title=f"Open house follow-up - {contact.full_name}",
            defaults={
                "task_type": Task.TaskType.FOLLOW_UP,
                "assigned_to": request.user,
                "assigned_by": request.user,
                "due_date": timezone.localdate(),
                "priority": Task.Priority.HIGH,
                "status": Task.Status.PENDING,
                "description": f"Follow up with {contact.full_name} from open house at {oh.display_address}.",
            },
        )

        messages.success(request, f"{contact.full_name} created as a new lead.")

    return redirect("open_houses:detail", pk=pk)


# ------------------------------------------------------------------ #
# Mark followed up
# ------------------------------------------------------------------ #

@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def mark_followed_up(request, pk, visitor_pk):
    org     = _get_org(request)
    oh      = get_object_or_404(OpenHouse.objects.for_org(org), pk=pk)
    visitor = get_object_or_404(OpenHouseVisitor, pk=visitor_pk, open_house=oh)

    if request.method == "POST":
        visitor.followed_up    = True
        visitor.followed_up_at = timezone.now()
        visitor.save(update_fields=["followed_up", "followed_up_at"])
        messages.success(request, f"{visitor.full_name} marked as followed up.")

    return redirect("open_houses:detail", pk=pk)


# ------------------------------------------------------------------ #
# Export visitors CSV
# ------------------------------------------------------------------ #

@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def export_visitors(request, pk):
    org = _get_org(request)
    oh  = get_object_or_404(OpenHouse.objects.for_org(org), pk=pk)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="open_house_{oh.date}_{pk}.csv"'
    )

    writer = csv.writer(response)
    writer.writerow([
        "First Name", "Last Name", "Email", "Phone",
        "Visitor Type", "Pre-Approved", "Pre-Approval Amount",
        "Working with Agent", "Agent Name",
        "Notes", "Signed In At", "Followed Up",
    ])
    for v in oh.visitors.order_by("signed_in_at"):
        writer.writerow([
            v.first_name, v.last_name, v.email, v.phone,
            v.get_visitor_type_display(),
            "Yes" if v.is_pre_approved else "No",
            v.pre_approval_amount or "",
            "Yes" if v.represented_by_agent else "No",
            v.agent_name,
            v.notes,
            v.signed_in_at.strftime("%Y-%m-%d %H:%M"),
            "Yes" if v.followed_up else "No",
        ])

    return response


# ------------------------------------------------------------------ #
# Delete
# ------------------------------------------------------------------ #

@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def open_house_delete(request, pk):
    org = _get_org(request)
    oh  = get_object_or_404(OpenHouse.objects.for_org(org), pk=pk)

    if request.method == "POST":
        title = oh.display_title
        oh_id = oh.pk
        oh.delete()
        messages.success(request, f'Open house "{title}" deleted.')
        log_audit_event(
            organization=org,
            actor=request.user,
            action="open_house.deleted",
            entity_type="open_house",
            entity_id=oh_id,
            severity="critical",
            message=f'Open house "{title}" deleted.',
            request=request,
        )
        return redirect("open_houses:list")

    return render(request, "open_houses/open_house_confirm_delete.html", {"oh": oh})
