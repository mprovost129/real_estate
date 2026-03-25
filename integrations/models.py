from django.conf import settings
from django.db import models

from organizations.mixins import OrgScopedModel


class IntegrationConnection(OrgScopedModel):
    class IntegrationType(models.TextChoices):
        CALENDAR = "calendar", "Calendar"
        MLS = "mls", "MLS / IDX"
        ZILLOW = "zillow", "Zillow"
        VOICE = "voice", "Voice / Calling"
        ESIGN = "esign", "E-Sign / Docs"

    class Provider(models.TextChoices):
        GOOGLE = "google", "Google"
        OUTLOOK = "outlook", "Outlook / Microsoft 365"
        MLS_GENERIC = "mls_generic", "MLS (Generic)"
        ZILLOW = "zillow", "Zillow"
        GENERIC = "generic", "Generic"

    class Status(models.TextChoices):
        DISCONNECTED = "disconnected", "Disconnected"
        CONNECTING = "connecting", "Connecting"
        CONNECTED = "connected", "Connected"
        ERROR = "error", "Error"

    integration_type = models.CharField(max_length=20, choices=IntegrationType.choices)
    provider = models.CharField(max_length=20, choices=Provider.choices)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DISCONNECTED,
    )
    display_name = models.CharField(max_length=120, blank=True)
    external_account_id = models.CharField(max_length=255, blank=True)
    access_token_encrypted = models.TextField(blank=True)
    refresh_token_encrypted = models.TextField(blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    config = models.JSONField(default=dict, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["integration_type", "provider", "display_name", "created_at"]
        indexes = [
            models.Index(fields=["organization", "integration_type", "provider"]),
            models.Index(fields=["organization", "status", "is_active"]),
        ]

    def __str__(self):
        label = self.display_name or self.get_provider_display()
        return f"{self.get_integration_type_display()} - {label}"


class CalendarSyncState(OrgScopedModel):
    connection = models.ForeignKey(
        IntegrationConnection,
        on_delete=models.CASCADE,
        related_name="calendar_states",
        limit_choices_to={"integration_type": IntegrationConnection.IntegrationType.CALENDAR},
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="calendar_sync_states",
    )
    remote_calendar_id = models.CharField(max_length=255)
    remote_calendar_name = models.CharField(max_length=255, blank=True)
    is_primary = models.BooleanField(default=False)
    sync_enabled = models.BooleanField(default=True)
    last_cursor = models.TextField(blank=True)
    last_sync_started_at = models.DateTimeField(null=True, blank=True)
    last_sync_finished_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        ordering = ["-is_primary", "remote_calendar_name", "remote_calendar_id"]
        unique_together = [("connection", "remote_calendar_id")]

    def __str__(self):
        return self.remote_calendar_name or self.remote_calendar_id


class ExternalCalendarEventMap(OrgScopedModel):
    class EventType(models.TextChoices):
        TASK = "task", "Task"
        OPEN_HOUSE = "open_house", "Open House"
        CLOSING = "closing", "Closing"

    connection = models.ForeignKey(
        IntegrationConnection,
        on_delete=models.CASCADE,
        related_name="calendar_event_maps",
        limit_choices_to={"integration_type": IntegrationConnection.IntegrationType.CALENDAR},
    )
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    local_object_id = models.PositiveBigIntegerField()
    remote_calendar_id = models.CharField(max_length=255, blank=True)
    remote_event_id = models.CharField(max_length=255)
    remote_etag = models.CharField(max_length=255, blank=True)
    last_pushed_at = models.DateTimeField(null=True, blank=True)
    sync_error = models.TextField(blank=True)

    class Meta:
        ordering = ["-updated_at"]
        unique_together = [
            ("connection", "remote_event_id"),
            ("connection", "event_type", "local_object_id"),
        ]
        indexes = [
            models.Index(fields=["organization", "event_type", "local_object_id"]),
        ]

    def __str__(self):
        return f"{self.get_event_type_display()} -> {self.remote_event_id}"


class ListingSyncState(OrgScopedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SYNCED = "synced", "Synced"
        ERROR = "error", "Error"

    connection = models.ForeignKey(
        IntegrationConnection,
        on_delete=models.CASCADE,
        related_name="listing_states",
        limit_choices_to={
            "integration_type__in": [
                IntegrationConnection.IntegrationType.MLS,
                IntegrationConnection.IntegrationType.ZILLOW,
            ]
        },
    )
    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="listing_sync_states",
    )
    remote_listing_id = models.CharField(max_length=255)
    source_mls_number = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    payload_checksum = models.CharField(max_length=128, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        ordering = ["-updated_at"]
        unique_together = [("connection", "remote_listing_id")]
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["organization", "source_mls_number"]),
        ]

    def __str__(self):
        return f"{self.connection.provider}:{self.remote_listing_id}"


class IntegrationSyncRun(OrgScopedModel):
    class RunType(models.TextChoices):
        CALENDAR_PUSH = "calendar_push", "Calendar Push"
        CALENDAR_PULL = "calendar_pull", "Calendar Pull"
        LISTING_SYNC = "listing_sync", "Listing Sync"

    class RunStatus(models.TextChoices):
        SUCCESS = "success", "Success"
        PARTIAL = "partial", "Partial"
        FAILED = "failed", "Failed"

    run_type = models.CharField(max_length=30, choices=RunType.choices)
    status = models.CharField(max_length=20, choices=RunStatus.choices, default=RunStatus.SUCCESS)
    command = models.CharField(max_length=80, blank=True)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    total_items = models.PositiveIntegerField(default=0)
    success_items = models.PositiveIntegerField(default=0)
    failed_items = models.PositiveIntegerField(default=0)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["organization", "run_type", "started_at"]),
            models.Index(fields=["organization", "status", "started_at"]),
        ]

    def __str__(self):
        return f"{self.get_run_type_display()} {self.started_at:%Y-%m-%d %H:%M} ({self.status})"
