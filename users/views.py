from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
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
from django.urls import reverse_lazy

from .forms import (
    CustomPasswordResetForm,
    CustomSetPasswordForm,
    LoginForm,
    RegistrationForm,
)


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
        membership = request.user.memberships.filter(is_active=True).select_related("organization").first()
        org = membership.organization if membership else None

    today = timezone.localdate()
    ctx = {"org": org}

    if org:
        # ---- stat cards ----
        ctx["contact_count"]    = Contact.objects.for_org(org).count()
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

    membership = (
        request.user.memberships
        .filter(is_active=True)
        .select_related("organization")
        .first()
    )
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

    membership = (
        request.user.memberships
        .filter(is_active=True)
        .select_related("organization")
        .first()
    )
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

    membership = (
        request.user.memberships
        .filter(is_active=True)
        .select_related("organization")
        .first()
    )

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
