from django.conf import settings
from django.db import models
from django.utils import timezone

from organizations.mixins import OrgScopedModel


class TaskTemplate(OrgScopedModel):
    """
    Reusable task blueprints. Applied manually or triggered by automations.
    """

    class TaskType(models.TextChoices):
        CALL = "call", "Call"
        TEXT = "text", "Text"
        EMAIL = "email", "Email"
        MEETING = "meeting", "Meeting"
        DOCUMENT = "document", "Document"
        FOLLOW_UP = "follow_up", "Follow-Up"
        SHOWING = "showing", "Showing"
        OPEN_HOUSE = "open_house", "Open House"
        INSPECTION = "inspection", "Inspection"
        APPRAISAL = "appraisal", "Appraisal"
        OTHER = "other", "Other"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"
        URGENT = "urgent", "Urgent"

    name = models.CharField(max_length=200)
    task_type = models.CharField(max_length=20, choices=TaskType.choices, default=TaskType.FOLLOW_UP)
    title_template = models.CharField(
        max_length=255,
        help_text="Use {contact_name}, {agent_name} as merge fields.",
    )
    description_template = models.TextField(blank=True)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    due_days_offset = models.SmallIntegerField(
        default=1,
        help_text="Days from trigger date when this task becomes due. Use 0 for same day.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Task(OrgScopedModel):

    class TaskType(models.TextChoices):
        CALL = "call", "Call"
        TEXT = "text", "Text"
        EMAIL = "email", "Email"
        MEETING = "meeting", "Meeting"
        DOCUMENT = "document", "Document"
        FOLLOW_UP = "follow_up", "Follow-Up"
        SHOWING = "showing", "Showing"
        OPEN_HOUSE = "open_house", "Open House"
        INSPECTION = "inspection", "Inspection"
        APPRAISAL = "appraisal", "Appraisal"
        OTHER = "other", "Other"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"
        URGENT = "urgent", "Urgent"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        SNOOZED = "snoozed", "Snoozed"
        CANCELLED = "cancelled", "Cancelled"

    class Recurrence(models.TextChoices):
        NONE = "none", "Does not repeat"
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"
        BIWEEKLY = "biweekly", "Every 2 weeks"
        MONTHLY = "monthly", "Monthly"
        QUARTERLY = "quarterly", "Quarterly"
        ANNUALLY = "annually", "Annually"

    # ------------------------------------------------------------------ #
    # Core fields
    # ------------------------------------------------------------------ #
    title = models.CharField(max_length=255)
    task_type = models.CharField(max_length=20, choices=TaskType.choices, default=TaskType.FOLLOW_UP)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING)
    description = models.TextField(blank=True)

    # ------------------------------------------------------------------ #
    # Assignment
    # ------------------------------------------------------------------ #
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="assigned_tasks",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="created_tasks",
    )

    # ------------------------------------------------------------------ #
    # Links — all optional; a task can link to a contact, deal, or both
    # ------------------------------------------------------------------ #
    contact = models.ForeignKey(
        "contacts.Contact",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="tasks",
    )
    deal = models.ForeignKey(
        "pipelines.Deal",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="tasks",
    )

    # ------------------------------------------------------------------ #
    # Scheduling
    # ------------------------------------------------------------------ #
    due_date = models.DateField()
    due_time = models.TimeField(null=True, blank=True)
    snooze_until = models.DateTimeField(null=True, blank=True)

    # ------------------------------------------------------------------ #
    # Recurrence
    # ------------------------------------------------------------------ #
    recurrence = models.CharField(max_length=15, choices=Recurrence.choices, default=Recurrence.NONE)
    recurrence_end_date = models.DateField(null=True, blank=True)
    parent_task = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="recurrence_children",
        help_text="Set on auto-generated recurring copies.",
    )

    # ------------------------------------------------------------------ #
    # Completion
    # ------------------------------------------------------------------ #
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="completed_tasks",
    )
    outcome = models.TextField(
        blank=True,
        help_text="What happened? Result of the call, outcome of the meeting, etc.",
    )

    # Template this was created from (for reporting)
    template = models.ForeignKey(
        TaskTemplate,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="tasks",
    )

    class Meta:
        ordering = ["due_date", "due_time", "-priority"]

    def __str__(self):
        return self.title

    # ------------------------------------------------------------------ #
    # Computed properties
    # ------------------------------------------------------------------ #
    @property
    def is_overdue(self):
        if self.status in (self.Status.COMPLETED, self.Status.CANCELLED):
            return False
        if self.snooze_until and timezone.now() < self.snooze_until:
            return False
        return self.due_date < timezone.localdate()

    @property
    def is_due_today(self):
        return (
            self.status == self.Status.PENDING
            and self.due_date == timezone.localdate()
        )

    def complete(self, user, outcome=""):
        """Mark complete and record who did it."""
        self.status = self.Status.COMPLETED
        self.completed_at = timezone.now()
        self.completed_by = user
        self.outcome = outcome
        self.save(update_fields=["status", "completed_at", "completed_by", "outcome", "updated_at"])
        if self.recurrence != self.Recurrence.NONE:
            self._spawn_next_recurrence()

    def snooze(self, until):
        """Push the task off until a future datetime."""
        self.snooze_until = until
        self.status = self.Status.SNOOZED
        self.save(update_fields=["snooze_until", "status", "updated_at"])

    def _spawn_next_recurrence(self):
        """Create the next occurrence of a recurring task."""
        from datetime import timedelta
        from dateutil.relativedelta import relativedelta

        offsets = {
            self.Recurrence.DAILY:     timedelta(days=1),
            self.Recurrence.WEEKLY:    timedelta(weeks=1),
            self.Recurrence.BIWEEKLY:  timedelta(weeks=2),
            self.Recurrence.MONTHLY:   relativedelta(months=1),
            self.Recurrence.QUARTERLY: relativedelta(months=3),
            self.Recurrence.ANNUALLY:  relativedelta(years=1),
        }
        delta = offsets.get(self.recurrence)
        if not delta:
            return

        next_due = self.due_date + delta
        if self.recurrence_end_date and next_due > self.recurrence_end_date:
            return

        Task.objects.create(
            organization=self.organization,
            title=self.title,
            task_type=self.task_type,
            priority=self.priority,
            status=self.Status.PENDING,
            description=self.description,
            assigned_to=self.assigned_to,
            assigned_by=self.assigned_by,
            contact=self.contact,
            deal=self.deal,
            due_date=next_due,
            due_time=self.due_time,
            recurrence=self.recurrence,
            recurrence_end_date=self.recurrence_end_date,
            parent_task=self,
            template=self.template,
        )
