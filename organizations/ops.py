from dataclasses import dataclass
from datetime import datetime, timezone
from io import StringIO
from typing import Callable

from django.core.checks import run_checks
from django.core.management import call_command
from django.db import connection


@dataclass
class OpsCheckResult:
    key: str
    label: str
    status: str  # pass | warn | fail
    detail: str


def _run_check(results, key: str, label: str, fn: Callable[[], OpsCheckResult]):
    try:
        result = fn()
        results.append(result)
    except Exception as exc:  # defensive: ops view should not crash
        results.append(
            OpsCheckResult(
                key=key,
                label=label,
                status="fail",
                detail=f"{type(exc).__name__}: {exc}",
            )
        )


def run_ops_health_check(organization):
    """
    Runs a broad smoke suite intended for SaaS operations monitoring.
    """
    results = []

    def check_workspace():
        if organization is None:
            return OpsCheckResult("workspace", "Workspace Selected", "fail", "No active workspace selected.")
        return OpsCheckResult("workspace", "Workspace Selected", "pass", f"Workspace: {organization.name}")

    def check_database():
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            row = cursor.fetchone()
        if row and row[0] == 1:
            return OpsCheckResult("database", "Database Connectivity", "pass", "Database responded successfully.")
        return OpsCheckResult("database", "Database Connectivity", "fail", "Unexpected database response.")

    def check_system():
        messages = run_checks()
        errors = [m for m in messages if m.level >= 40]
        warnings = [m for m in messages if m.level == 30]
        if errors:
            return OpsCheckResult("system_checks", "Django System Checks", "fail", f"{len(errors)} error(s), {len(warnings)} warning(s).")
        if warnings:
            return OpsCheckResult("system_checks", "Django System Checks", "warn", f"0 errors, {len(warnings)} warning(s).")
        return OpsCheckResult("system_checks", "Django System Checks", "pass", "No warnings or errors.")

    def check_core_queries():
        from contacts.models import Contact
        from pipelines.models import Deal
        from properties.models import Property
        from tasks.models import Task
        from transactions.models import Transaction

        contact_count = Contact.objects.for_org(organization).count() if organization else 0
        task_count = Task.objects.for_org(organization).count() if organization else 0
        deal_count = Deal.objects.for_org(organization).count() if organization else 0
        property_count = Property.objects.for_org(organization).count() if organization else 0
        tx_count = Transaction.objects.for_org(organization).count() if organization else 0
        detail = (
            f"contacts={contact_count}, tasks={task_count}, deals={deal_count}, "
            f"properties={property_count}, transactions={tx_count}"
        )
        return OpsCheckResult("core_queries", "Core Data Queries", "pass", detail)

    def check_ops_commands():
        # Run low-risk checks only. No data mutation.
        out = StringIO()
        call_command("db_isolation_gate", "--json", stdout=out)
        call_command("integration_groundwork_check", stdout=out)
        return OpsCheckResult("ops_commands", "Ops Command Suite", "pass", "Isolation/integration checks executed.")

    _run_check(results, "workspace", "Workspace Selected", check_workspace)
    _run_check(results, "database", "Database Connectivity", check_database)
    _run_check(results, "system_checks", "Django System Checks", check_system)
    _run_check(results, "core_queries", "Core Data Queries", check_core_queries)
    _run_check(results, "ops_commands", "Ops Command Suite", check_ops_commands)

    fail_count = sum(1 for r in results if r.status == "fail")
    warn_count = sum(1 for r in results if r.status == "warn")
    pass_count = sum(1 for r in results if r.status == "pass")
    overall = "pass"
    if fail_count:
        overall = "fail"
    elif warn_count:
        overall = "warn"

    return {
        "ran_at": datetime.now(timezone.utc),
        "overall": overall,
        "results": results,
        "counts": {
            "pass": pass_count,
            "warn": warn_count,
            "fail": fail_count,
            "total": len(results),
        },
    }
