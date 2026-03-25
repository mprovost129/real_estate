from datetime import timedelta

from django.utils import timezone


def _normalize_task_requirements(stage):
    items = stage.required_tasks or []
    normalized = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        normalized.append(
            {
                "title": title,
                "description": str(item.get("description", "")).strip(),
                "task_type": item.get("task_type", "follow_up"),
                "priority": item.get("priority", "normal"),
                "due_in_days": int(item.get("due_in_days", 0)),
            }
        )
    return normalized


def evaluate_stage_requirements(*, deal, stage):
    from automations.models import AutomationRule
    from lead_forms.models import LeadCaptureForm, LeadFormSubmission
    from tasks.models import Task

    task_requirements = _normalize_task_requirements(stage)
    form_ids = stage.required_form_ids or []
    automation_ids = stage.required_automation_rule_ids or []

    task_statuses = []
    for req in task_requirements:
        existing = (
            Task.objects.for_org(deal.organization)
            .filter(deal=deal, title=req["title"])
            .exclude(status=Task.Status.CANCELLED)
            .order_by("-created_at")
            .first()
        )
        task_statuses.append(
            {
                "title": req["title"],
                "config": req,
                "exists": bool(existing),
                "completed": bool(existing and existing.status == Task.Status.COMPLETED),
                "task_id": existing.pk if existing else None,
            }
        )

    forms = list(
        LeadCaptureForm.objects.for_org(deal.organization)
        .filter(pk__in=form_ids)
        .only("id", "name")
    )
    form_by_id = {f.pk: f for f in forms}
    form_statuses = []
    for form_id in form_ids:
        form_obj = form_by_id.get(form_id)
        submitted = False
        if form_obj and deal.contact_id:
            submitted = LeadFormSubmission.objects.filter(form_id=form_id, contact_id=deal.contact_id).exists()
        form_statuses.append(
            {
                "form_id": form_id,
                "name": form_obj.name if form_obj else f"Form #{form_id}",
                "exists": bool(form_obj),
                "submitted": submitted,
            }
        )

    rules = list(
        AutomationRule.objects.for_org(deal.organization)
        .filter(pk__in=automation_ids)
        .only("id", "name", "is_active")
    )
    rule_by_id = {r.pk: r for r in rules}
    automation_statuses = []
    for rule_id in automation_ids:
        rule_obj = rule_by_id.get(rule_id)
        automation_statuses.append(
            {
                "rule_id": rule_id,
                "name": rule_obj.name if rule_obj else f"Rule #{rule_id}",
                "exists": bool(rule_obj),
                "active": bool(rule_obj and rule_obj.is_active),
            }
        )

    unmet_forms = [f for f in form_statuses if not f["exists"] or not f["submitted"]]
    unmet_automations = [r for r in automation_statuses if not r["exists"] or not r["active"]]
    unmet_tasks_missing = [t for t in task_statuses if not t["exists"]]

    return {
        "task_statuses": task_statuses,
        "form_statuses": form_statuses,
        "automation_statuses": automation_statuses,
        "unmet_forms": unmet_forms,
        "unmet_automations": unmet_automations,
        "unmet_tasks_missing": unmet_tasks_missing,
        "has_any": bool(task_statuses or form_statuses or automation_statuses),
    }


def provision_stage_tasks(*, deal, stage, trigger_user):
    from tasks.models import Task

    created = []
    status = evaluate_stage_requirements(deal=deal, stage=stage)
    for task_item in status["unmet_tasks_missing"]:
        cfg = task_item["config"]
        due_date = timezone.localdate() + timedelta(days=cfg.get("due_in_days", 0))
        task = Task.objects.create(
            organization=deal.organization,
            title=cfg["title"],
            description=cfg.get("description", ""),
            task_type=cfg.get("task_type", Task.TaskType.FOLLOW_UP),
            priority=cfg.get("priority", Task.Priority.NORMAL),
            status=Task.Status.PENDING,
            due_date=due_date,
            assigned_to=deal.assigned_to or trigger_user,
            assigned_by=trigger_user,
            contact=deal.contact,
            deal=deal,
        )
        created.append(task)
    return created


def can_enter_stage(*, deal, stage):
    status = evaluate_stage_requirements(deal=deal, stage=stage)
    blocking = []
    if stage.enforce_requirements:
        if status["unmet_forms"]:
            blocking.append("required forms are missing")
        if status["unmet_automations"]:
            blocking.append("required automation rules are missing/inactive")
    return len(blocking) == 0, status, blocking
