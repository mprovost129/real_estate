from django.core.exceptions import ValidationError


CONDITION_KEYS = {
    "source_in",
    "contact_type_in",
    "pipeline_type_in",
    "stage_in",
    "days_overdue_gte",
}
LOGIC_KEYS = {"all", "any", "not"}


ACTION_TYPES = {
    "assign_owner",
    "create_task",
    "change_stage",
    "create_note",
    "notify",
}


def _is_str_list(value):
    return isinstance(value, list) and all(isinstance(v, str) and v.strip() for v in value)


def validate_conditions(conditions):
    if conditions is None:
        return
    if not isinstance(conditions, dict):
        raise ValidationError("Conditions must be a JSON object.")

    _validate_condition_node(conditions, path="conditions", depth=0)


def _validate_condition_node(node, path, depth):
    if not isinstance(node, dict):
        raise ValidationError(f"{path} must be a JSON object.")
    if depth > 12:
        raise ValidationError("Conditions nesting is too deep.")

    unknown = set(node.keys()) - CONDITION_KEYS - LOGIC_KEYS
    if unknown:
        raise ValidationError(f"{path} has unknown key(s): {', '.join(sorted(unknown))}.")

    if "all" in node:
        value = node["all"]
        if not isinstance(value, list) or not value:
            raise ValidationError(f"{path}.all must be a non-empty array of condition objects.")
        for idx, child in enumerate(value):
            _validate_condition_node(child, path=f"{path}.all[{idx}]", depth=depth + 1)

    if "any" in node:
        value = node["any"]
        if not isinstance(value, list) or not value:
            raise ValidationError(f"{path}.any must be a non-empty array of condition objects.")
        for idx, child in enumerate(value):
            _validate_condition_node(child, path=f"{path}.any[{idx}]", depth=depth + 1)

    if "not" in node:
        value = node["not"]
        if not isinstance(value, dict):
            raise ValidationError(f"{path}.not must be a condition object.")
        _validate_condition_node(value, path=f"{path}.not", depth=depth + 1)

    if "source_in" in node and not _is_str_list(node["source_in"]):
        raise ValidationError("source_in must be a list of non-empty strings.")

    if "contact_type_in" in node:
        from contacts.models import Contact

        value = node["contact_type_in"]
        if not _is_str_list(value):
            raise ValidationError("contact_type_in must be a list of contact type values.")
        allowed = {choice[0] for choice in Contact.ContactType.choices}
        invalid = [v for v in value if v not in allowed]
        if invalid:
            raise ValidationError(f"Invalid contact_type_in value(s): {', '.join(invalid)}.")

    if "pipeline_type_in" in node:
        from pipelines.models import Pipeline

        value = node["pipeline_type_in"]
        if not _is_str_list(value):
            raise ValidationError("pipeline_type_in must be a list of pipeline type values.")
        allowed = {choice[0] for choice in Pipeline.PipelineType.choices}
        invalid = [v for v in value if v not in allowed]
        if invalid:
            raise ValidationError(f"Invalid pipeline_type_in value(s): {', '.join(invalid)}.")

    if "stage_in" in node:
        value = node["stage_in"]
        if not isinstance(value, list):
            raise ValidationError("stage_in must be a list of stage names or ids.")
        for item in value:
            if not isinstance(item, (str, int)):
                raise ValidationError("stage_in values must be strings or integers.")

    if "days_overdue_gte" in node:
        value = node["days_overdue_gte"]
        if not isinstance(value, int):
            raise ValidationError("days_overdue_gte must be an integer.")
        if value < 0 or value > 3650:
            raise ValidationError("days_overdue_gte must be between 0 and 3650.")


