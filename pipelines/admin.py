from django.contrib import admin
from django.utils.html import format_html

from .models import Deal, Pipeline, PipelineStage, StageHistory


class PipelineStageInline(admin.TabularInline):
    model = PipelineStage
    extra = 0
    fields = ["order", "name", "probability", "color", "expected_days", "is_won", "is_lost", "enforce_requirements", "is_active"]
    ordering = ["order"]


@admin.register(Pipeline)
class PipelineAdmin(admin.ModelAdmin):
    list_display = ["name", "pipeline_type", "organization", "is_default", "is_active"]
    list_filter = ["pipeline_type", "is_default", "is_active", "organization"]
    search_fields = ["name", "organization__name"]
    autocomplete_fields = ["organization"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [PipelineStageInline]


@admin.register(PipelineStage)
class PipelineStageAdmin(admin.ModelAdmin):
    list_display = [
        "name", "pipeline", "order", "probability", "color_swatch", "expected_days",
        "is_won", "is_lost", "enforce_requirements", "required_counts",
    ]
    list_filter = ["pipeline", "is_won", "is_lost", "is_active"]
    search_fields = ["name", "pipeline__name"]
    ordering = ["pipeline", "order"]
    fields = [
        "pipeline", "name", "order", "probability", "color", "expected_days", "description",
        "is_active", "is_won", "is_lost",
        "required_tasks", "required_form_ids", "required_automation_rule_ids", "enforce_requirements",
    ]

    @admin.display(description="Color")
    def color_swatch(self, obj):
        return format_html(
            '<span style="display:inline-block;width:16px;height:16px;'
            'border-radius:3px;background:{}"></span> {}',
            obj.color, obj.color,
        )

    @admin.display(description="Requirements")
    def required_counts(self, obj):
        return f"T:{len(obj.required_tasks or [])} F:{len(obj.required_form_ids or [])} A:{len(obj.required_automation_rule_ids or [])}"


class StageHistoryInline(admin.TabularInline):
    model = StageHistory
    extra = 0
    fields = ["from_stage", "to_stage", "changed_by", "changed_at", "note"]
    readonly_fields = ["from_stage", "to_stage", "changed_by", "changed_at"]
    ordering = ["-changed_at"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Deal)
class DealAdmin(admin.ModelAdmin):
    list_display = [
        "title", "contact", "pipeline", "stage", "status",
        "value", "expected_close_date", "days_in_stage", "assigned_to",
    ]
    list_filter = ["status", "pipeline", "stage", "organization"]
    search_fields = ["title", "contact__first_name", "contact__last_name"]
    autocomplete_fields = ["contact", "pipeline", "stage", "assigned_to", "organization"]
    readonly_fields = ["entered_stage_at", "created_at", "updated_at", "days_in_stage"]
    inlines = [StageHistoryInline]

    fieldsets = (
        (None, {"fields": ("title", "contact", "organization", "assigned_to")}),
        ("Pipeline", {"fields": ("pipeline", "stage", "status", "lost_reason", "entered_stage_at")}),
        ("Value & Timing", {"fields": ("value", "expected_close_date", "actual_close_date")}),
        ("Notes", {"fields": ("notes",)}),
        ("Metadata", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="Days in stage")
    def days_in_stage(self, obj):
        return obj.days_in_stage
