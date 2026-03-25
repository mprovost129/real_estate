import csv
import io

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from compliance.audit import log_audit_event
from organizations.models import Membership
from organizations.permissions import OrgRoleRequiredMixin, require_org_role
from .forms import (
    ContactDocumentForm,
    ContactForm,
    ContactNoteForm,
    LogCallForm,
    LogEmailForm,
    LogNoteForm,
    LogTextForm,
    TagForm,
)
from .models import Contact, ContactDocument, ContactNote, Tag
from .sms import SMSDeliveryError, send_sms_message


def _get_org(request):
    membership = (
        request.user.memberships
        .filter(is_active=True)
        .select_related("organization")
        .first()
    )
    return membership.organization if membership else None


def _merge_fields(text, contact, user):
    if not text:
        return ""
    values = {
        "first_name": contact.first_name or "",
        "last_name": contact.last_name or "",
        "full_name": contact.full_name or "",
        "address": contact.address or "",
        "agent_name": getattr(user, "full_name", "") or user.get_username(),
        "closing_date": "",
        "price": "",
    }
    rendered = text
    for key, val in values.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", str(val))
    return rendered


def _required_contact_document_codes(contact):
    if contact.contact_type in [Contact.ContactType.ACTIVE_BUYER]:
        return [
            ContactDocument.Category.IDENTITY,
            ContactDocument.Category.PREAPPROVAL,
            ContactDocument.Category.AGREEMENT,
        ]
    if contact.contact_type in [Contact.ContactType.ACTIVE_SELLER]:
        return [
            ContactDocument.Category.IDENTITY,
            ContactDocument.Category.AGREEMENT,
            ContactDocument.Category.DISCLOSURE,
        ]
    if contact.contact_type in [Contact.ContactType.UNDER_CONTRACT]:
        return [
            ContactDocument.Category.IDENTITY,
            ContactDocument.Category.AGREEMENT,
            ContactDocument.Category.DISCLOSURE,
            ContactDocument.Category.FINANCIAL,
        ]
    return []


class OrgMixin(LoginRequiredMixin):
    """Resolves the current org for every authenticated view."""

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        membership = (
            request.user.memberships
            .filter(is_active=True)
            .select_related("organization")
            .first()
        )
        self.org = membership.organization if membership else None
        self.membership = membership

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["org"] = self.org
        ctx["membership"] = self.membership
        return ctx


class ContactListView(OrgMixin, ListView):
    template_name = "contacts/list.html"
    context_object_name = "contacts"
    paginate_by = 25

    def get_queryset(self):
        qs = (
            Contact.objects
            .for_org(self.org)
            .filter(is_active=True)
            .select_related("assigned_to")
            .prefetch_related("tags")
            .order_by("last_name", "first_name")
        )
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(primary_email__icontains=q)
                | Q(primary_phone__icontains=q)
                | Q(employer__icontains=q)
            )
        contact_type = self.request.GET.get("type", "")
        if contact_type:
            qs = qs.filter(contact_type=contact_type)
        source = self.request.GET.get("source", "")
        if source:
            qs = qs.filter(source=source)
        assigned = self.request.GET.get("assigned", "")
        if assigned == "me":
            qs = qs.filter(assigned_to=self.request.user)
        tag_slug = self.request.GET.get("tag", "")
        if tag_slug:
            qs = qs.filter(tags__pk=tag_slug)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = self.request.GET.get("q", "")
        ctx["selected_type"] = self.request.GET.get("type", "")
        ctx["selected_source"] = self.request.GET.get("source", "")
        ctx["selected_assigned"] = self.request.GET.get("assigned", "")
        ctx["selected_tag"] = self.request.GET.get("tag", "")
        ctx["contact_types"] = Contact.ContactType.choices
        ctx["sources"] = Contact.Source.choices
        ctx["total_count"] = Contact.objects.for_org(self.org).filter(is_active=True).count()
        ctx["all_tags"] = Tag.objects.filter(organization=self.org).order_by("name")
        return ctx


