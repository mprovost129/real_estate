from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Q, Sum
from django.shortcuts import redirect, render
from django.utils import timezone

from compliance.models import AuditEvent
from organizations.models import Membership

def _get_org(request):
    m = (
        request.user.memberships
        .filter(is_active=True)
        .select_related("organization")
        .first()
    )
    return m.organization if m else None


def _get_membership(request):
    return (
        request.user.memberships
        .filter(is_active=True)
        .select_related("organization")
        .first()
    )


# ------------------------------------------------------------------ #
# Overview
# ------------------------------------------------------------------ #

@login_required
def overview(request):
    org = _get_org(request)
    if not org:
        return redirect("dashboard")

    from contacts.models import Contact, ContactNote
    from pipelines.models import Deal, Pipeline
    from properties.models import Property
    from tasks.models import Task

    today     = timezone.localdate()
    now       = timezone.now()
    month_ago = today - timedelta(days=30)
    week_ago  = today - timedelta(days=7)

    # ---- Contact stats ----
    contacts_qs   = Contact.objects.for_org(org).filter(is_active=True)
    contact_total = contacts_qs.count()
    contact_month = contacts_qs.filter(created_at__date__gte=month_ago).count()
    contact_week  = contacts_qs.filter(created_at__date__gte=week_ago).count()

    # Month-over-month: compare last 30d vs prior 30d
    prior_month = contacts_qs.filter(
        created_at__date__gte=today - timedelta(days=60),
        created_at__date__lt=month_ago,
    ).count()
    contact_mom_delta = contact_month - prior_month

    # ---- Deal stats ----
    deals_qs      = Deal.objects.for_org(org)
    active_deals  = deals_qs.filter(status=Deal.Status.ACTIVE)
    deal_count    = active_deals.count()
    pipeline_value = active_deals.aggregate(total=Sum("value"))["total"] or 0

    won_month = deals_qs.filter(
        status=Deal.Status.WON,
        updated_at__date__gte=month_ago,
    ).count()

    # ---- Task stats ----
    tasks_qs          = Task.objects.for_org(org)
    tasks_overdue     = tasks_qs.filter(
        due_date__lt=today,
        status__in=[Task.Status.PENDING, Task.Status.IN_PROGRESS],
    ).count()
    tasks_due_today   = tasks_qs.filter(due_date=today, status__in=[Task.Status.PENDING, Task.Status.IN_PROGRESS]).count()
    tasks_completed_month = tasks_qs.filter(
        status=Task.Status.COMPLETED,
        completed_at__date__gte=month_ago,
    ).count()

    # ---- Property stats ----
    props_active = Property.objects.for_org(org).filter(
        status="active", is_active=True
    ).count()

    # ---- Activity feed ----
    recent_notes = (
        ContactNote.objects.for_org(org)
        .select_related("contact", "author")
        .order_by("-created_at")[:10]
    )

    # ---- Pipeline value by pipeline ----
    pipelines = []
    from pipelines.models import Pipeline as PipelineModel
    for pipeline in PipelineModel.objects.for_org(org).filter(is_active=True).prefetch_related("stages"):
        stages_data = []
        total_val   = 0
        total_count = 0
        for stage in pipeline.stages.filter(is_active=True, is_lost=False).order_by("order"):
            agg = active_deals.filter(pipeline=pipeline, stage=stage).aggregate(
                cnt=Count("id"), val=Sum("value")
            )
            cnt = agg["cnt"] or 0
            val = agg["val"] or 0
            if cnt:
                stages_data.append({
                    "stage": stage,
                    "count": cnt,
                    "value": val,
                })
                total_val   += val
                total_count += cnt
        if total_count:
            pipelines.append({
                "pipeline":   pipeline,
                "stages":     stages_data,
                "total_count": total_count,
                "total_value": total_val,
            })

    ctx = {
        "contact_total":          contact_total,
        "contact_month":          contact_month,
        "contact_week":           contact_week,
        "contact_mom_delta":      contact_mom_delta,
        "deal_count":             deal_count,
        "pipeline_value":         pipeline_value,
        "won_month":              won_month,
        "tasks_overdue":          tasks_overdue,
        "tasks_due_today":        tasks_due_today,
        "tasks_completed_month":  tasks_completed_month,
        "props_active":           props_active,
        "recent_notes":           recent_notes,
        "pipelines":              pipelines,
        "active_section":         "overview",
    }
    return render(request, "reports/overview.html", ctx)


