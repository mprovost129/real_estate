from django.contrib import admin
from django.utils.html import format_html

from .models import Task, TaskTemplate


@admin.register(TaskTemplate)
class TaskTemplateAdmin(admin.ModelAdmin):
    list_display = ["name", "task_type", "priority", "due_days_offset", "organization", "is_active"]
    list_filter = ["task_type", "priority", "is_active", "organization"]
    search_fields = ["name", "title_template"]
    autocomplete_fields = ["organization"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = [
        "title", "task_type", "priority_badge", "status", "due_date",
        "assigned_to", "contact", "is_overdue_display", "organization",
    ]
    list_filter = ["status", "task_type", "priority", "recurrence", "organization"]
    search_fields = ["title", "contact__first_name", "contact__last_name", "assigned_to__email"]
    autocomplete_fields = ["organization", "assigned_to", "assigned_by", "contact", "deal", "template"]
    readonly_fields = ["completed_at", "completed_by", "created_at", "updated_at"]
    date_hierarchy = "due_date"

    fieldsets = (
        (None, {"fields": ("title", "task_type", "priority", "status", "description")}),
        ("Assignment", {"fields": (("assigned_to", "assigned_by"), "organization")}),
        ("Links", {"fields": ("contact", "deal")}),
        ("Scheduling", {"fields": (("due_date", "due_time"), "snooze_until")}),
        ("Recurrence", {
            "fields": ("recurrence", "recurrence_end_date", "parent_task"),
            "classes": ("collapse",),
        }),
        ("Completion", {
            "fields": ("completed_at", "completed_by", "outcome"),
            "classes": ("collapse",),
        }),
        ("Metadata", {
            "fields": ("template", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description="Priority")
    def priority_badge(self, obj):
        colors = {
            "low": "#94a3b8",
            "normal": "#3b82f6",
            "high": "#f59e0b",
            "urgent": "#ef4444",
        }
        color = colors.get(obj.priority, "#94a3b8")
        return format_html(
            '<span style="padding:2px 8px;border-radius:4px;background:{};color:#fff;font-size:11px">{}</span>',
            color, obj.get_priority_display(),
        )

    @admin.display(description="Overdue", boolean=True)
    def is_overdue_display(self, obj):
        return obj.is_overdue