def validate_actions(actions, trigger_type=None):
    if actions is None:
        return
    if not isinstance(actions, list):
        raise ValidationError("Actions must be a JSON array.")
    if not actions:
        raise ValidationError("At least one action is required.")

    from automations.models import AutomationRule
    from contacts.models import ContactNote
    from tasks.models import Task

    for idx, action in enumerate(actions):
        prefix = f"Action #{idx + 1}"
        if not isinstance(action, dict):
            raise ValidationError(f"{prefix} must be a JSON object.")

        action_type = action.get("type")
        if action_type not in ACTION_TYPES:
            raise ValidationError(f"{prefix} has invalid type '{action_type}'.")

        common_allowed = {"type", "user_id", "use_trigger_user"}
        user_id = action.get("user_id")
        if user_id is not None and (not isinstance(user_id, int) or user_id < 1):
            raise ValidationError(f"{prefix}: user_id must be a positive integer.")
        if "use_trigger_user" in action and not isinstance(action["use_trigger_user"], bool):
            raise ValidationError(f"{prefix}: use_trigger_user must be true/false.")

        if action_type == "assign_owner":
            allowed = common_allowed | {"target"}
            _validate_no_unknown_keys(prefix, action, allowed)
            target = action.get("target", "contact")
            if target not in {"contact", "deal"}:
                raise ValidationError(f"{prefix}: target must be 'contact' or 'deal'.")
            if user_id is None and not action.get("use_trigger_user"):
                raise ValidationError(f"{prefix}: provide user_id or set use_trigger_user=true.")

        elif action_type == "create_task":
            allowed = common_allowed | {"title", "description", "due_in_days", "task_type", "priority"}
            _validate_no_unknown_keys(prefix, action, allowed)
            title = str(action.get("title", "")).strip()
            if not title:
                raise ValidationError(f"{prefix}: title is required.")
            if len(title) > 255:
                raise ValidationError(f"{prefix}: title must be <= 255 characters.")
            if "description" in action and len(str(action.get("description") or "")) > 5000:
                raise ValidationError(f"{prefix}: description must be <= 5000 characters.")
            due_in_days = action.get("due_in_days", 0)
            if not isinstance(due_in_days, int):
                raise ValidationError(f"{prefix}: due_in_days must be an integer.")
            if due_in_days < 0 or due_in_days > 3650:
                raise ValidationError(f"{prefix}: due_in_days must be between 0 and 3650.")
            if "task_type" in action:
                valid_task_types = {choice[0] for choice in Task.TaskType.choices}
                if action["task_type"] not in valid_task_types:
                    raise ValidationError(f"{prefix}: invalid task_type.")
            if "priority" in action:
                valid_priorities = {choice[0] for choice in Task.Priority.choices}
                if action["priority"] not in valid_priorities:
                    raise ValidationError(f"{prefix}: invalid priority.")

        elif action_type == "change_stage":
            allowed = {"type", "stage_id"}
            _validate_no_unknown_keys(prefix, action, allowed)
            stage_id = action.get("stage_id")
            if not isinstance(stage_id, int) or stage_id < 1:
                raise ValidationError(f"{prefix}: stage_id must be a positive integer.")
            if trigger_type and trigger_type != AutomationRule.TriggerType.DEAL_STAGE_CHANGED:
                raise ValidationError(
                    f"{prefix}: change_stage is only allowed for trigger '{AutomationRule.TriggerType.DEAL_STAGE_CHANGED}'."
                )

        elif action_type == "create_note":
            allowed = {"type", "body", "note_type"}
            _validate_no_unknown_keys(prefix, action, allowed)
            body = str(action.get("body", "")).strip()
            if not body:
                raise ValidationError(f"{prefix}: body is required.")
            if len(body) > 5000:
                raise ValidationError(f"{prefix}: body must be <= 5000 characters.")
            if "note_type" in action:
                valid_note_types = {choice[0] for choice in ContactNote.NoteType.choices}
                if action["note_type"] not in valid_note_types:
                    raise ValidationError(f"{prefix}: invalid note_type.")

        elif action_type == "notify":
            allowed = common_allowed | {"title", "body", "link"}
            _validate_no_unknown_keys(prefix, action, allowed)
            title = str(action.get("title", "")).strip()
            if not title:
                raise ValidationError(f"{prefix}: title is required.")
            if len(title) > 255:
                raise ValidationError(f"{prefix}: title must be <= 255 characters.")
            if "body" in action and len(str(action.get("body") or "")) > 5000:
                raise ValidationError(f"{prefix}: body must be <= 5000 characters.")
            if "link" in action and len(str(action.get("link") or "")) > 500:
                raise ValidationError(f"{prefix}: link must be <= 500 characters.")
            if user_id is None and not action.get("use_trigger_user"):
                raise ValidationError(f"{prefix}: provide user_id or set use_trigger_user=true.")


def _validate_no_unknown_keys(prefix, action, allowed_keys):
    unknown = set(action.keys()) - set(allowed_keys)
    if unknown:
        raise ValidationError(f"{prefix}: unknown key(s): {', '.join(sorted(unknown))}.")