# ------------------------------------------------------------------ #
# Contacts report
# ------------------------------------------------------------------ #

@login_required
def contacts_report(request):
    org = _get_org(request)
    if not org:
        return redirect("dashboard")

    from contacts.models import Contact

    base = Contact.objects.for_org(org).filter(is_active=True)

    # By source
    by_source = (
        base.values("source")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    # By type
    by_type = (
        base.values("contact_type")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    # By assigned agent
    by_agent = (
        base.values("assigned_to__first_name", "assigned_to__last_name", "assigned_to__email")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    # Monthly additions — last 12 months
    today = timezone.localdate()
    monthly = []
    for i in range(11, -1, -1):
        # First day of the month i months ago
        from datetime import date
        year  = today.year
        month = today.month - i
        while month <= 0:
            month += 12
            year  -= 1
        label = date(year, month, 1).strftime("%b %Y")
        next_month = month + 1 if month < 12 else 1
        next_year  = year if month < 12 else year + 1
        cnt = base.filter(
            created_at__year=year,
            created_at__month=month,
        ).count()
        monthly.append({"label": label, "count": cnt})

    # Get display labels for source and type
    from contacts.models import Contact as C
    source_labels = dict(C.Source.choices) if hasattr(C, "Source") else {}
    type_labels   = dict(C.ContactType.choices) if hasattr(C, "ContactType") else {}

    # Enrich queryset results with display labels
    by_source_display = [
        {
            "label": source_labels.get(r["source"], r["source"] or "Unknown"),
            "count": r["count"],
        }
        for r in by_source if r["count"]
    ]
    by_type_display = [
        {
            "label": type_labels.get(r["contact_type"], r["contact_type"] or "Unknown"),
            "count": r["count"],
        }
        for r in by_type if r["count"]
    ]

    ctx = {
        "by_source":   by_source_display,
        "by_type":     by_type_display,
        "by_agent":    by_agent,
        "monthly":     monthly,
        "total":       base.count(),
        "active_section": "contacts",
    }
    return render(request, "reports/contacts.html", ctx)


# ------------------------------------------------------------------ #
# Pipeline report
# ------------------------------------------------------------------ #

@login_required
def pipeline_report(request):
    org = _get_org(request)
    if not org:
        return redirect("dashboard")

    from pipelines.models import Deal, Pipeline

    deals_qs = Deal.objects.for_org(org)
    active   = deals_qs.filter(status=Deal.Status.ACTIVE)

    # Per-pipeline summary
    pipeline_data = []
    for pipeline in Pipeline.objects.for_org(org).filter(is_active=True).prefetch_related("stages"):
        stages = []
        p_total_count = 0
        p_total_value = 0
        for stage in pipeline.stages.filter(is_active=True).order_by("order"):
            agg = active.filter(pipeline=pipeline, stage=stage).aggregate(
                cnt=Count("id"), val=Sum("value")
            )
            stages.append({
                "stage": stage,
                "count": agg["cnt"] or 0,
                "value": agg["val"] or 0,
            })
            p_total_count += agg["cnt"] or 0
            p_total_value += agg["val"] or 0
        pipeline_data.append({
            "pipeline":    pipeline,
            "stages":      stages,
            "total_count": p_total_count,
            "total_value": p_total_value,
        })

    # Overall deal stats
    today     = timezone.localdate()
    month_ago = today - timedelta(days=30)

    total_active     = active.count()
    total_value      = active.aggregate(v=Sum("value"))["v"] or 0
    won_total        = deals_qs.filter(status=Deal.Status.WON).count()
    won_month        = deals_qs.filter(status=Deal.Status.WON, updated_at__date__gte=month_ago).count()
    lost_total       = deals_qs.filter(status=Deal.Status.LOST).count()

    # Won value this month
    won_value_month = (
        deals_qs.filter(status=Deal.Status.WON, updated_at__date__gte=month_ago)
        .aggregate(v=Sum("value"))["v"] or 0
    )

    # Deals by assigned agent
    by_agent = (
        active.values("assigned_to__first_name", "assigned_to__last_name")
        .annotate(count=Count("id"), value=Sum("value"))
        .order_by("-count")
    )

    # ---- Forecast depth ----
    active_deals = list(
        active.select_related("stage", "assigned_to")
        .only("id", "value", "expected_close_date", "entered_stage_at", "stage__probability", "assigned_to__first_name", "assigned_to__last_name")
    )
    weighted_pipeline_value = 0
    forecast_buckets = [
        {"key": "0_30", "label": "0-30 days", "count": 0, "value": 0, "weighted": 0},
        {"key": "31_60", "label": "31-60 days", "count": 0, "value": 0, "weighted": 0},
        {"key": "61_90", "label": "61-90 days", "count": 0, "value": 0, "weighted": 0},
        {"key": "90_plus", "label": "90+ days", "count": 0, "value": 0, "weighted": 0},
        {"key": "unscheduled", "label": "No close date", "count": 0, "value": 0, "weighted": 0},
    ]
    bucket_index = {b["key"]: b for b in forecast_buckets}

    scorecard_map = {}
    won_30 = {
        row["assigned_to"]: row["count"]
        for row in deals_qs.filter(status=Deal.Status.WON, updated_at__date__gte=month_ago)
        .values("assigned_to")
        .annotate(count=Count("id"))
    }
    won_90 = {
        row["assigned_to"]: row["count"]
        for row in deals_qs.filter(status=Deal.Status.WON, updated_at__date__gte=today - timedelta(days=90))
        .values("assigned_to")
        .annotate(count=Count("id"))
    }
    lost_90 = {
        row["assigned_to"]: row["count"]
        for row in deals_qs.filter(status=Deal.Status.LOST, updated_at__date__gte=today - timedelta(days=90))
        .values("assigned_to")
        .annotate(count=Count("id"))
    }

    for deal in active_deals:
        raw_value = float(deal.value or 0)
        probability = (deal.stage.probability or 0) / 100
        weighted_value = raw_value * probability
        weighted_pipeline_value += weighted_value

        if not deal.expected_close_date:
            bucket_key = "unscheduled"
        else:
            days_out = (deal.expected_close_date - today).days
            if days_out <= 30:
                bucket_key = "0_30"
            elif days_out <= 60:
                bucket_key = "31_60"
            elif days_out <= 90:
                bucket_key = "61_90"
            else:
                bucket_key = "90_plus"
        bucket = bucket_index[bucket_key]
        bucket["count"] += 1
        bucket["value"] += raw_value
        bucket["weighted"] += weighted_value

        agent_key = deal.assigned_to_id or 0
        agent_name = (
            f"{deal.assigned_to.first_name} {deal.assigned_to.last_name}".strip()
            if deal.assigned_to_id
            else "Unassigned"
        )
        row = scorecard_map.setdefault(
            agent_key,
            {
                "agent_name": agent_name,
                "active_deals": 0,
                "pipeline_value": 0,
                "weighted_value": 0,
                "days_in_stage_total": 0,
                "stale_count": 0,
                "won_30d": won_30.get(agent_key, 0),
                "won_90d": won_90.get(agent_key, 0),
                "lost_90d": lost_90.get(agent_key, 0),
            },
        )
        row["active_deals"] += 1
        row["pipeline_value"] += raw_value
        row["weighted_value"] += weighted_value
        row["days_in_stage_total"] += deal.days_in_stage
        if deal.is_stale:
            row["stale_count"] += 1

    scorecards = []
    for row in scorecard_map.values():
        total_decisions_90 = row["won_90d"] + row["lost_90d"]
        row["avg_days_in_stage"] = (
            round(row["days_in_stage_total"] / row["active_deals"], 1) if row["active_deals"] else 0
        )
        row["stale_rate"] = (
            round((row["stale_count"] / row["active_deals"]) * 100, 1) if row["active_deals"] else 0
        )
        row["win_rate_90d"] = (
            round((row["won_90d"] / total_decisions_90) * 100, 1) if total_decisions_90 else None
        )
        scorecards.append(row)
    scorecards.sort(key=lambda x: (x["weighted_value"], x["pipeline_value"]), reverse=True)

    forecast_confidence = round((weighted_pipeline_value / float(total_value)) * 100, 1) if total_value else 0

    ctx = {
        "pipeline_data":   pipeline_data,
        "total_active":    total_active,
        "total_value":     total_value,
        "weighted_pipeline_value": weighted_pipeline_value,
        "forecast_confidence": forecast_confidence,
        "won_total":       won_total,
        "won_month":       won_month,
        "lost_total":      lost_total,
        "won_value_month": won_value_month,
        "by_agent":        by_agent,
        "forecast_buckets": forecast_buckets,
        "scorecards":      scorecards,
        "active_section":  "pipeline",
    }
    return render(request, "reports/pipeline.html", ctx)


# ------------------------------------------------------------------ #
# Tasks report
# ------------------------------------------------------------------ #

@login_required
def tasks_report(request):
    org = _get_org(request)
    if not org:
        return redirect("dashboard")

    from tasks.models import Task

    base  = Task.objects.for_org(org)
    today = timezone.localdate()
    month_ago = today - timedelta(days=30)

    # Status breakdown
    status_counts = (
        base.values("status")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    # Type breakdown (active tasks only)
    type_counts = (
        base.filter(status__in=[Task.Status.PENDING, Task.Status.IN_PROGRESS])
        .values("task_type")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    # Priority breakdown (active)
    priority_counts = (
        base.filter(status__in=[Task.Status.PENDING, Task.Status.IN_PROGRESS])
        .values("priority")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    # By assigned agent
    by_agent = (
        base.filter(status__in=[Task.Status.PENDING, Task.Status.IN_PROGRESS])
        .values("assigned_to__first_name", "assigned_to__last_name", "assigned_to__email")
        .annotate(
            total=Count("id"),
            overdue=Count("id", filter=Q(due_date__lt=today)),
        )
        .order_by("-total")
    )

    # Completion trend last 8 weeks
    weekly_completions = []
    for i in range(7, -1, -1):
        week_start = today - timedelta(days=today.weekday()) - timedelta(weeks=i)
        week_end   = week_start + timedelta(days=6)
        cnt = base.filter(
            status=Task.Status.COMPLETED,
            completed_at__date__gte=week_start,
            completed_at__date__lte=week_end,
        ).count()
        weekly_completions.append({
            "label": week_start.strftime("%b %d"),
            "count": cnt,
        })

    # Summary numbers
    pending   = base.filter(status__in=[Task.Status.PENDING, Task.Status.IN_PROGRESS]).count()
    overdue   = base.filter(due_date__lt=today, status__in=[Task.Status.PENDING, Task.Status.IN_PROGRESS]).count()
    completed_month = base.filter(status=Task.Status.COMPLETED, completed_at__date__gte=month_ago).count()
    total_completed = base.filter(status=Task.Status.COMPLETED).count()

    completion_rate = 0
    total_closed = total_completed + base.filter(status=Task.Status.CANCELLED).count()
    total_all = base.count()
    if total_all:
        completion_rate = round((total_completed / total_all) * 100)

    status_labels = dict(Task.Status.choices)
    type_labels   = dict(Task.TaskType.choices)
    priority_labels = dict(Task.Priority.choices)

    ctx = {
        "status_counts":     [{"label": status_labels.get(r["status"], r["status"]), "count": r["count"]} for r in status_counts],
        "type_counts":       [{"label": type_labels.get(r["task_type"], r["task_type"]), "count": r["count"]} for r in type_counts],
        "priority_counts":   [{"label": priority_labels.get(r["priority"], r["priority"]), "count": r["count"]} for r in priority_counts],
        "by_agent":          by_agent,
        "weekly_completions": weekly_completions,
        "pending":           pending,
        "overdue":           overdue,
        "completed_month":   completed_month,
        "total_completed":   total_completed,
        "completion_rate":   completion_rate,
        "active_section":    "tasks",
    }
    return render(request, "reports/tasks.html", ctx)


# ------------------------------------------------------------------ #
# Transactions / GCI report
# ------------------------------------------------------------------ #

@login_required
def transactions_report(request):
    org = _get_org(request)
    if not org:
        return redirect("dashboard")

    from datetime import date
    from transactions.models import Transaction

    today     = timezone.localdate()
    year      = int(request.GET.get("year", today.year))
    year_start = date(year, 1, 1)
    year_end   = date(year, 12, 31)

    base   = Transaction.objects.for_org(org)
    closed = base.filter(status=Transaction.Status.CLOSED)

    # ---- Summary stats ----
    closed_ytd = closed.filter(closed_at__gte=year_start, closed_at__lte=year_end)
    closed_all = closed.count()

    volume_ytd   = closed_ytd.aggregate(v=Sum("purchase_price"))["v"] or 0
    gci_ytd      = closed_ytd.aggregate(v=Sum("commission_amount"))["v"] or 0
    avg_price_ytd = (
        closed_ytd.filter(purchase_price__isnull=False)
        .aggregate(v=Avg("purchase_price"))["v"] or 0
    )
    referral_ytd = closed_ytd.aggregate(v=Sum("referral_fee"))["v"] or 0

    closed_month = closed.filter(
        closed_at__year=today.year,
        closed_at__month=today.month,
    ).count()
    gci_month = closed.filter(
        closed_at__year=today.year,
        closed_at__month=today.month,
    ).aggregate(v=Sum("commission_amount"))["v"] or 0

    # ---- Closings by month (selected year) ----
    monthly = []
    for m in range(1, 13):
        month_closed = closed.filter(closed_at__year=year, closed_at__month=m)
        monthly.append({
            "label": date(year, m, 1).strftime("%b"),
            "count": month_closed.count(),
            "gci":   float(month_closed.aggregate(v=Sum("commission_amount"))["v"] or 0),
            "volume": float(month_closed.aggregate(v=Sum("purchase_price"))["v"] or 0),
        })

    # ---- By transaction type ----
    by_type_qs = (
        closed_ytd
        .values("transaction_type")
        .annotate(count=Count("id"), gci=Sum("commission_amount"), vol=Sum("purchase_price"))
        .order_by("-count")
    )
    tx_type_labels = dict(Transaction.TxType.choices)
    by_type = [
        {
            "label": tx_type_labels.get(r["transaction_type"], r["transaction_type"]),
            "count": r["count"],
            "gci":   r["gci"] or 0,
            "vol":   r["vol"] or 0,
        }
        for r in by_type_qs
    ]

    # ---- By agent (listing agent) ----
    by_agent_listing = (
        closed_ytd
        .filter(listing_agent__isnull=False)
        .values("listing_agent__first_name", "listing_agent__last_name")
        .annotate(count=Count("id"), gci=Sum("commission_amount"), vol=Sum("purchase_price"))
        .order_by("-count")
    )
    by_agent_buying = (
        closed_ytd
        .filter(buyers_agent__isnull=False)
        .values("buyers_agent__first_name", "buyers_agent__last_name")
        .annotate(count=Count("id"), gci=Sum("commission_amount"), vol=Sum("purchase_price"))
        .order_by("-count")
    )

    # ---- Pipeline (active + pending) ----
    pipeline_txs = (
        base
        .filter(status__in=[
            Transaction.Status.ACTIVE,
            Transaction.Status.PENDING,
            Transaction.Status.CLEAR_TO_CLOSE,
        ])
        .select_related("linked_property", "buyer_contact", "seller_contact",
                        "listing_agent", "buyers_agent")
        .order_by("closing_date")
    )
    projected_gci = pipeline_txs.aggregate(v=Sum("commission_amount"))["v"] or 0
    projected_vol = pipeline_txs.aggregate(v=Sum("purchase_price"))["v"] or 0

    # ---- Year range for selector ----
    earliest = closed.order_by("closed_at").values_list("closed_at", flat=True).first()
    first_year = earliest.year if earliest else today.year
    year_range = list(range(today.year, first_year - 1, -1))

    ctx = {
        "year":           year,
        "year_range":     year_range,
        "closed_ytd":     closed_ytd.count(),
        "closed_all":     closed_all,
        "closed_month":   closed_month,
        "volume_ytd":     volume_ytd,
        "gci_ytd":        gci_ytd,
        "gci_month":      gci_month,
        "avg_price_ytd":  avg_price_ytd,
        "referral_ytd":   referral_ytd,
        "monthly":        monthly,
        "by_type":        by_type,
        "by_agent_listing": by_agent_listing,
        "by_agent_buying":  by_agent_buying,
        "pipeline_txs":   pipeline_txs[:20],
        "projected_gci":  projected_gci,
        "projected_vol":  projected_vol,
        "active_section": "transactions",
    }
    return render(request, "reports/transactions.html", ctx)


@login_required
def compliance_report(request):
    membership = _get_membership(request)
    org = membership.organization if membership else None
    if not org:
        return redirect("dashboard")
    if membership.role not in (Membership.Role.ADMIN, Membership.Role.OWNER):
        return redirect("reports:overview")

    now = timezone.now()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    events = AuditEvent.objects.for_org(org).select_related("actor").order_by("-created_at")
    top_actions = (
        events.filter(created_at__gte=month_ago)
        .values("action")
        .annotate(count=Count("id"))
        .order_by("-count")[:10]
    )

    ctx = {
        "events": events[:100],
        "top_actions": top_actions,
        "count_7d": events.filter(created_at__gte=week_ago).count(),
        "count_30d": events.filter(created_at__gte=month_ago).count(),
        "critical_30d": events.filter(created_at__gte=month_ago, severity=AuditEvent.Severity.CRITICAL).count(),
        "active_section": "compliance",
    }
    return render(request, "reports/compliance.html", ctx)
