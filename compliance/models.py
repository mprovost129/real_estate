from django.conf import settings
from django.db import models

from organizations.mixins import OrgScopedModel


class AuditEvent(OrgScopedModel):
    class Severity(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        CRITICAL = "critical", "Critical"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    action = models.CharField(max_length=120)
    entity_type = models.CharField(max_length=80, blank=True)
    entity_id = models.CharField(max_length=80, blank=True)
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.INFO)
    message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "created_at"]),
            models.Index(fields=["organization", "action"]),
            models.Index(fields=["organization", "entity_type", "entity_id"]),
        ]

    def __str__(self):
        return f"{self.action} ({self.organization_id})"


class CompliancePolicy(OrgScopedModel):
    audit_retention_days = models.PositiveIntegerField(default=365)
    purge_enabled = models.BooleanField(default=False)
    last_purged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "compliance policies"

    def __str__(self):
        return f"Compliance Policy ({self.organization_id})"


class ComplianceExport(OrgScopedModel):
    class ExportFormat(models.TextChoices):
        CSV = "csv", "CSV"
        ZIP = "zip", "ZIP Package"

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="compliance_exports",
    )
    export_format = models.CharField(max_length=10, choices=ExportFormat.choices, default=ExportFormat.CSV)
    date_from = models.DateField(null=True, blank=True)
    date_to = models.DateField(null=True, blank=True)
    row_count = models.PositiveIntegerField(default=0)
    sha256 = models.CharField(max_length=64)
    file_name = models.CharField(max_length=255, blank=True)
    artifact_path = models.CharField(max_length=500, blank=True)
    signature = models.CharField(max_length=128, blank=True)
    manifest = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.export_format} export ({self.organization_id})"
