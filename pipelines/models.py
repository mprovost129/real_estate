from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from organizations.mixins import OrgScopedModel


class Pipeline(OrgScopedModel):

    class PipelineType(models.TextChoices):
        LEAD = "lead", "Lead"
        BUYER = "buyer", "Buyer"
        SELLER = "seller", "Seller"
        RECRUITING = "recruiting", "Recruiting"
        CUSTOM = "custom", "Custom"

    name = models.CharField(max_length=150)
    pipeline_type = models.CharField(max_length=20, choices=PipelineType.choices)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(
        default=False,
        help_text="Auto-assigned to new contacts of the matching type.",
    )

    class Meta:
        ordering = ["pipeline_type", "name"]
        unique_together = [("organization", "name")]

    def __str__(self):
        return f"{self.name} ({self.get_pipeline_type_display()})"


class PipelineStage(models.Model):

    pipeline = models.ForeignKey(Pipeline, on_delete=models.CASCADE, related_name="stages")
    name = models.CharField(max_length=100)
    order = models.PositiveSmallIntegerField(default=0)
    probability = models.PositiveSmallIntegerField(
        default=0,
        help_text="Likelihood of closing (0–100%).",
    )
    color = models.CharField(max_length=7, default="#6366f1")
    expected_days = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Expected days a deal stays in this stage.",
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    # Terminal stages — exactly one won and one lost per pipeline
    is_won = models.BooleanField(default=False)
    is_lost = models.BooleanField(default=False)
    required_tasks = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "List of task definitions to create/check on stage entry. "
            'Example: [{"title":"Send disclosure","task_type":"document","due_in_days":0,"priority":"high"}]'
        ),
    )
    required_form_ids = models.JSONField(
        default=list,
        blank=True,
        help_text="List of LeadCaptureForm IDs required for this stage.",
    )
    required_automation_rule_ids = models.JSONField(
        default=list,
        blank=True,
        help_text="List of AutomationRule IDs that must be active for this stage.",
    )
    enforce_requirements = models.BooleanField(
        default=False,
        help_text="When enabled, block stage moves if form/automation requirements are unmet.",
    )

    class Meta:
        ordering = ["pipeline", "order"]
        unique_together = [("pipeline", "name")]

    def __str__(self):
        return f"{self.pipeline.name} › {self.name}"


    def clean(self):
        super().clean()
        self._validate_required_tasks()
        self._validate_int_list("required_form_ids", self.required_form_ids)
        self._validate_int_list("required_automation_rule_ids", self.required_automation_rule_ids)

    def _validate_required_tasks(self):
        if self.required_tasks in (None, ""):
            return
        if not isinstance(self.required_tasks, list):
            raise ValidationError({"required_tasks": "required_tasks must be a JSON array."})
        allowed_task_types = {"call", "text", "email", "meeting", "document", "follow_up", "showing", "inspection", "appraisal", "other"}
        allowed_priorities = {"low", "normal", "high", "urgent"}
        for idx, item in enumerate(self.required_tasks):
            prefix = f"required_tasks[{idx}]"
            if not isinstance(item, dict):
                raise ValidationError({"required_tasks": f"{prefix} must be an object."})
            title = str(item.get("title", "")).strip()
            if not title:
                raise ValidationError({"required_tasks": f"{prefix}.title is required."})
            if len(title) > 255:
                raise ValidationError({"required_tasks": f"{prefix}.title must be <= 255 characters."})
            due_in_days = item.get("due_in_days", 0)
            if not isinstance(due_in_days, int) or due_in_days < 0 or due_in_days > 3650:
                raise ValidationError({"required_tasks": f"{prefix}.due_in_days must be an integer between 0 and 3650."})
            if "task_type" in item and item["task_type"] not in allowed_task_types:
                raise ValidationError({"required_tasks": f"{prefix}.task_type is invalid."})
            if "priority" in item and item["priority"] not in allowed_priorities:
                raise ValidationError({"required_tasks": f"{prefix}.priority is invalid."})
            if "description" in item and len(str(item.get("description") or "")) > 5000:
                raise ValidationError({"required_tasks": f"{prefix}.description must be <= 5000 characters."})

    def _validate_int_list(self, field_name, value):
        if value in (None, ""):
            return
        if not isinstance(value, list):
            raise ValidationError({field_name: f"{field_name} must be a JSON array."})
        for idx, item in enumerate(value):
            if not isinstance(item, int) or item < 1:
                raise ValidationError({field_name: f"{field_name}[{idx}] must be a positive integer."})


class Deal(OrgScopedModel):

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        WON = "won", "Won"
        LOST = "lost", "Lost"
        INACTIVE = "inactive", "Inactive"

    # Core relationships
    contact = models.ForeignKey(
        "contacts.Contact",
        on_delete=models.CASCADE,
        related_name="deals",
    )
    pipeline = models.ForeignKey(Pipeline, on_delete=models.PROTECT, related_name="deals")
    stage = models.ForeignKey(PipelineStage, on_delete=models.PROTECT, related_name="deals")
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_deals",
    )

    # Deal details
    title = models.CharField(
        max_length=255, blank=True,
        help_text="Defaults to contact name if blank.",
    )
    value = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Estimated deal value or commission.",
    )
    expected_close_date = models.DateField(null=True, blank=True)
    actual_close_date = models.DateField(null=True, blank=True)

    # Status
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    lost_reason = models.TextField(blank=True)

    # Stage timing — used to detect stale deals
    entered_stage_at = models.DateTimeField(default=timezone.now)

    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title or str(self.contact)

    def save(self, *args, **kwargs):
        if not self.title:
            self.title = str(self.contact)
        super().save(*args, **kwargs)

    @property
    def days_in_stage(self):
        return (timezone.now() - self.entered_stage_at).days

    @property
    def is_stale(self):
        if self.stage.expected_days and self.status == self.Status.ACTIVE:
            return self.days_in_stage > self.stage.expected_days
        return False


class StageHistory(models.Model):
    """Immutable audit trail of every stage change on a deal."""

    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, related_name="stage_history")
    from_stage = models.ForeignKey(
        PipelineStage,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="+",
    )
    to_stage = models.ForeignKey(
        PipelineStage,
        on_delete=models.PROTECT,
        related_name="+",
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="stage_changes",
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["-changed_at"]

    def __str__(self):
        return f"{self.deal} › {self.to_stage.name} ({self.changed_at:%Y-%m-%d})"
