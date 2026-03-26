from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.contrib.auth.views import (
    PasswordChangeDoneView,
    PasswordChangeView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from organizations.models import Membership
from organizations.utils import get_active_membership

from .forms import (
    AddPublicListingByMlsForm,
    AgentPublicProfileForm,
    CustomPasswordResetForm,
    CustomSetPasswordForm,
    LoginForm,
    PublicAgentInquiryForm,
    PublicListingCardForm,
    RegistrationForm,
)
from .models import AgentPublicProfile, PublicListingCard


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    form = LoginForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        if not form.cleaned_data.get("remember_me"):
            request.session.set_expiry(0)  # expire on browser close
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        next_url = request.GET.get("next") or "dashboard"
        return redirect(next_url)

    return render(request, "registration/login.html", {"form": form})


def logout_view(request):
    logout(request)
    return redirect("login")


def register_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, f"Welcome, {user.first_name}! Your account is ready.")
        return redirect("dashboard")

    return render(request, "registration/register.html", {"form": form})


@login_required
def dashboard_view(request):
    from datetime import timedelta

    from django.utils import timezone
    from contacts.models import Contact, ContactNote
    from open_houses.models import OpenHouse
    from pipelines.models import Deal, Pipeline
    from tasks.models import Task
    from transactions.models import Transaction

    org = getattr(request, "_current_org", None)
    if org is None:
        membership = get_active_membership(request)
        org = membership.organization if membership else None

    today = timezone.localdate()
    ctx = {"org": org}

    if org:
        # ---- stat cards ----
        ctx["contact_count"]    = Contact.objects.for_org(org).filter(is_active=True).count()
        ctx["open_deal_count"]  = Deal.objects.for_org(org).filter(status=Deal.Status.ACTIVE).count()
        ctx["tasks_today"]      = (
            Task.objects.for_org(org)
            .filter(assigned_to=request.user, due_date=today, status=Task.Status.PENDING)
            .count()
        )
        ctx["overdue_task_count"] = (
            Task.objects.for_org(org)
            .filter(assigned_to=request.user, due_date__lt=today,
                    status__in=[Task.Status.PENDING, Task.Status.IN_PROGRESS])
            .count()
        )

        # ---- today's task list (max 10) ----
        ctx["task_list"] = (
            Task.objects.for_org(org)
            .filter(assigned_to=request.user, due_date=today,
                    status__in=[Task.Status.PENDING, Task.Status.IN_PROGRESS])
            .select_related("contact")
            .order_by("-priority", "due_time")[:10]
        )

        # ---- overdue tasks (max 5) ----
        ctx["overdue_tasks"] = (
            Task.objects.for_org(org)
            .filter(assigned_to=request.user, due_date__lt=today,
                    status__in=[Task.Status.PENDING, Task.Status.IN_PROGRESS])
            .select_related("contact")
            .order_by("due_date")[:5]
        )

        # ---- recent activity ----
        ctx["recent_activity"] = (
            ContactNote.objects.for_org(org)
            .select_related("contact", "author")
            .order_by("-created_at")[:15]
        )

        # ---- pipeline summary ----
        pipelines = (
            Pipeline.objects.for_org(org)
            .filter(is_active=True)
            .prefetch_related("stages")
        )
        pipeline_summaries = []
        for pipeline in pipelines:
            stages = []
            total  = 0
            for stage in pipeline.stages.filter(is_active=True, is_lost=False).order_by("order"):
                count = Deal.objects.filter(pipeline=pipeline, stage=stage, status=Deal.Status.ACTIVE).count()
                if count:
                    stages.append({"stage": stage, "count": count})
                    total += count
            if stages:
                pipeline_summaries.append({"pipeline": pipeline, "stages": stages, "total": total})
        ctx["pipeline_summaries"] = pipeline_summaries

        # ---- active transactions with upcoming deadlines (next 14 days) ----
        window = today + timedelta(days=14)
        active_txs = (
            Transaction.objects.for_org(org)
            .filter(status__in=[
                Transaction.Status.ACTIVE, Transaction.Status.PENDING,
                Transaction.Status.CLEAR_TO_CLOSE,
            ])
            .select_related("linked_property", "buyer_contact", "seller_contact")
            .order_by("closing_date")
        )
        tx_deadlines = []
        for tx in active_txs:
            upcoming = tx.upcoming_dates   # list of (label, date)
            overdue  = tx.overdue_dates    # list of (label, date)
            if upcoming or overdue:
                tx_deadlines.append({"tx": tx, "upcoming": upcoming, "overdue": overdue})
        ctx["tx_deadlines"] = tx_deadlines[:8]
        ctx["active_tx_count"] = active_txs.count()

        # ---- open houses this week ----
        ctx["upcoming_open_houses"] = (
            OpenHouse.objects.for_org(org)
            .filter(date__gte=today, date__lte=today + timedelta(days=7))
            .select_related("listing", "host")
            .order_by("date", "start_time")[:5]
        )

    return render(request, "dashboard.html", ctx)


