from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from organizations.mixins import OrgScopedModel
from .validation import validate_actions, validate_conditions


class AutomationRule(OrgScopedModel):
    class TriggerType(models.TextChoices):
        LEAD_CREATED = "lead_created", "Lead Created"
        DEAL_STAGE_CHANGED = "deal_stage_changed", "Deal Stage Changed"
        TASK_OVERDUE = "task_overdue", "Task Overdue"

    name = models.CharField(max_length=200)
    trigger_type = models.CharField(max_length=30, choices=TriggerType.choices)
    is_active = models.BooleanField(default=True)

    # Example:
    # {"source_in": ["website", "open_house"], "pipeline_type_in": ["lead"]}
    conditions = models.JSONField(default=dict, blank=True)

    # Example:
    # [
    #   {"type": "assign_owner", "target": "contact", "user_id": 5},
    #   {"type": "create_task", "title": "Call new lead", "due_in_days": 0}
    # ]
    actions = models.JSONField(default=list, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_automation_rules",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        try:
            validate_conditions(self.conditions or {})
        except ValidationError as exc:
            raise ValidationError({"conditions": exc.messages})
        try:
            validate_actions(self.actions or [], trigger_type=self.trigger_type)
        except ValidationError as exc:
            raise ValidationError({"actions": exc.messages})


class AutomationRun(OrgScopedModel):
    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        SKIPPED = "skipped", "Skipped"
        FAILED = "failed", "Failed"

    rule = models.ForeignKey(
        AutomationRule,
        on_delete=models.CASCADE,
        related_name="runs",
    )
    trigger_type = models.CharField(max_length=30)
    object_ref = models.CharField(
        max_length=120,
        blank=True,
        help_text="Entity reference, e.g. contact:12, deal:45, task:99:2026-03-24",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SUCCESS)
    message = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.rule.name} ({self.status})"
