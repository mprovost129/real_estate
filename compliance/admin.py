from django.contrib import admin

from .models import AuditEvent, ComplianceExport, CompliancePolicy


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ["created_at", "organization", "action", "severity", "actor", "entity_type", "entity_id"]
    list_filter = ["severity", "action", "organization"]
    search_fields = ["action", "message", "entity_type", "entity_id", "actor__email"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(CompliancePolicy)
class CompliancePolicyAdmin(admin.ModelAdmin):
    list_display = ["organization", "audit_retention_days", "purge_enabled", "last_purged_at"]
    list_filter = ["purge_enabled"]
    search_fields = ["organization__name"]


@admin.register(ComplianceExport)
class ComplianceExportAdmin(admin.ModelAdmin):
    list_display = ["created_at", "organization", "requested_by", "export_format", "row_count", "sha256_short", "signature_short"]
    list_filter = ["export_format", "organization"]
    search_fields = ["organization__name", "requested_by__email", "sha256", "file_name"]

    @admin.display(description="SHA256")
    def sha256_short(self, obj):
        return f"{obj.sha256[:12]}..." if obj.sha256 else ""

    @admin.display(description="Signature")
    def signature_short(self, obj):
        return f"{obj.signature[:12]}..." if obj.signature else "-"