# ------------------------------------------------------------------ #
# Calendar
# ------------------------------------------------------------------ #

@login_required
def calendar_view(request):
    import calendar as cal_module
    from datetime import date

    from contacts.models import Contact
    from integrations.models import IntegrationConnection
    from open_houses.models import OpenHouse
    from tasks.models import Task
    from transactions.models import Transaction

    membership = get_active_membership(request)
    org = membership.organization if membership else None

    today = date.today()
    try:
        year  = int(request.GET.get("year",  today.year))
        month = int(request.GET.get("month", today.month))
    except (ValueError, TypeError):
        year, month = today.year, today.month

    # Clamp
    year  = max(2000, min(2099, year))
    month = max(1, min(12, month))

    # Previous / next month
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1

    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    # First and last day of the month
    first_day = date(year, month, 1)
    last_day  = date(year, month, cal_module.monthrange(year, month)[1])

    # ── Fetch data for the month ──────────────────────────────────
    tasks = []
    open_houses = []
    closings = []

    if org:
        tasks = list(
            Task.objects.for_org(org)
            .filter(
                due_date__gte=first_day,
                due_date__lte=last_day,
                status__in=[Task.Status.PENDING, Task.Status.IN_PROGRESS],
            )
            .select_related("contact", "assigned_to")
            .order_by("due_date", "due_time")
        )

        open_houses = list(
            OpenHouse.objects.for_org(org)
            .filter(date__gte=first_day, date__lte=last_day)
            .select_related("listing", "host")
            .order_by("date", "start_time")
        )

        closings = list(
            Transaction.objects.for_org(org)
            .filter(
                closing_date__gte=first_day,
                closing_date__lte=last_day,
                status__in=[
                    Transaction.Status.ACTIVE,
                    Transaction.Status.PENDING,
                    Transaction.Status.CLEAR_TO_CLOSE,
                ],
            )
            .select_related("linked_property", "buyer_contact", "seller_contact")
            .order_by("closing_date")
        )
        calendar_connections = (
            IntegrationConnection.objects.for_org(org)
            .filter(
                integration_type=IntegrationConnection.IntegrationType.CALENDAR,
                is_active=True,
            )
            .order_by("provider", "display_name")
        )
    else:
        calendar_connections = []

    # ── Build calendar grid ───────────────────────────────────────
    # Index events by day number
    tasks_by_day    = {}
    oh_by_day       = {}
    closings_by_day = {}

    for t in tasks:
        tasks_by_day.setdefault(t.due_date.day, []).append(t)
    for oh in open_houses:
        oh_by_day.setdefault(oh.date.day, []).append(oh)
    for tx in closings:
        closings_by_day.setdefault(tx.closing_date.day, []).append(tx)

    # Build 6-row grid (Mon–Sun weeks)
    cal = cal_module.Calendar(firstweekday=6)  # 6 = Sunday
    weeks = cal.monthdayscalendar(year, month)

    grid = []
    for week in weeks:
        row = []
        for day_num in week:
            if day_num == 0:
                row.append(None)
            else:
                row.append({
                    "day":      day_num,
                    "is_today": (day_num == today.day and year == today.year and month == today.month),
                    "tasks":    tasks_by_day.get(day_num, []),
                    "open_houses": oh_by_day.get(day_num, []),
                    "closings": closings_by_day.get(day_num, []),
                })
        grid.append(row)

    month_name = first_day.strftime("%B %Y")

    return render(request, "calendar.html", {
        "year":        year,
        "month":       month,
        "month_pad":   f"{month:02d}",
        "month_name":  month_name,
        "day_names":   ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
        "grid":        grid,
        "prev_year":  prev_year,
        "prev_month": prev_month,
        "next_year":  next_year,
        "next_month": next_month,
        "today":      today,
        "org":        org,
        "membership": membership,
        "task_total":     len(tasks),
        "oh_total":       len(open_houses),
        "closing_total":  len(closings),
        "calendar_connections": calendar_connections,
    })


