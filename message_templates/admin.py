from django.contrib import admin

from .models import (
    AudienceSegment,
    CampaignEnrollment,
    CampaignSendLog,
    DripCampaign,
    DripCampaignStep,
    MessageTemplate,
    OneTimeBroadcast,
    OneTimeBroadcastDelivery,
)


@admin.register(MessageTemplate)
class MessageTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "template_type", "category", "is_active")
    list_filter = ("template_type", "category", "is_active", "organization")
    search_fields = ("name", "subject", "body")


@admin.register(AudienceSegment)
class AudienceSegmentAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "contact_type", "assigned_to", "is_active")
    list_filter = ("contact_type", "is_active", "organization")
    search_fields = ("name", "city", "state", "zip_code")


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


@admin.register(OneTimeBroadcast)
class OneTimeBroadcastAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "channel", "status", "recipient_count", "sent_count", "failed_count")
    list_filter = ("channel", "status", "organization")
    search_fields = ("name", "template__name")


@admin.register(OneTimeBroadcastDelivery)
class OneTimeBroadcastDeliveryAdmin(admin.ModelAdmin):
    list_display = ("broadcast", "contact", "status", "created_at")
    list_filter = ("status", "organization")
    search_fields = ("contact__first_name", "contact__last_name", "detail")
