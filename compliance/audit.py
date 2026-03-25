from .models import AuditEvent


def log_audit_event(
    *,
    organization,
    action,
    actor=None,
    entity_type="",
    entity_id="",
    severity=AuditEvent.Severity.INFO,
    message="",
    metadata=None,
    request=None,
):
    if not organization:
        return None

    ip_address = None
    user_agent = ""
    if request is not None:
        ip_address = request.META.get("REMOTE_ADDR")
        user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]

    return AuditEvent.objects.create(
        organization=organization,
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id or ""),
        severity=severity,
        message=message,
        metadata=metadata or {},
        ip_address=ip_address,
        user_agent=user_agent,
    )