# ------------------------------------------------------------------ #
# Global search
# ------------------------------------------------------------------ #

@login_required
def global_search(request):
    from contacts.models import Contact
    from properties.models import Property
    from transactions.models import Transaction
    from tasks.models import Task

    membership = get_active_membership(request)
    org = membership.organization if membership else None

    q = request.GET.get("q", "").strip()
    contacts = []
    properties = []
    transactions = []
    tasks = []

    if q and org:
        contacts = (
            Contact.objects.for_org(org)
            .filter(
                is_active=True,
            )
            .filter(
                Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(primary_email__icontains=q)
                | Q(primary_phone__icontains=q)
                | Q(employer__icontains=q)
            )
            .order_by("last_name", "first_name")[:10]
        )

        properties = (
            Property.objects.for_org(org)
            .filter(
                Q(address__icontains=q)
                | Q(city__icontains=q)
                | Q(zip_code__icontains=q)
                | Q(mls_number__icontains=q)
                | Q(neighborhood__icontains=q)
            )
            .order_by("address")[:10]
        )

        transactions = (
            Transaction.objects.for_org(org)
            .filter(
                Q(property_address__icontains=q)
                | Q(mls_number__icontains=q)
                | Q(linked_property__address__icontains=q)
                | Q(linked_property__city__icontains=q)
                | Q(linked_property__zip_code__icontains=q)
                | Q(buyer_contact__first_name__icontains=q)
                | Q(buyer_contact__last_name__icontains=q)
                | Q(seller_contact__first_name__icontains=q)
                | Q(seller_contact__last_name__icontains=q)
            )
            .select_related("linked_property", "buyer_contact", "seller_contact")
            .distinct()
            .order_by("-created_at")[:10]
        )

        tasks = (
            Task.objects.for_org(org)
            .filter(
                status__in=[Task.Status.PENDING, Task.Status.IN_PROGRESS],
            )
            .filter(
                Q(title__icontains=q)
                | Q(description__icontains=q)
                | Q(contact__first_name__icontains=q)
                | Q(contact__last_name__icontains=q)
            )
            .select_related("contact", "assigned_to")
            .order_by("due_date")[:10]
        )

    total = len(contacts) + len(properties) + len(transactions) + len(tasks)

    return render(request, "search_results.html", {
        "q": q,
        "contacts": contacts,
        "properties": properties,
        "transactions": transactions,
        "tasks": tasks,
        "total": total,
        "org": org,
        "membership": membership,
    })


# ------------------------------------------------------------------ #
# Password reset — Django built-ins with custom forms / templates
# ------------------------------------------------------------------ #

class CustomPasswordResetView(PasswordResetView):
    form_class = CustomPasswordResetForm
    template_name = "registration/password_reset.html"
    email_template_name = "registration/emails/password_reset_email.txt"
    subject_template_name = "registration/emails/password_reset_subject.txt"
    success_url = reverse_lazy("password_reset_done")


class CustomPasswordResetDoneView(PasswordResetDoneView):
    template_name = "registration/password_reset_done.html"


class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    form_class = CustomSetPasswordForm
    template_name = "registration/password_reset_confirm.html"
    success_url = reverse_lazy("password_reset_complete")


class CustomPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = "registration/password_reset_complete.html"


class CustomPasswordChangeView(PasswordChangeView):
    template_name = "registration/password_change.html"
    success_url = reverse_lazy("password_change_done")