class ContactDetailView(OrgMixin, DetailView):
    template_name = "contacts/detail.html"
    context_object_name = "contact"

    def get_queryset(self):
        return Contact.objects.for_org(self.org).filter(is_active=True)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        contact = self.object
        ctx["note_form"]  = ContactNoteForm()
        ctx["log_call_form"]  = LogCallForm()
        ctx["log_email_form"] = LogEmailForm()
        ctx["log_text_form"]  = LogTextForm()
        ctx["log_note_form"]  = LogNoteForm()
        ctx["notes"] = (
            ContactNote.objects
            .filter(contact=contact)
            .select_related("author")
            .order_by("-is_pinned", "-created_at")
        )
        ctx["tasks"] = (
            contact.tasks
            .filter(status__in=["pending", "in_progress"])
            .order_by("due_date")[:5]
        )
        ctx["deals"] = (
            contact.deals
            .select_related("pipeline", "stage")
            .order_by("-created_at")[:5]
        )
        ctx["emails"] = contact.emails.all()
        ctx["phones"] = contact.phones.all()

        # Task type choices for quick-task form
        from tasks.models import Task as TaskModel
        ctx["task_type_choices"] = TaskModel.TaskType.choices

        # Message templates for picker (email + sms only)
        from message_templates.models import MessageTemplate
        ctx["email_templates"] = (
            MessageTemplate.objects.for_org(self.org)
            .filter(template_type="email", is_active=True)
            .order_by("category", "name")
        )
        ctx["sms_templates"] = (
            MessageTemplate.objects.for_org(self.org)
            .filter(template_type="sms", is_active=True)
            .order_by("category", "name")
        )
        ctx["all_tags"] = Tag.objects.filter(organization=self.org).order_by("name")
        ctx["contact_tag_ids"] = set(contact.tags.values_list("pk", flat=True))
        documents = contact.documents.select_related("uploaded_by").all()
        ctx["documents"] = documents
        ctx["document_form"] = ContactDocumentForm()
        category_counts = {}
        for doc in documents:
            category_counts[doc.category] = category_counts.get(doc.category, 0) + 1
        required_codes = _required_contact_document_codes(contact)
        category_labels = dict(ContactDocument.Category.choices)
        checklist = []
        missing = []
        for code in required_codes:
            count = category_counts.get(code, 0)
            is_present = count > 0
            checklist.append({
                "code": code,
                "label": category_labels.get(code, code),
                "count": count,
                "is_present": is_present,
            })
            if not is_present:
                missing.append(category_labels.get(code, code))
        ctx["document_required_checklist"] = checklist
        ctx["missing_document_labels"] = missing
        ctx["missing_document_count"] = len(missing)
        return ctx


