from django.contrib import admin

from .models import (
    CalendarSyncState,
    ExternalCalendarEventMap,
    IntegrationConnection,
    ListingSyncState,
)


@admin.register(IntegrationConnection)
class IntegrationConnectionAdmin(admin.ModelAdmin):
    list_display = [
        "display_name",
        "integration_type",
        "provider",
        "status",
        "organization",
        "last_sync_at",
        "is_active",
    ]
    list_filter = ["integration_type", "provider", "status", "organization", "is_active"]
    search_fields = ["display_name", "external_account_id"]


@admin.register(CalendarSyncState)
class CalendarSyncStateAdmin(admin.ModelAdmin):
    list_display = [
        "remote_calendar_name",
        "connection",
        "user",
        "is_primary",
        "sync_enabled",
        "last_sync_finished_at",
    ]
    list_filter = ["is_primary", "sync_enabled", "organization"]
    search_fields = ["remote_calendar_name", "remote_calendar_id"]


@admin.register(ExternalCalendarEventMap)
class ExternalCalendarEventMapAdmin(admin.ModelAdmin):
    list_display = [
        "event_type",
        "local_object_id",
        "connection",
        "remote_event_id",
        "last_pushed_at",
    ]
    list_filter = ["event_type", "organization"]
    search_fields = ["remote_event_id", "remote_calendar_id"]


@admin.register(ListingSyncState)
class ListingSyncStateAdmin(admin.ModelAdmin):
    list_display = [
        "connection",
        "remote_listing_id",
        "source_mls_number",
        "status",
        "last_synced_at",
    ]
    list_filter = ["status", "organization", "connection__provider"]
    search_fields = ["remote_listing_id", "source_mls_number"]
