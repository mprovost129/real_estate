import hashlib
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date

from organizations.models import Membership
from organizations.permissions import require_org_role
from organizations.utils import get_active_membership

from .audit import log_audit_event
from .export_utils import (
    build_audit_csv_payload,
    build_simple_pdf,
    build_signed_zip_package,
    build_signed_zip_package_with_pdf,
    persist_export_artifact,
)
from .forms import CompliancePolicyForm
from .models import AuditEvent, ComplianceExport, CompliancePolicy


def _get_org(request):
    membership = get_active_membership(request)
    return membership.organization if membership else None


@login_required
@require_org_role(Membership.Role.ADMIN, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def compliance_dashboard(request):
    org = _get_org(request)
    if not org:
        return redirect("dashboard")

    policy, _ = CompliancePolicy.objects.get_or_create(organization=org)
    form = CompliancePolicyForm(request.POST or None, instance=policy)

    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(request, "Compliance policy updated.")
            return redirect("compliance:dashboard")

    now = timezone.now()
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    cutoff = now - timedelta(days=policy.audit_retention_days)

    events_qs = AuditEvent.objects.for_org(org).select_related("actor")
    recent_events = events_qs[:100]
    paginator = Paginator(recent_events, 25)
    page = paginator.get_page(request.GET.get("page"))

    counts = {
        "last_24h": events_qs.filter(created_at__gte=day_ago).count(),
        "last_7d": events_qs.filter(created_at__gte=week_ago).count(),
        "last_30d": events_qs.filter(created_at__gte=month_ago).count(),
        "critical_30d": events_qs.filter(created_at__gte=month_ago, severity=AuditEvent.Severity.CRITICAL).count(),
    }
    top_actions = (
        events_qs.filter(created_at__gte=month_ago)
        .values("action")
        .annotate(count=Count("id"))
        .order_by("-count")[:10]
    )
    purgeable_now = events_qs.filter(created_at__lt=cutoff).count()
    days_since_last_purge = None
    if policy.last_purged_at:
        days_since_last_purge = (now - policy.last_purged_at).days
    recommended_interval_days = min(14, max(1, policy.audit_retention_days // 8))
    monitor_status = {
        "purge_enabled": policy.purge_enabled,
        "purgeable_now": purgeable_now,
        "days_since_last_purge": days_since_last_purge,
        "has_last_purge": policy.last_purged_at is not None,
        "recommended_interval_days": recommended_interval_days,
        "is_stale": bool(
            policy.purge_enabled
            and (
                policy.last_purged_at is None
                or (days_since_last_purge is not None and days_since_last_purge > recommended_interval_days)
            )
        ),
    }

    return render(
        request,
        "compliance/dashboard.html",
        {
            "org": org,
            "form": form,
            "policy": policy,
            "events_page": page,
            "counts": counts,
            "top_actions": top_actions,
            "recent_exports": ComplianceExport.objects.for_org(org).select_related("requested_by")[:10],
            "monitor_status": monitor_status,
        },
    )


@login_required
@require_org_role(Membership.Role.ADMIN, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def export_audit_csv(request):
    org = _get_org(request)
    if not org:
        return redirect("dashboard")

    date_from = parse_date(request.GET.get("from", ""))
    date_to = parse_date(request.GET.get("to", ""))

    qs = AuditEvent.objects.for_org(org).select_related("actor").order_by("created_at")
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    payload, row_count, checksum = build_audit_csv_payload(qs)
    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"audit_export_{org.pk}_{timestamp}.csv"
    artifact_path = persist_export_artifact(payload=payload, file_name=file_name)

    ComplianceExport.objects.create(
        organization=org,
        requested_by=request.user,
        export_format=ComplianceExport.ExportFormat.CSV,
        date_from=date_from,
        date_to=date_to,
        row_count=row_count,
        sha256=checksum,
        file_name=file_name,
        artifact_path=artifact_path,
        manifest={
            "version": 1,
            "row_count": row_count,
            "csv_sha256": checksum,
            "date_from": str(date_from or ""),
            "date_to": str(date_to or ""),
        },
    )
    log_audit_event(
        organization=org,
        actor=request.user,
        action="compliance.audit_exported",
        entity_type="compliance_export",
        entity_id=file_name,
        severity=AuditEvent.Severity.WARNING,
        message=f"Audit CSV exported ({row_count} rows).",
        metadata={"sha256": checksum, "row_count": row_count, "date_from": str(date_from or ""), "date_to": str(date_to or "")},
        request=request,
    )

    response = HttpResponse(payload, content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{file_name}"'
    response["X-Audit-SHA256"] = checksum
    return response


@login_required
@require_org_role(Membership.Role.ADMIN, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def export_audit_package(request):
    org = _get_org(request)
    if not org:
        return redirect("dashboard")

    date_from = parse_date(request.GET.get("from", ""))
    date_to = parse_date(request.GET.get("to", ""))

    qs = AuditEvent.objects.for_org(org).select_related("actor").order_by("created_at")
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    csv_payload, row_count, csv_checksum = build_audit_csv_payload(qs)
    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"audit_package_{org.pk}_{timestamp}.zip"
    include_pdf = request.GET.get("include_pdf") in ("1", "true", "yes")
    if include_pdf:
        pdf_payload = build_simple_pdf(
            [
                f"Organization ID: {org.pk}",
                f"Generated at: {timezone.now().isoformat()}",
                f"Date from: {date_from or ''}",
                f"Date to: {date_to or ''}",
                f"Row count: {row_count}",
                f"CSV SHA256: {csv_checksum}",
                "",
                "This summary is part of a signed compliance export package.",
            ],
            title="Audit Export Summary",
        )
        pdf_checksum = hashlib.sha256(pdf_payload).hexdigest()
        zip_payload, package_checksum, manifest, signature = build_signed_zip_package_with_pdf(
            file_name=file_name,
            csv_payload=csv_payload,
            csv_sha256=csv_checksum,
            row_count=row_count,
            organization_id=org.pk,
            date_from=date_from,
            date_to=date_to,
            pdf_payload=pdf_payload,
            pdf_sha256=pdf_checksum,
        )
    else:
        zip_payload, package_checksum, manifest, signature = build_signed_zip_package(
            file_name=file_name,
            csv_payload=csv_payload,
            csv_sha256=csv_checksum,
            row_count=row_count,
            organization_id=org.pk,
            date_from=date_from,
            date_to=date_to,
        )
    artifact_path = persist_export_artifact(payload=zip_payload, file_name=file_name)

    ComplianceExport.objects.create(
        organization=org,
        requested_by=request.user,
        export_format=ComplianceExport.ExportFormat.ZIP,
        date_from=date_from,
        date_to=date_to,
        row_count=row_count,
        sha256=package_checksum,
        file_name=file_name,
        artifact_path=artifact_path,
        signature=signature,
        manifest=manifest,
    )
    log_audit_event(
        organization=org,
        actor=request.user,
        action="compliance.audit_package_exported",
        entity_type="compliance_export",
        entity_id=file_name,
        severity=AuditEvent.Severity.WARNING,
        message=f"Signed audit package exported ({row_count} rows).",
        metadata={"sha256": package_checksum, "signature": signature, "row_count": row_count},
        request=request,
    )

    response = HttpResponse(zip_payload, content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{file_name}"'
    response["X-Package-SHA256"] = package_checksum
    response["X-Package-Signature"] = signature
    return response