class CustomPasswordChangeDoneView(PasswordChangeDoneView):
    template_name = "registration/password_change_done.html"


# ------------------------------------------------------------------ #
# Profile settings
# ------------------------------------------------------------------ #

@login_required
def profile_settings(request):
    from organizations.forms import UserProfileForm

    membership = get_active_membership(request)

    form = UserProfileForm(
        user=request.user,
        data=request.POST or None,
    )

    if request.method == "POST" and form.is_valid():
        user = request.user
        user.first_name = form.cleaned_data["first_name"]
        user.last_name  = form.cleaned_data["last_name"]
        user.phone      = form.cleaned_data["phone"]
        user.role       = form.cleaned_data["role"]
        user.save(update_fields=["first_name", "last_name", "phone", "role"])
        messages.success(request, "Profile updated.")
        return redirect("profile_settings")

    return render(request, "settings/profile.html", {
        "form": form,
        "membership": membership,
        "active_section": "profile",
    })


def _resolve_listing_status(raw_status: str):
    value = (raw_status or "").strip().lower()
    if value in {"active"}:
        return PublicListingCard.ListingStatus.ACTIVE, True
    if value in {"pending", "under_contract", "under contract"}:
        return PublicListingCard.ListingStatus.PENDING, True
    if value in {"coming_soon", "coming soon"}:
        return PublicListingCard.ListingStatus.COMING_SOON, True
    if value in {"sold", "closed", "expired", "cancelled", "canceled"}:
        return PublicListingCard.ListingStatus.CLOSED, False
    if value in {"off_market", "off market", "withdrawn"}:
        return PublicListingCard.ListingStatus.OFF_MARKET, False
    return PublicListingCard.ListingStatus.ACTIVE, True


def _split_full_name(full_name: str):
    raw = (full_name or "").strip()
    if not raw:
        return "Website", "Lead"
    parts = raw.split()
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


