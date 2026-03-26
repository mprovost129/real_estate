from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from datetime import timedelta
from zoneinfo import ZoneInfo

from contacts.models import Contact
from contacts.sms import send_sms_message

from .models import OneTimeBroadcast, OneTimeBroadcastDelivery


def get_broadcast_recipients(
    *,
    org,
    channel,
    contact_type="",
    assigned_to=None,
    tags=None,
    city="",
    state="",
    zip_code="",
    inactive_days=None,
):
    qs = Contact.objects.for_org(org).filter(is_active=True)
    if contact_type:
        qs = qs.filter(contact_type=contact_type)
    if assigned_to:
        qs = qs.filter(assigned_to=assigned_to)
    tag_values = list(tags) if tags is not None else []
    if tag_values:
        qs = qs.filter(tags__in=tag_values)
    if city:
        qs = qs.filter(city__iexact=city.strip())
    if state:
        qs = qs.filter(state__iexact=state.strip())
    if zip_code:
        qs = qs.filter(zip_code__iexact=zip_code.strip())
    if inactive_days:
        cutoff = timezone.now() - timedelta(days=int(inactive_days))
        qs = qs.exclude(contact_notes__created_at__gte=cutoff)

    if channel == OneTimeBroadcast.Channel.EMAIL:
        qs = qs.exclude(primary_email="").filter(do_not_contact=False, opted_out_email=False)
    elif channel == OneTimeBroadcast.Channel.SMS:
        qs = qs.exclude(primary_phone="").filter(do_not_contact=False, opted_out_sms=False)
    return qs.distinct().order_by("last_name", "first_name", "id")


def run_one_time_broadcast(*, broadcast):
    recipients = get_broadcast_recipients(
        org=broadcast.organization,
        channel=broadcast.channel,
        contact_type=broadcast.filter_contact_type,
        assigned_to=broadcast.filter_assigned_to,
        tags=list(broadcast.filter_tags.all()),
        city=broadcast.filter_city,
        state=broadcast.filter_state,
        zip_code=broadcast.filter_zip_code,
        inactive_days=broadcast.filter_inactive_days,
    )
    sent_count = 0
    failed_count = 0
    skipped_count = 0
    template = broadcast.template
    max_recipients = getattr(settings, "ONE_TIME_BROADCAST_MAX_RECIPIENTS", 300)

    recipient_total = recipients.count()
    if recipient_total > max_recipients:
        raise ValueError(
            f"Recipient count ({recipient_total}) exceeds broadcast safety limit ({max_recipients})."
        )

    for contact in recipients.iterator():
        context = {
            "first_name": contact.first_name or "",
            "last_name": contact.last_name or "",
            "full_name": contact.full_name or "",
            "address": contact.address or "",
            "agent_name": (contact.assigned_to.full_name if contact.assigned_to else ""),
            "closing_date": "",
            "price": "",
        }
        body = template.preview(context=context)
        body = _apply_legal_footer(channel=broadcast.channel, body=body)
        provider_message_id = ""
        status = OneTimeBroadcastDelivery.Status.SENT
        detail = ""
        if _should_skip_for_quiet_hours(contact=contact):
            status = OneTimeBroadcastDelivery.Status.SKIPPED
            detail = "Skipped due to quiet-hours policy."
            OneTimeBroadcastDelivery.objects.create(
                organization=broadcast.organization,
                broadcast=broadcast,
                contact=contact,
                status=status,
                detail=detail,
                provider_message_id=provider_message_id,
            )
            skipped_count += 1
            continue
        try:
            if broadcast.channel == OneTimeBroadcast.Channel.EMAIL:
                subject = template.preview_subject(context=context) or f"Update from {broadcast.organization.name}"
                send_mail(
                    subject=subject,
                    message=body,
                    from_email=None,
                    recipient_list=[contact.primary_email],
                    fail_silently=False,
                )
                detail = f"Email sent to {contact.primary_email}."
            elif broadcast.channel == OneTimeBroadcast.Channel.SMS:
                result = send_sms_message(to_number=contact.primary_phone, body=body)
                provider_message_id = result.get("message_id", "")
                detail = f"SMS sent to {contact.primary_phone}."
            else:
                status = OneTimeBroadcastDelivery.Status.SKIPPED
                detail = f"Unsupported channel: {broadcast.channel}"
        except Exception as exc:  # noqa: BLE001
            status = OneTimeBroadcastDelivery.Status.FAILED
            detail = str(exc)

        OneTimeBroadcastDelivery.objects.create(
            organization=broadcast.organization,
            broadcast=broadcast,
            contact=contact,
            status=status,
            detail=detail,
            provider_message_id=provider_message_id,
        )
        if status == OneTimeBroadcastDelivery.Status.SENT:
            sent_count += 1
        elif status == OneTimeBroadcastDelivery.Status.FAILED:
            failed_count += 1
        else:
            skipped_count += 1

    broadcast.recipient_count = recipient_total
    broadcast.sent_count = sent_count
    broadcast.failed_count = failed_count
    broadcast.skipped_count = skipped_count
    if recipient_total == 0 or sent_count == 0:
        broadcast.status = OneTimeBroadcast.Status.FAILED
    elif failed_count > 0:
        broadcast.status = OneTimeBroadcast.Status.PARTIAL
    else:
        broadcast.status = OneTimeBroadcast.Status.COMPLETED
    return broadcast


def _should_skip_for_quiet_hours(*, contact):
    if not getattr(settings, "BROADCAST_QUIET_HOURS_ENABLED", True):
        return False
    start_hour = int(getattr(settings, "BROADCAST_QUIET_HOURS_START", 21))
    end_hour = int(getattr(settings, "BROADCAST_QUIET_HOURS_END", 8))
    if start_hour == end_hour:
        return False

    tz_name = (contact.timezone or "").strip() or settings.TIME_ZONE
    try:
        zone = ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001
        zone = ZoneInfo(settings.TIME_ZONE)
    local_now = timezone.now().astimezone(zone)
    hour = local_now.hour

    if start_hour < end_hour:
        return start_hour <= hour < end_hour
    return hour >= start_hour or hour < end_hour


def _apply_legal_footer(*, channel, body):
    if not getattr(settings, "BROADCAST_REQUIRE_LEGAL_FOOTER", True):
        return body
    if channel == OneTimeBroadcast.Channel.EMAIL:
        footer = (getattr(settings, "BROADCAST_EMAIL_LEGAL_FOOTER", "") or "").strip()
    else:
        footer = (getattr(settings, "BROADCAST_SMS_LEGAL_FOOTER", "") or "").strip()
    if not footer:
        return body
    if footer in body:
        return body
    separator = "\n\n"
    return f"{body}{separator}{footer}"


def broadcast_is_approved(broadcast):
    if not broadcast.approval_required:
        return True
    return broadcast.approval_status == OneTimeBroadcast.ApprovalStatus.APPROVED


def broadcast_is_due(broadcast):
    if not broadcast.scheduled_for:
        return True
    return broadcast.scheduled_for <= timezone.now()
