from django.conf import settings
from django.db import models

from organizations.mixins import OrgScopedModel


class Notification(OrgScopedModel):

    class Type(models.TextChoices):
        TASK_DUE         = "task_due",         "Task Due"
        TASK_OVERDUE     = "task_overdue",     "Task Overdue"
        CONTACT_ASSIGNED = "contact_assigned", "Contact Assigned"
        BIRTHDAY         = "birthday",         "Birthday Reminder"
        ANNIVERSARY      = "anniversary",      "Anniversary Reminder"
        FOLLOW_UP        = "follow_up",        "Follow-up Needed"
        GENERAL          = "general",          "General"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    notification_type = models.CharField(
        max_length=20, choices=Type.choices, default=Type.GENERAL
    )
    title   = models.CharField(max_length=255)
    body    = models.TextField(blank=True)
    link    = models.CharField(max_length=500, blank=True)
    is_read = models.BooleanField(default=False)

    # Optional FK links
    contact = models.ForeignKey(
        "contacts.Contact",
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name="notifications",
    )
    task = models.ForeignKey(
        "tasks.Task",
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name="notifications",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} → {self.recipient}"

    @property
    def icon(self):
        return {
            "task_due":         "bi-clock-fill",
            "task_overdue":     "bi-exclamation-circle-fill",
            "contact_assigned": "bi-person-fill",
            "birthday":         "bi-cake2-fill",
            "anniversary":      "bi-house-heart-fill",
            "follow_up":        "bi-bell-fill",
            "general":          "bi-info-circle-fill",
        }.get(self.notification_type, "bi-bell-fill")

    @property
    def color(self):
        return {
            "task_due":         "#d97706",
            "task_overdue":     "#dc2626",
            "contact_assigned": "#6366f1",
            "birthday":         "#a21caf",
            "anniversary":      "#16a34a",
            "follow_up":        "#0ea5e9",
            "general":          "#6b7280",
        }.get(self.notification_type, "#6b7280")