@login_required
def public_page_settings(request):
    membership = get_active_membership(request)
    if not membership:
        messages.error(request, "No active workspace selected.")
        return redirect("dashboard")

    org = membership.organization
    profile, _ = AgentPublicProfile.objects.get_or_create(
        organization=org,
        user=request.user,
        defaults={
            "agent_display_name": request.user.full_name,
            "contact_email": request.user.email,
            "contact_phone": request.user.phone,
            "broker_name": org.name,
            "page_title": f"{request.user.full_name or request.user.email} Listings",
        },
    )
    if not profile.broker_name:
        profile.broker_name = org.name
        profile.save(update_fields=["broker_name", "updated_at"])

    profile_form = AgentPublicProfileForm(
        request.POST or None,
        request.FILES or None,
        instance=profile,
        prefix="profile",
    )
    add_listing_form = AddPublicListingByMlsForm(request.POST or None, prefix="add")
    selected_card_id = request.GET.get("edit_card") or request.POST.get("card_id")
    selected_card = PublicListingCard.objects.filter(profile=profile, pk=selected_card_id).first() if selected_card_id else None
    card_form = PublicListingCardForm(
        request.POST or None,
        instance=selected_card,
        prefix="card",
    ) if selected_card else None

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save_profile":
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Public page profile updated.")
                return redirect("public_page_settings")
            messages.error(request, "Could not save public page profile. Check the form.")
        elif action == "add_listing":
            if add_listing_form.is_valid():
                mls_id = add_listing_form.cleaned_data["mls_id"].strip()
                is_featured = add_listing_form.cleaned_data["is_featured"]
                created_or_updated = "updated"
                with transaction.atomic():
                    card, created = PublicListingCard.objects.update_or_create(
                        profile=profile,
                        mls_id=mls_id,
                        defaults={
                            "is_featured": is_featured,
                            "is_active": True,
                        },
                    )
                    if created:
                        created_or_updated = "created"

                    try:
                        from integrations.models import IntegrationConnection
                        from integrations.services.listings import get_listing_provider

                        connection = (
                            IntegrationConnection.objects.for_org(org)
                            .filter(
                                integration_type__in=[
                                    IntegrationConnection.IntegrationType.MLS,
                                    IntegrationConnection.IntegrationType.ZILLOW,
                                ],
                                is_active=True,
                                status=IntegrationConnection.Status.CONNECTED,
                            )
                            .order_by("integration_type", "provider", "id")
                            .first()
                        )
                        if connection:
                            record = get_listing_provider(connection).fetch_by_mls(mls_id)
                            if record:
                                status, is_active = _resolve_listing_status(record.status)
                                if record.mlg_can_view is False:
                                    status = PublicListingCard.ListingStatus.OFF_MARKET
                                    is_active = False
                                    messages.warning(
                                        request,
                                        f'Listing "{mls_id}" is not displayable (MlgCanView=false). Card was archived.',
                                    )
                                if record.mlg_can_use and "IDX" not in set(record.mlg_can_use):
                                    status = PublicListingCard.ListingStatus.OFF_MARKET
                                    is_active = False
                                    messages.warning(
                                        request,
                                        f'Listing "{mls_id}" is not IDX-eligible for public display. Card was archived.',
                                    )
                                card.status = status
                                card.is_active = is_active
                                card.title = card.title or f"MLS {record.mls_number}"
                                card.address = record.address or card.address
                                card.city = record.city or card.city
                                card.state = record.state or card.state
                                card.postal_code = record.postal_code or card.postal_code
                                card.price = record.price if record.price is not None else card.price
                                urls = record.photo_urls or []
                                if urls and not card.photo_url:
                                    card.photo_url = urls[0]
                                card.last_synced_at = timezone.now()
                                card.save()
                    except Exception:
                        pass

                messages.success(request, f'Listing card for MLS "{mls_id}" {created_or_updated}.')
                return redirect("public_page_settings")
            messages.error(request, "Could not add listing card. Please provide a valid MLS ID.")
        elif action == "archive_listing":
            card_id = request.POST.get("card_id")
            card = PublicListingCard.objects.filter(profile=profile, pk=card_id).first()
            if card:
                card.is_active = False
                card.status = PublicListingCard.ListingStatus.CLOSED
                card.closed_at = timezone.now()
                card.save(update_fields=["is_active", "status", "closed_at", "updated_at"])
                messages.success(request, f'Listing "{card.mls_id}" archived.')
            return redirect("public_page_settings")
        elif action == "save_listing_card":
            card_id = request.POST.get("card_id")
            card = PublicListingCard.objects.filter(profile=profile, pk=card_id).first()
            if not card:
                messages.error(request, "Listing card not found.")
                return redirect("public_page_settings")

            card_form = PublicListingCardForm(
                request.POST,
                instance=card,
                prefix="card",
            )
            if card_form.is_valid():
                updated_card = card_form.save(commit=False)
                if not updated_card.is_active and not updated_card.closed_at:
                    updated_card.closed_at = timezone.now()
                if updated_card.is_active:
                    updated_card.closed_at = None
                updated_card.save()
                messages.success(request, f'Listing "{updated_card.mls_id}" updated manually.')
                return redirect(f"{reverse('public_page_settings')}?edit_card={updated_card.pk}")
            messages.error(request, "Could not save listing fallback details. Please correct the form.")
            selected_card = card

    cards = profile.listing_cards.order_by("-is_featured", "-updated_at")
    public_url = request.build_absolute_uri(reverse_lazy("public_agent_page", kwargs={"slug": profile.slug}))
    preview_url = f"{public_url}?preview=1"

    return render(
        request,
        "settings/public_page.html",
        {
            "membership": membership,
            "active_section": "public_page",
            "profile": profile,
            "profile_form": profile_form,
            "add_listing_form": add_listing_form,
            "cards": cards,
            "public_url": public_url,
            "preview_url": preview_url,
            "selected_card": selected_card,
            "card_form": card_form,
        },
    )


