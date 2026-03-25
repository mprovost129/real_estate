from django.core.management.base import BaseCommand
from django.utils import timezone

from automations.engine import run_trigger
from automations.models import AutomationRule, AutomationRun
from tasks.models import Task


class Command(BaseCommand):
    help = "Run automation triggers that require scheduled processing (currently task_overdue)."

    def handle(self, *args, **options):
        today = timezone.localdate()
        task_rules_exist = AutomationRule.objects.filter(
            is_active=True,
            trigger_type=AutomationRule.TriggerType.TASK_OVERDUE,
        ).exists()
        if not task_rules_exist:
            self.stdout.write(self.style.SUCCESS("No active task_overdue automation rules."))
            return

        overdue_tasks = Task.objects.filter(
            due_date__lt=today,
            status__in=[Task.Status.PENDING, Task.Status.IN_PROGRESS],
        ).select_related("organization", "assigned_to", "contact", "deal")

        triggered = 0
        for task in overdue_tasks:
            object_ref = f"task:{task.pk}:{today.isoformat()}"
            already = AutomationRun.objects.for_org(task.organization).filter(
                trigger_type=AutomationRule.TriggerType.TASK_OVERDUE,
                object_ref=object_ref,
            ).exists()
            if already:
                continue

            run_trigger(
                organization=task.organization,
                trigger_type=AutomationRule.TriggerType.TASK_OVERDUE,
                context={
                    "task": task,
                    "contact": task.contact,
                    "deal": task.deal,
                    "trigger_user": task.assigned_to,
                    "source": "task_overdue",
                },
                object_ref=object_ref,
            )
            triggered += 1

        self.stdout.write(self.style.SUCCESS(f"Processed overdue-task automation for {triggered} task(s)."))
