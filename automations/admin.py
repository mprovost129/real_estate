from django.contrib import admin

from .models import AutomationRule, AutomationRun


@admin.register(AutomationRule)
class AutomationRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "trigger_type", "is_active", "created_at")
    list_filter = ("trigger_type", "is_active", "organization")
    search_fields = ("name",)


@admin.register(AutomationRun)
class AutomationRunAdmin(admin.ModelAdmin):
    list_display = ("rule", "organization", "trigger_type", "status", "object_ref", "created_at")
    list_filter = ("status", "trigger_type", "organization")
    search_fields = ("rule__name", "object_ref", "message")
    readonly_fields = ("created_at", "updated_at")
