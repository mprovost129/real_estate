from datetime import timedelta

from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from contacts.sms import send_sms_message
from message_templates.models import (
    CampaignEnrollment,
    CampaignSendLog,
    DripCampaign,
    DripCampaignStep,
)


class Command(BaseCommand):
    help = "Run due drip campaign steps and send messages."

    def handle(self, *args, **options):
        enrolled = self._auto_enroll_contacts()
        sent, failed, completed = self._process_due_enrollments()
        self.stdout.write(
            self.style.SUCCESS(
                f"Campaign runner complete. Auto-enrolled={enrolled}, sent={sent}, failed={failed}, completed={completed}"
            )
        )

    def _auto_enroll_contacts(self):
        from contacts.models import Contact

        count = 0
        campaigns = DripCampaign.objects.filter(is_active=True).select_related("organization")
        for campaign in campaigns:
            if not campaign.enroll_contact_type:
                continue
            first_step = campaign.steps.filter(is_active=True).order_by("order").first()
            if not first_step:
                continue

            contacts = Contact.objects.for_org(campaign.organization).filter(
                is_active=True,
                contact_type=campaign.enroll_contact_type,
            )
            for contact in contacts:
                enrollment, created = CampaignEnrollment.objects.get_or_create(
                    organization=campaign.organization,
                    campaign=campaign,
                    contact=contact,
                    defaults={
                        "status": CampaignEnrollment.Status.ACTIVE,
                        "next_run_at": timezone.now() + timedelta(days=first_step.delay_days),
                    },
                )
                if created:
                    count += 1
        return count

    def _process_due_enrollments(self):
        now = timezone.now()
        enrollments = (
            CampaignEnrollment.objects
            .filter(status=CampaignEnrollment.Status.ACTIVE, next_run_at__lte=now)
            .select_related("campaign", "contact")
            .order_by("next_run_at")
        )
        sent = 0
        failed = 0
        completed = 0

        for enrollment in enrollments:
            campaign = enrollment.campaign
            contact = enrollment.contact

            next_step = (
                campaign.steps
                .filter(is_active=True, order__gt=enrollment.last_step_order)
                .select_related("template")
                .order_by("order")
                .first()
            )
            if not next_step:
                enrollment.status = CampaignEnrollment.Status.COMPLETED
                enrollment.next_run_at = None
                enrollment.save(update_fields=["status", "next_run_at", "updated_at"])
                completed += 1
                continue

            try:
                self._send_step(enrollment, next_step)
                sent += 1
            except Exception as exc:
                CampaignSendLog.objects.create(
                    organization=enrollment.organization,
                    enrollment=enrollment,
                    step=next_step,
                    contact=contact,
                    channel=campaign.channel,
                    status=CampaignSendLog.Status.FAILED,
                    detail=str(exc),
                )
                enrollment.next_run_at = now + timedelta(days=1)
                enrollment.save(update_fields=["next_run_at", "updated_at"])
                failed += 1
                continue

            with transaction.atomic():
                enrollment.last_step_order = next_step.order
                upcoming_step = (
                    campaign.steps
                    .filter(is_active=True, order__gt=next_step.order)
                    .order_by("order")
                    .first()
                )
                if upcoming_step:
                    enrollment.next_run_at = now + timedelta(days=upcoming_step.delay_days)
                else:
                    enrollment.status = CampaignEnrollment.Status.COMPLETED
                    enrollment.next_run_at = None
                    completed += 1
                enrollment.save(update_fields=["last_step_order", "next_run_at", "status", "updated_at"])

        return sent, failed, completed

    def _send_step(self, enrollment, step):
        campaign = enrollment.campaign
        contact = enrollment.contact
        template = step.template

        context = {
            "first_name": contact.first_name or "",
            "last_name": contact.last_name or "",
            "full_name": contact.full_name or "",
            "address": contact.address or "",
            "agent_name": (enrollment.enrolled_by.full_name if enrollment.enrolled_by else ""),
            "closing_date": "",
            "price": "",
        }
        body = template.preview(context=context)
        provider_message_id = ""

        if campaign.channel == DripCampaign.Channel.EMAIL:
            if not contact.primary_email:
                raise ValueError("Contact has no primary email.")
            subject = template.preview_subject(context=context) or f"Update from {enrollment.organization.name}"
            send_mail(
                subject=subject,
                message=body,
                from_email=None,
                recipient_list=[contact.primary_email],
                fail_silently=False,
            )
            detail = f"Email sent to {contact.primary_email}."

        elif campaign.channel == DripCampaign.Channel.SMS:
            if contact.do_not_contact or contact.opted_out_sms:
                raise ValueError("Contact is opted out of SMS.")
            if not contact.primary_phone:
                raise ValueError("Contact has no primary phone.")
            result = send_sms_message(to_number=contact.primary_phone, body=body)
            provider_message_id = result.get("message_id", "")
            detail = f"SMS sent to {contact.primary_phone}."
        else:
            raise ValueError(f"Unsupported campaign channel: {campaign.channel}")

        CampaignSendLog.objects.create(
            organization=enrollment.organization,
            enrollment=enrollment,
            step=step,
            contact=contact,
            channel=campaign.channel,
            status=CampaignSendLog.Status.SENT,
            detail=detail,
            provider_message_id=provider_message_id,
        )