def public_agent_page(request, slug):
    from contacts.models import Contact, ContactNote
    from tasks.models import Task

    profile = None
    is_preview = False
    preview_requested = request.GET.get("preview") == "1"

    base_qs = AgentPublicProfile.objects.select_related("user", "organization").filter(slug=slug)
    if preview_requested:
        candidate = base_qs.first()
        if candidate:
            membership = get_active_membership(request, organization=candidate.organization_id)
            can_preview = bool(
                membership
                and (
                    request.user.is_authenticated
                    and (
                        request.user.pk == candidate.user_id
                        or membership.role in {Membership.Role.OWNER, Membership.Role.ADMIN}
                    )
                )
            )
            if can_preview:
                profile = candidate
                is_preview = not candidate.is_published
    else:
        profile = base_qs.filter(is_published=True).first()
        if not profile:
            candidate = base_qs.first()
            if candidate and request.user.is_authenticated:
                membership = get_active_membership(request, organization=candidate.organization_id)
                can_preview = bool(
                    membership
                    and (
                        request.user.pk == candidate.user_id
                        or membership.role in {Membership.Role.OWNER, Membership.Role.ADMIN}
                    )
                )
                if can_preview:
                    profile = candidate
                    is_preview = not candidate.is_published

    if not profile:
        from django.http import Http404
        raise Http404("Public agent page not found.")

    cards = profile.listing_cards.filter(is_active=True).order_by("-is_featured", "-updated_at")
    listing_choices = [(card.mls_id, card.address or card.title or f"MLS {card.mls_id}") for card in cards]

    inquiry_form = PublicAgentInquiryForm(
        request.POST or None,
        listing_choices=listing_choices,
    )
    inquiry_submitted = request.GET.get("sent") == "1"

    if request.method == "POST" and inquiry_form.is_valid():
        full_name = inquiry_form.cleaned_data["full_name"]
        first_name, last_name = _split_full_name(full_name)
        email = (inquiry_form.cleaned_data.get("email") or "").strip().lower()
        phone = (inquiry_form.cleaned_data.get("phone") or "").strip()
        selected_mls_id = (inquiry_form.cleaned_data.get("target_mls_id") or "").strip()
        message = inquiry_form.cleaned_data["message"].strip()

        org = profile.organization
        contact = None
        if email:
            contact = Contact.objects.for_org(org).filter(primary_email__iexact=email, is_active=True).first()
        if not contact and phone:
            contact = Contact.objects.for_org(org).filter(primary_phone=phone, is_active=True).first()

        if contact:
            changed_fields = []
            if email and not contact.primary_email:
                contact.primary_email = email
                changed_fields.append("primary_email")
            if phone and not contact.primary_phone:
                contact.primary_phone = phone
                changed_fields.append("primary_phone")
            if changed_fields:
                contact.save(update_fields=[*changed_fields, "updated_at"])
        else:
            contact = Contact.objects.create(
                organization=org,
                first_name=first_name,
                last_name=last_name,
                primary_email=email,
                primary_phone=phone,
                contact_type=Contact.ContactType.LEAD,
                source=Contact.Source.WEBSITE,
                assigned_to=profile.user,
                is_active=True,
            )

        listing_label = f"Listing MLS {selected_mls_id}" if selected_mls_id else "General inquiry"
        note_body = f"{listing_label}\n\n{message}"
        ContactNote.objects.create(
            organization=org,
            contact=contact,
            author=None,
            note_type=ContactNote.NoteType.SYSTEM,
            body=note_body,
        )

        Task.objects.create(
            organization=org,
            title=f"Respond to website inquiry from {contact.display_name}",
            task_type=Task.TaskType.FOLLOW_UP,
            priority=Task.Priority.HIGH,
            status=Task.Status.PENDING,
            description=note_body,
            assigned_to=profile.user,
            assigned_by=profile.user,
            contact=contact,
            due_date=timezone.localdate(),
        )
        return redirect(f"{reverse('public_agent_page', kwargs={'slug': profile.slug})}?sent=1")

    initial_listing_id = request.GET.get("mls", "").strip()
    if request.method == "GET" and initial_listing_id:
        inquiry_form.fields["target_mls_id"].initial = initial_listing_id

    return render(
        request,
        "public/agent_page.html",
        {
            "profile": profile,
            "cards": cards,
            "inquiry_form": inquiry_form,
            "inquiry_submitted": inquiry_submitted,
            "is_preview": is_preview,
        },
    )
