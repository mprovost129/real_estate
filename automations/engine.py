from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import AutomationRule, AutomationRun


def _match_conditions(rule, context):
    conditions = rule.conditions or {}
    if not conditions:
        return True
    return _match_condition_node(conditions, context)


def _match_condition_node(node, context):
    if not isinstance(node, dict):
        return False

    results = []

    source = context.get("source")
    if node.get("source_in"):
        results.append(source in node["source_in"])

    contact = context.get("contact")
    if node.get("contact_type_in"):
        results.append(bool(contact and contact.contact_type in node["contact_type_in"]))

    deal = context.get("deal")
    if node.get("pipeline_type_in"):
        results.append(bool(deal and deal.pipeline.pipeline_type in node["pipeline_type_in"]))

    to_stage = context.get("to_stage")
    if node.get("stage_in"):
        allowed = {str(x) for x in node["stage_in"]}
        stage_name = to_stage.name if to_stage else ""
        stage_id = str(to_stage.pk) if to_stage else ""
        results.append(bool(to_stage and (stage_name in allowed or stage_id in allowed)))

    task = context.get("task")
    min_days = node.get("days_overdue_gte")
    if min_days is not None:
        if task and task.due_date:
            days_overdue = (timezone.localdate() - task.due_date).days
            results.append(days_overdue >= int(min_days))
        else:
            results.append(False)

    if "all" in node:
        results.append(all(_match_condition_node(child, context) for child in node["all"]))
    if "any" in node:
        results.append(any(_match_condition_node(child, context) for child in node["any"]))
    if "not" in node:
        results.append(not _match_condition_node(node["not"], context))

    return all(results) if results else True


def _resolve_user(organization, action, context):
    User = get_user_model()
    user_id = action.get("user_id")
    if user_id:
        return User.objects.filter(
            pk=user_id,
            memberships__organization=organization,
            memberships__is_active=True,
        ).distinct().first()

    if action.get("use_trigger_user"):
        return context.get("trigger_user")

    return None


def _action_assign_owner(organization, action, context):
    target = action.get("target", "contact")
    user = _resolve_user(organization, action, context)
    if not user:
        return

    if target == "deal" and context.get("deal"):
        deal = context["deal"]
        if deal.assigned_to_id != user.id:
            deal.assigned_to = user
            deal.save(update_fields=["assigned_to", "updated_at"])
        return

    contact = context.get("contact")
    if contact and contact.assigned_to_id != user.id:
        contact.assigned_to = user
        contact.save(update_fields=["assigned_to", "updated_at"])


def _action_create_task(organization, action, context):
    from tasks.models import Task

    contact = context.get("contact")
    deal = context.get("deal")
    trigger_user = context.get("trigger_user")
    assignee = _resolve_user(organization, action, context)
    if not assignee:
        assignee = (deal.assigned_to if deal and deal.assigned_to else None) or (contact.assigned_to if contact else None) or trigger_user

    due_in_days = int(action.get("due_in_days", 0))
    due_date = timezone.localdate() + timedelta(days=due_in_days)
    title = action.get("title", "Automation task")
    description = action.get("description", "")
    task_type = action.get("task_type", Task.TaskType.FOLLOW_UP)
    priority = action.get("priority", Task.Priority.NORMAL)

    Task.objects.create(
        organization=organization,
        title=title,
        description=description,
        task_type=task_type,
        priority=priority,
        status=Task.Status.PENDING,
        due_date=due_date,
        assigned_to=assignee,
        assigned_by=trigger_user,
        contact=contact,
        deal=deal,
    )


def _action_change_stage(organization, action, context):
    from pipelines.models import PipelineStage, Deal

    deal = context.get("deal")
    if not deal:
        return

    stage_id = action.get("stage_id")
    if not stage_id:
        return

    new_stage = PipelineStage.objects.filter(pk=stage_id, pipeline=deal.pipeline).first()
    if not new_stage or new_stage.pk == deal.stage_id:
        return

    deal.stage = new_stage
    deal.entered_stage_at = timezone.now()
    if new_stage.is_won:
        deal.status = Deal.Status.WON
        deal.actual_close_date = timezone.localdate()
    elif new_stage.is_lost:
        deal.status = Deal.Status.LOST
    else:
        deal.status = Deal.Status.ACTIVE
    deal.save(update_fields=["stage", "entered_stage_at", "status", "actual_close_date", "updated_at"])


def _action_create_note(organization, action, context):
    from contacts.models import ContactNote

    contact = context.get("contact")
    if not contact:
        return

    body = action.get("body", "").strip() or "Automation note"
    note_type = action.get("note_type", ContactNote.NoteType.SYSTEM)
    ContactNote.objects.create(
        organization=organization,
        contact=contact,
        author=context.get("trigger_user"),
        note_type=note_type,
        body=body,
    )


def _action_notify(organization, action, context):
    from notifications.models import Notification

    recipient = _resolve_user(organization, action, context)
    if not recipient:
        recipient = context.get("trigger_user")
    if not recipient:
        return

    Notification.objects.create(
        organization=organization,
        recipient=recipient,
        notification_type=Notification.Type.GENERAL,
        title=action.get("title", "Automation notification"),
        body=action.get("body", ""),
        link=action.get("link", ""),
        contact=context.get("contact"),
        task=context.get("task"),
    )


ACTION_HANDLERS = {
    "assign_owner": _action_assign_owner,
    "create_task": _action_create_task,
    "change_stage": _action_change_stage,
    "create_note": _action_create_note,
    "notify": _action_notify,
}


def run_trigger(*, organization, trigger_type, context, object_ref=""):
    """
    Execute all active automation rules for a trigger.
    """
    rules = AutomationRule.objects.for_org(organization).filter(
        is_active=True,
        trigger_type=trigger_type,
    )

    for rule in rules:
        if not _match_conditions(rule, context):
            AutomationRun.objects.create(
                organization=organization,
                rule=rule,
                trigger_type=trigger_type,
                object_ref=object_ref,
                status=AutomationRun.Status.SKIPPED,
                message="Conditions not met.",
            )
            continue

        try:
            with transaction.atomic():
                for action in (rule.actions or []):
                    handler = ACTION_HANDLERS.get(action.get("type"))
                    if handler:
                        handler(organization, action, context)
            AutomationRun.objects.create(
                organization=organization,
                rule=rule,
                trigger_type=trigger_type,
                object_ref=object_ref,
                status=AutomationRun.Status.SUCCESS,
            )
        except Exception as exc:
            AutomationRun.objects.create(
                organization=organization,
                rule=rule,
                trigger_type=trigger_type,
                object_ref=object_ref,
                status=AutomationRun.Status.FAILED,
                message=str(exc),
            )


def preview_trigger(*, organization, trigger_type, context):
    """
    Dry-run preview: returns which rules would run and why.
    """
    rules = AutomationRule.objects.for_org(organization).filter(
        is_active=True,
        trigger_type=trigger_type,
    ).order_by("name")

    results = []
    for rule in rules:
        matched = _match_conditions(rule, context)
        results.append(
            {
                "rule_id": rule.pk,
                "name": rule.name,
                "matched": matched,
                "conditions": rule.conditions or {},
                "actions": rule.actions or [],
                "reason": "Conditions matched." if matched else "Conditions not met.",
            }
        )
    return results
