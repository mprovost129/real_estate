"""
Auto-create Notification records when key events happen.

Triggers:
  - Task created/assigned   → notify assignee (task_due / task_overdue)
  - Contact assigned_to set → notify new assignee (contact_assigned)
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone


@receiver(post_save, sender="tasks.Task")
def task_saved(sender, instance, created, **kwargs):
    from notifications.models import Notification

    task = instance
    if not task.assigned_to or not task.organization:
        return

    # Only fire on creation or when status changes to pending/in_progress
    if not created:
        return

    today = timezone.localdate()
    if task.due_date < today:
        ntype = Notification.Type.TASK_OVERDUE
        title = f"Overdue task: {task.title}"
    elif task.due_date == today:
        ntype = Notification.Type.TASK_DUE
        title = f"Task due today: {task.title}"
    else:
        # Due in the future — no notification at creation time
        return

    link = reverse("tasks:detail", kwargs={"pk": task.pk})

    # Deduplicate: don't create same notification twice
    if not Notification.objects.filter(
        recipient=task.assigned_to,
        task=task,
        notification_type=ntype,
    ).exists():
        Notification.objects.create(
            organization=task.organization,
            recipient=task.assigned_to,
            notification_type=ntype,
            title=title,
            body=f"Due: {task.due_date}",
            link=link,
            task=task,
            contact=task.contact,
        )


@receiver(post_save, sender="contacts.Contact")
def contact_assigned(sender, instance, created, **kwargs):
    from notifications.models import Notification

    contact = instance
    if not contact.assigned_to or not contact.organization:
        return

    # Only create a notification when assigned_to is freshly set
    if not created:
        # Check if assigned_to just changed via update_fields hint
        update_fields = kwargs.get("update_fields")
        if update_fields and "assigned_to" not in update_fields:
            return

    link = reverse("contacts:detail", kwargs={"pk": contact.pk})

    if not Notification.objects.filter(
        recipient=contact.assigned_to,
        contact=contact,
        notification_type=Notification.Type.CONTACT_ASSIGNED,
    ).exists():
        Notification.objects.create(
            organization=contact.organization,
            recipient=contact.assigned_to,
            notification_type=Notification.Type.CONTACT_ASSIGNED,
            title=f"Contact assigned: {contact.full_name}",
            body=contact.get_contact_type_display(),
            link=link,
            contact=contact,
        )
