from django.contrib import admin

from .models import CampaignEnrollment, CampaignSendLog, DripCampaign, DripCampaignStep, MessageTemplate


@admin.register(MessageTemplate)
class MessageTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "template_type", "category", "is_active")
    list_filter = ("template_type", "category", "is_active", "organization")
    search_fields = ("name", "subject", "body")


class DripCampaignStepInline(admin.TabularInline):
    model = DripCampaignStep
    extra = 0


@admin.register(DripCampaign)
class DripCampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "channel", "category", "is_active")
    list_filter = ("channel", "category", "is_active", "organization")
    search_fields = ("name",)
    inlines = [DripCampaignStepInline]


@admin.register(CampaignEnrollment)
class CampaignEnrollmentAdmin(admin.ModelAdmin):
    list_display = ("campaign", "contact", "organization", "status", "last_step_order", "next_run_at")
    list_filter = ("status", "campaign", "organization")
    search_fields = ("contact__first_name", "contact__last_name", "campaign__name")


@admin.register(CampaignSendLog)
class CampaignSendLogAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "contact", "channel", "status", "created_at")
    list_filter = ("channel", "status", "organization")
    search_fields = ("contact__first_name", "contact__last_name", "detail")