class ContactCreateView(OrgRoleRequiredMixin, OrgMixin, CreateView):
    template_name = "contacts/form.html"
    form_class = ContactForm

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["org"] = self.org
        return kw

    def form_valid(self, form):
        form.instance.organization = self.org
        response = super().form_valid(form)
        messages.success(self.request, f'Contact "{self.object.full_name}" was saved.')
        return response

    def form_invalid(self, form):
        messages.error(self.request, "Contact was not saved. Please fix the highlighted fields and try again.")
        return super().form_invalid(form)

    def get_success_url(self):
        return reverse("contacts:detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["action"] = "Add Contact"
        return ctx


class ContactUpdateView(OrgRoleRequiredMixin, OrgMixin, UpdateView):
    template_name = "contacts/form.html"
    form_class = ContactForm

    def get_queryset(self):
        return Contact.objects.for_org(self.org)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["org"] = self.org
        return kw

    def get_success_url(self):
        return reverse("contacts:detail", kwargs={"pk": self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Contact "{self.object.full_name}" was updated.')
        return response

    def form_invalid(self, form):
        messages.error(self.request, "Changes were not saved. Please fix the highlighted fields and try again.")
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["action"] = f"Edit — {self.object.full_name}"
        return ctx


@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def contact_add_note(request, pk):
    membership = (
        request.user.memberships
        .filter(is_active=True)
        .select_related("organization")
        .first()
    )
    org = membership.organization if membership else None
    contact = get_object_or_404(Contact, pk=pk, organization=org, is_active=True)

    if request.method == "POST":
        form = ContactNoteForm(request.POST)
        if form.is_valid():
            note = form.save(commit=False)
            note.contact      = contact
            note.organization = org
            note.author       = request.user
            note.save()

    return redirect("contacts:detail", pk=pk)


@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def log_communication(request, pk):
    """Unified handler for call/email/text/note log forms."""
    membership = (
        request.user.memberships
        .filter(is_active=True)
        .select_related("organization")
        .first()
    )
    org     = membership.organization if membership else None
    contact = get_object_or_404(Contact, pk=pk, organization=org, is_active=True)

    if request.method != "POST":
        return redirect("contacts:detail", pk=pk)

    comm_type = request.POST.get("comm_type", "note")

    note = ContactNote(contact=contact, organization=org, author=request.user)

    if comm_type == "call":
        form = LogCallForm(request.POST, instance=note)
        if form.is_valid():
            n = form.save(commit=False)
            n.note_type = ContactNote.NoteType.CALL
            n.save()
            messages.success(request, "Call logged.")
        else:
            messages.error(request, "Could not log call — check the form.")

    elif comm_type == "email":
        form = LogEmailForm(request.POST, instance=note)
        if form.is_valid():
            raw_subject = form.cleaned_data.get("email_subject", "")
            raw_body = form.cleaned_data.get("body", "")
            subject = _merge_fields(raw_subject, contact, request.user)
            body = _merge_fields(raw_body, contact, request.user)
            send_now = request.POST.get("send_now") == "1"

            if send_now:
                if not contact.primary_email:
                    messages.error(request, "This contact has no primary email address.")
                    return redirect("contacts:detail", pk=pk)
                try:
                    sent = send_mail(
                        subject=subject or "(No subject)",
                        message=body,
                        from_email=None,  # use DEFAULT_FROM_EMAIL
                        recipient_list=[contact.primary_email],
                        fail_silently=False,
                    )
                    if sent:
                        n = form.save(commit=False)
                        n.note_type = ContactNote.NoteType.EMAIL
                        n.email_subject = subject
                        n.body = body
                        n.save()
                        messages.success(request, f"Email sent to {contact.primary_email} and logged.")
                    else:
                        ContactNote.objects.create(
                            organization=org,
                            contact=contact,
                            author=request.user,
                            note_type=ContactNote.NoteType.SYSTEM,
                            body=f"Email send failed (no messages sent) to {contact.primary_email}. Subject: {subject}",
                        )
                        messages.error(request, "Email was not sent (provider returned no deliveries).")
                except Exception as exc:
                    ContactNote.objects.create(
                        organization=org,
                        contact=contact,
                        author=request.user,
                        note_type=ContactNote.NoteType.SYSTEM,
                        body=f"Email send failed to {contact.primary_email}. Subject: {subject}. Error: {exc}",
                    )
                    messages.error(request, "Email failed to send. A system note was added.")
            else:
                n = form.save(commit=False)
                n.note_type = ContactNote.NoteType.EMAIL
                n.email_subject = subject
                n.body = body
                n.save()
                messages.success(request, "Email logged.")
        else:
            messages.error(request, "Could not log email — check the form.")

    elif comm_type == "text":
        form = LogTextForm(request.POST, instance=note)
        if form.is_valid():
            raw_body = form.cleaned_data.get("body", "")
            body = _merge_fields(raw_body, contact, request.user)
            send_now = request.POST.get("send_now") == "1"

            if send_now:
                if contact.do_not_contact or contact.opted_out_sms:
                    messages.error(request, "SMS blocked because this contact is marked Do Not Contact / opted out.")
                    return redirect("contacts:detail", pk=pk)
                if not contact.primary_phone:
                    messages.error(request, "This contact has no primary phone number.")
                    return redirect("contacts:detail", pk=pk)
                try:
                    send_sms_message(to_number=contact.primary_phone, body=body)
                    n = form.save(commit=False)
                    n.note_type = ContactNote.NoteType.TEXT
                    n.body = body
                    n.save()
                    messages.success(request, f"SMS sent to {contact.primary_phone} and logged.")
                except SMSDeliveryError as exc:
                    ContactNote.objects.create(
                        organization=org,
                        contact=contact,
                        author=request.user,
                        note_type=ContactNote.NoteType.SYSTEM,
                        body=f"SMS send failed to {contact.primary_phone}. Error: {exc}",
                    )
                    messages.error(request, "SMS failed to send. A system note was added.")
            else:
                n = form.save(commit=False)
                n.note_type = ContactNote.NoteType.TEXT
                n.body = body
                n.save()
                messages.success(request, "Text logged.")
        else:
            messages.error(request, "Could not log text — check the form.")

    else:  # general note / meeting / showing
        form = LogNoteForm(request.POST, instance=note)
        if form.is_valid():
            n             = form.save(commit=False)
            n.note_type   = form.cleaned_data.get("note_type") or ContactNote.NoteType.GENERAL
            n.is_pinned   = form.cleaned_data.get("is_pinned", False)
            n.save()
        else:
            messages.error(request, "Could not add note.")

    return redirect("contacts:detail", pk=pk)


@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def contact_delete(request, pk):
    membership = (
        request.user.memberships
        .filter(is_active=True)
        .select_related("organization")
        .first()
    )
    org = membership.organization if membership else None
    contact = get_object_or_404(Contact, pk=pk, organization=org)

    if request.method == "POST":
        contact.is_active = False
        contact.save(update_fields=["is_active"])
        log_audit_event(
            organization=org,
            actor=request.user,
            action="contact.deactivated",
            entity_type="contact",
            entity_id=contact.pk,
            severity="critical",
            message=f"Contact {contact.full_name} deactivated.",
            request=request,
        )
        return redirect("contacts:list")

    return render(request, "contacts/confirm_delete.html", {"contact": contact})


# ------------------------------------------------------------------ #
# Follow-up Center
# ------------------------------------------------------------------ #

@login_required
def follow_up_center(request):
    from datetime import timedelta
    from django.db.models import Max, Q
    from django.db.models.functions import ExtractMonth, ExtractDay
    from django.utils import timezone
    from tasks.models import Task

    membership = request.user.memberships.filter(is_active=True).select_related("organization").first()
    org   = membership.organization if membership else None
    today = timezone.localdate()
    now   = timezone.now()

    # ── 1. No next step: active types with no open task ─────────────
    active_types = [
        Contact.ContactType.LEAD, Contact.ContactType.PROSPECT,
        Contact.ContactType.ACTIVE_BUYER, Contact.ContactType.ACTIVE_SELLER,
        Contact.ContactType.UNDER_CONTRACT,
    ]
    contacts_with_open_task = (
        Task.objects.for_org(org)
        .filter(status__in=[Task.Status.PENDING, Task.Status.IN_PROGRESS], contact__isnull=False)
        .values_list("contact_id", flat=True)
    )
    no_next_step = (
        Contact.objects.for_org(org)
        .filter(contact_type__in=active_types, is_active=True)
        .exclude(pk__in=contacts_with_open_task)
        .select_related("assigned_to")
        .order_by("contact_type", "last_name")[:30]
    )

    # ── 2. Going cold: last activity older than threshold ───────────
    thresholds = {
        "lead": 3, "prospect": 5, "active_buyer": 7,
        "active_seller": 7, "under_contract": 3,
        "past_client": 90, "sphere": 60,
    }
    going_cold = []
    for ctype, days in thresholds.items():
        cutoff = now - timedelta(days=days)
        qs = (
            Contact.objects.for_org(org)
            .filter(contact_type=ctype, is_active=True)
            .annotate(last_activity=Max("contact_notes__created_at"))
            .filter(Q(last_activity__lt=cutoff) | Q(last_activity__isnull=True))
            .select_related("assigned_to")
            .order_by("last_activity")[:10]
        )
        for c in qs:
            days_inactive = (now - c.last_activity).days if c.last_activity else None
            going_cold.append({
                "contact":       c,
                "days_inactive": days_inactive,
                "threshold":     days,
                "is_critical":   bool(days_inactive is not None and days_inactive > (days * 2)),
            })
    going_cold.sort(key=lambda x: x["days_inactive"] or 9999, reverse=True)
    going_cold = going_cold[:25]

    # ── 3. Upcoming birthdays (next 30 days) ────────────────────────
    window    = [today + timedelta(days=i) for i in range(31)]
    window_md = {(d.month, d.day) for d in window}

    upcoming_birthdays = []
    for c in Contact.objects.for_org(org).filter(date_of_birth__isnull=False, is_active=True).annotate(
        bm=ExtractMonth("date_of_birth"), bd=ExtractDay("date_of_birth")
    ):
        if (c.bm, c.bd) not in window_md:
            continue
        try:
            bday = c.date_of_birth.replace(year=today.year)
        except ValueError:
            bday = c.date_of_birth.replace(year=today.year, day=28)
        if bday < today:
            bday = bday.replace(year=today.year + 1)
        upcoming_birthdays.append({"contact": c, "birthday": bday, "days_until": (bday - today).days})
    upcoming_birthdays.sort(key=lambda x: x["days_until"])

    # ── 4. Home anniversaries (next 30 days) ────────────────────────
    upcoming_anniversaries = []
    for c in Contact.objects.for_org(org).filter(home_anniversary__isnull=False, is_active=True).annotate(
        am=ExtractMonth("home_anniversary"), ad=ExtractDay("home_anniversary")
    ):
        if (c.am, c.ad) not in window_md:
            continue
        try:
            anniv = c.home_anniversary.replace(year=today.year)
        except ValueError:
            anniv = c.home_anniversary.replace(year=today.year, day=28)
        if anniv < today:
            anniv = anniv.replace(year=today.year + 1)
        years = anniv.year - c.home_anniversary.year
        upcoming_anniversaries.append({
            "contact": c, "anniv_date": anniv,
            "days_until": (anniv - today).days, "years": years,
        })
    upcoming_anniversaries.sort(key=lambda x: x["days_until"])

    # ── 5. Open house visitors needing follow-up ────────────────────
    from open_houses.models import OpenHouseVisitor
    unfollowed = (
        OpenHouseVisitor.objects
        .filter(open_house__organization=org, followed_up=False, contact__isnull=True)
        .select_related("open_house")
        .order_by("signed_in_at")[:15]
    )

    return render(request, "contacts/follow_up.html", {
        "no_next_step":           no_next_step,
        "going_cold":             going_cold,
        "upcoming_birthdays":     upcoming_birthdays,
        "upcoming_anniversaries": upcoming_anniversaries,
        "unfollowed_visitors":    unfollowed,
        "today":                  today,
    })


@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def generate_reminders(request):
    """Create birthday/anniversary follow-up tasks for the next 30 days (idempotent)."""
    from datetime import timedelta
    from django.db.models.functions import ExtractMonth, ExtractDay
    from django.utils import timezone
    from tasks.models import Task

    if request.method != "POST":
        return redirect("contacts:follow_up")

    membership = request.user.memberships.filter(is_active=True).select_related("organization").first()
    org   = membership.organization if membership else None
    today = timezone.localdate()
    window_md = {(d.month, d.day) for d in [today + timedelta(days=i) for i in range(31)]}
    created = 0

    def _next_occurrence(d):
        try:
            result = d.replace(year=today.year)
        except ValueError:
            result = d.replace(year=today.year, day=28)
        if result < today:
            try:
                result = d.replace(year=today.year + 1)
            except ValueError:
                result = d.replace(year=today.year + 1, day=28)
        return result

    for c in Contact.objects.for_org(org).filter(date_of_birth__isnull=False, is_active=True).annotate(
        bm=ExtractMonth("date_of_birth"), bd=ExtractDay("date_of_birth")
    ):
        if (c.bm, c.bd) not in window_md:
            continue
        due   = _next_occurrence(c.date_of_birth)
        title = f"Birthday follow-up — {c.full_name}"
        if not Task.objects.for_org(org).filter(
            contact=c, title=title, due_date=due,
            status__in=[Task.Status.PENDING, Task.Status.IN_PROGRESS],
        ).exists():
            Task.objects.create(
                organization=org, title=title, task_type=Task.TaskType.FOLLOW_UP,
                contact=c, assigned_to=request.user, due_date=due,
                priority=Task.Priority.NORMAL, status=Task.Status.PENDING,
                description=f"Reach out to {c.full_name} for their birthday.",
            )
            created += 1

    for c in Contact.objects.for_org(org).filter(home_anniversary__isnull=False, is_active=True).annotate(
        am=ExtractMonth("home_anniversary"), ad=ExtractDay("home_anniversary")
    ):
        if (c.am, c.ad) not in window_md:
            continue
        due   = _next_occurrence(c.home_anniversary)
        years = due.year - c.home_anniversary.year
        title = f"Home anniversary — {c.full_name} ({years} yr)"
        if not Task.objects.for_org(org).filter(
            contact=c, title=title, due_date=due,
            status__in=[Task.Status.PENDING, Task.Status.IN_PROGRESS],
        ).exists():
            Task.objects.create(
                organization=org, title=title, task_type=Task.TaskType.FOLLOW_UP,
                contact=c, assigned_to=request.user, due_date=due,
                priority=Task.Priority.NORMAL, status=Task.Status.PENDING,
                description=f"Happy {years}-year home anniversary to {c.full_name}!",
            )
            created += 1

    if created:
        messages.success(request, f"Created {created} reminder task{'s' if created != 1 else ''} for upcoming birthdays and anniversaries.")
    else:
        messages.info(request, "No new reminders needed — all upcoming events already have tasks.")
    return redirect("contacts:follow_up")


# ------------------------------------------------------------------ #
# CSV Export
# ------------------------------------------------------------------ #

@login_required
def contact_export(request):
    membership = request.user.memberships.filter(is_active=True).select_related("organization").first()
    org = membership.organization if membership else None

    qs = Contact.objects.for_org(org).filter(is_active=True).select_related("assigned_to").order_by("last_name", "first_name")

    # Honour same filters as list view
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(primary_email__icontains=q) | Q(primary_phone__icontains=q))
    ctype = request.GET.get("type", "")
    if ctype:
        qs = qs.filter(contact_type=ctype)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="contacts_export.csv"'

    writer = csv.writer(response)
    writer.writerow([
        "First Name", "Last Name", "Email", "Phone",
        "Contact Type", "Source", "Assigned To",
        "Address", "City", "State", "Zip",
        "Employer", "Notes", "Created",
    ])
    for c in qs:
        writer.writerow([
            c.first_name, c.last_name, c.primary_email, c.primary_phone,
            c.get_contact_type_display(), c.get_source_display(),
            c.assigned_to.full_name if c.assigned_to else "",
            c.address, c.city, c.state, c.zip_code,
            c.employer, c.notes, c.created_at.strftime("%Y-%m-%d"),
        ])
    return response


# ------------------------------------------------------------------ #
# CSV Import
# ------------------------------------------------------------------ #

# Fields agents can map CSV columns to
IMPORT_FIELD_CHOICES = [
    ("",               "— Skip this column —"),
    ("first_name",     "First Name"),
    ("last_name",      "Last Name"),
    ("primary_email",  "Email"),
    ("primary_phone",  "Phone"),
    ("contact_type",   "Contact Type"),
    ("source",         "Lead Source"),
    ("address",        "Address"),
    ("city",           "City"),
    ("state",          "State"),
    ("zip_code",       "Zip Code"),
    ("employer",       "Employer"),
    ("preferred_areas","Preferred Areas"),
    ("notes",          "Notes"),
    ("tags",           "Tags (comma-separated)"),
]

# Fuzzy auto-detect: lowercase header → field name
_HEADER_MAP = {
    "first": "first_name", "first name": "first_name", "firstname": "first_name",
    "last": "last_name",  "last name": "last_name",  "lastname": "last_name",
    "email": "primary_email", "e-mail": "primary_email", "email address": "primary_email",
    "phone": "primary_phone", "mobile": "primary_phone", "cell": "primary_phone",
    "phone number": "primary_phone", "mobile number": "primary_phone",
    "type": "contact_type", "contact type": "contact_type",
    "source": "source", "lead source": "source",
    "address": "address", "street": "address", "street address": "address",
    "city": "city", "state": "state", "zip": "zip_code", "zip code": "zip_code",
    "postal": "zip_code", "postal code": "zip_code",
    "employer": "employer", "company": "employer", "company name": "employer",
    "notes": "notes", "note": "notes", "comments": "notes",
    "tags": "tags", "tag": "tags",
    "preferred areas": "preferred_areas", "areas": "preferred_areas",
}

# Reverse maps for contact_type and source values
_TYPE_MAP  = {v.lower(): k for k, v in Contact.ContactType.choices}
_TYPE_MAP.update({k.lower(): k for k, v in Contact.ContactType.choices})
_SOURCE_MAP = {v.lower(): k for k, v in Contact.Source.choices}
_SOURCE_MAP.update({k.lower(): k for k, v in Contact.Source.choices})


@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def contact_import(request):
    membership = request.user.memberships.filter(is_active=True).select_related("organization").first()
    org = membership.organization if membership else None

    step = request.POST.get("step", "upload")

    # ── Step 1: show upload form ────────────────────────────────────
    if request.method == "GET":
        return render(request, "contacts/import.html", {
            "step": "upload",
            "field_choices": IMPORT_FIELD_CHOICES,
        })

    # ── Step 2: parse CSV, show mapping UI ─────────────────────────
    if step == "upload":
        uploaded = request.FILES.get("csv_file")
        if not uploaded:
            messages.error(request, "Please select a CSV file.")
            return render(request, "contacts/import.html", {"step": "upload", "field_choices": IMPORT_FIELD_CHOICES})

        try:
            content = uploaded.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            content = uploaded.read().decode("latin-1")

        reader   = csv.reader(io.StringIO(content))
        rows     = list(reader)
        if not rows:
            messages.error(request, "The CSV file is empty.")
            return render(request, "contacts/import.html", {"step": "upload", "field_choices": IMPORT_FIELD_CHOICES})

        headers  = rows[0]
        preview  = rows[1:6]  # first 5 data rows

        # Auto-detect column mapping
        auto_mapping = [_HEADER_MAP.get(h.strip().lower(), "") for h in headers]

        # Store CSV in session for next step
        request.session["import_csv"] = content
        request.session["import_headers"] = headers

        # Build column_info: list of (index, header, auto_field, [sample_val, ...])
        column_info = []
        for i, header in enumerate(headers):
            samples = [row[i] if i < len(row) else "" for row in preview]
            column_info.append({
                "idx":        i,
                "header":     header,
                "auto_field": auto_mapping[i],
                "samples":    [s for s in samples if s][:3],
            })

        return render(request, "contacts/import.html", {
            "step":         "mapping",
            "column_info":  column_info,
            "field_choices": IMPORT_FIELD_CHOICES,
            "total_rows":   len(rows) - 1,
        })

    # ── Step 3: do the import ──────────────────────────────────────
    if step == "import":
        content  = request.session.get("import_csv", "")
        headers  = request.session.get("import_headers", [])
        if not content:
            messages.error(request, "Session expired. Please re-upload the file.")
            return redirect("contacts:import")

        # Build column → field mapping from POST
        mapping = {}
        for i, header in enumerate(headers):
            field = request.POST.get(f"col_{i}", "")
            if field:
                mapping[i] = field

        skip_dupes  = request.POST.get("duplicate_action", "skip") == "skip"

        reader = csv.reader(io.StringIO(content))
        next(reader)  # skip header row

        imported = 0
        updated  = 0
        skipped  = 0
        errors   = []

        for row_num, row in enumerate(reader, start=2):
            if not any(row):
                continue
            data = {}
            tags_val = ""
            for col_idx, field_name in mapping.items():
                if col_idx < len(row):
                    val = row[col_idx].strip()
                    if field_name == "tags":
                        tags_val = val
                    else:
                        data[field_name] = val

            if not data.get("first_name"):
                errors.append(f"Row {row_num}: skipped — no first name.")
                skipped += 1
                continue

            # Normalise contact_type
            if "contact_type" in data:
                ct = _TYPE_MAP.get(data["contact_type"].lower(), "")
                data["contact_type"] = ct or Contact.ContactType.LEAD

            # Normalise source
            if "source" in data:
                src = _SOURCE_MAP.get(data["source"].lower(), "")
                data["source"] = src or Contact.Source.OTHER

            email = data.get("primary_email", "")
            existing = None
            if email:
                existing = Contact.objects.filter(organization=org, primary_email__iexact=email).first()

            if existing:
                if skip_dupes:
                    skipped += 1
                    continue
                # Update
                for field, val in data.items():
                    if val:
                        setattr(existing, field, val)
                existing.save()
                updated += 1
            else:
                try:
                    contact = Contact(organization=org, **data)
                    contact.full_clean(exclude=["organization"])
                    contact.save()
                    # Handle tags
                    if tags_val:
                        from .models import Tag
                        for tag_name in [t.strip() for t in tags_val.split(",") if t.strip()]:
                            tag, _ = Tag.objects.get_or_create(organization=org, name=tag_name[:50])
                            contact.tags.add(tag)
                    imported += 1
                except Exception as e:
                    errors.append(f"Row {row_num}: {e}")
                    skipped += 1

        # Clean up session
        request.session.pop("import_csv", None)
        request.session.pop("import_headers", None)

        return render(request, "contacts/import.html", {
            "step":     "results",
            "imported": imported,
            "updated":  updated,
            "skipped":  skipped,
            "errors":   errors[:20],  # cap display
        })

    return redirect("contacts:import")


# ------------------------------------------------------------------ #
# Quick Task from Contact
# ------------------------------------------------------------------ #

@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def contact_quick_task(request, pk):
    from tasks.models import Task
    from django.utils import timezone

    membership = request.user.memberships.filter(is_active=True).select_related("organization").first()
    org     = membership.organization if membership else None
    contact = get_object_or_404(Contact, pk=pk, organization=org, is_active=True)

    if request.method == "POST":
        title    = request.POST.get("title", "").strip()
        due_date = request.POST.get("due_date", "")
        task_type = request.POST.get("task_type", "call")
        if title:
            Task.objects.create(
                organization = org,
                title        = title,
                task_type    = task_type,
                contact      = contact,
                assigned_to  = request.user,
                due_date     = due_date or timezone.localdate(),
                status       = Task.Status.PENDING,
                priority     = "normal",
            )
            messages.success(request, f'Task "{title}" created.')
        else:
            messages.error(request, "Task title is required.")

    return redirect("contacts:detail", pk=pk)


# ------------------------------------------------------------------ #
# Tag management
# ------------------------------------------------------------------ #

@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def tag_list(request):
    org = _get_org(request)

    if request.method == "POST":
        form = TagForm(request.POST)
        if form.is_valid():
            tag = form.save(commit=False)
            tag.organization = org
            try:
                tag.save()
                messages.success(request, f'Tag "{tag.name}" created.')
            except Exception:
                messages.error(request, f'A tag named "{tag.name}" already exists.')
        else:
            for field, errs in form.errors.items():
                for e in errs:
                    messages.error(request, e)
        return redirect("contacts:tag_list")

    from django.db.models import Count
    tags = (
        Tag.objects
        .filter(organization=org)
        .annotate(contact_count=Count("contacts", distinct=True))
        .order_by("name")
    )
    return render(request, "contacts/tags.html", {
        "tags": tags,
        "form": TagForm(),
        "org": org,
    })


@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def tag_edit(request, pk):
    org = _get_org(request)
    tag = get_object_or_404(Tag, pk=pk, organization=org)

    if request.method == "POST":
        form = TagForm(request.POST, instance=tag)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, f'Tag "{tag.name}" updated.')
            except Exception:
                messages.error(request, "A tag with that name already exists.")
        else:
            for field, errs in form.errors.items():
                for e in errs:
                    messages.error(request, e)

    return redirect("contacts:tag_list")


@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def tag_delete(request, pk):
    org = _get_org(request)
    tag = get_object_or_404(Tag, pk=pk, organization=org)
    if request.method == "POST":
        name = tag.name
        tag.delete()
        messages.success(request, f'Tag "{name}" deleted.')
    return redirect("contacts:tag_list")


# ------------------------------------------------------------------ #
# Contact inline tag assignment
# ------------------------------------------------------------------ #

@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def contact_set_tags(request, pk):
    org = _get_org(request)
    contact = get_object_or_404(Contact, pk=pk, organization=org, is_active=True)

    if request.method == "POST":
        tag_ids = request.POST.getlist("tags")
        valid_tags = Tag.objects.filter(organization=org, pk__in=tag_ids)
        contact.tags.set(valid_tags)
        messages.success(request, "Tags updated.")

    return redirect("contacts:detail", pk=pk)


@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def contact_document_upload(request, pk):
    org = _get_org(request)
    contact = get_object_or_404(Contact, pk=pk, organization=org, is_active=True)

    if request.method == "POST":
        form = ContactDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            doc = form.save(commit=False)
            doc.organization = org
            doc.contact = contact
            doc.uploaded_by = request.user
            doc.save()
            messages.success(request, f'Document "{doc.title}" uploaded.')
        else:
            messages.error(request, "Could not upload document. Check the form and try again.")

    return redirect("contacts:detail", pk=pk)


@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def contact_document_delete(request, pk, doc_pk):
    org = _get_org(request)
    contact = get_object_or_404(Contact, pk=pk, organization=org, is_active=True)
    doc = get_object_or_404(ContactDocument.objects.for_org(org), pk=doc_pk, contact=contact)

    if request.method == "POST":
        title = doc.title
        if doc.file:
            doc.file.delete(save=False)
        doc.delete()
        messages.success(request, f'Document "{title}" deleted.')

    return redirect("contacts:detail", pk=pk)
