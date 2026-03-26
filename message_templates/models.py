from django.conf import settings
from django.db import models

from organizations.mixins import OrgScopedModel


class MessageTemplate(OrgScopedModel):

    class TemplateType(models.TextChoices):
        EMAIL       = "email",       "Email"
        SMS         = "sms",         "SMS / Text"
        CALL_SCRIPT = "call_script", "Call Script"

    class Category(models.TextChoices):
        BUYER_LEAD   = "buyer_lead",   "Buyer Lead"
        SELLER_LEAD  = "seller_lead",  "Seller Lead"
        OPEN_HOUSE   = "open_house",   "Open House"
        PAST_CLIENT  = "past_client",  "Past Client"
        SPHERE       = "sphere",       "Sphere / Referral"
        TRANSACTION  = "transaction",  "Transaction"
        NURTURE      = "nurture",      "Long-Term Nurture"
        GENERAL      = "general",      "General"

    name          = models.CharField(max_length=200)
    template_type = models.CharField(max_length=15, choices=TemplateType.choices, default=TemplateType.EMAIL)
    category      = models.CharField(max_length=20, choices=Category.choices, default=Category.GENERAL)
    subject       = models.CharField(max_length=255, blank=True, help_text="Email subject line (email templates only)")
    body          = models.TextField(help_text="Use {{first_name}}, {{last_name}}, {{full_name}}, {{address}}, {{agent_name}}, {{closing_date}}, {{price}} as merge fields.")
    is_active     = models.BooleanField(default=True)
    created_by    = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="created_templates",
    )

    class Meta:
        ordering = ["template_type", "category", "name"]

    def __str__(self):
        return self.name

    def _fill(self, text, context=None):
        sample = {
            "first_name":   "Alex",
            "last_name":    "Johnson",
            "full_name":    "Alex Johnson",
            "address":      "123 Main St",
            "agent_name":   "Your Agent",
            "closing_date": "April 15, 2026",
            "price":        "$450,000",
        }
        if context:
            sample.update(context)
        for key, val in sample.items():
            text = text.replace(f"{{{{{key}}}}}", val)
        return text

    def preview(self, context=None):
        """Return body with sample merge fields substituted."""
        return self._fill(self.body, context)

    def preview_subject(self, context=None):
        """Return subject with sample merge fields substituted."""
        return self._fill(self.subject, context)


class DripCampaign(OrgScopedModel):
    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"

    name = models.CharField(max_length=200)
    channel = models.CharField(max_length=10, choices=Channel.choices, default=Channel.EMAIL)
    category = models.CharField(max_length=20, choices=MessageTemplate.Category.choices, default=MessageTemplate.Category.GENERAL)
    enroll_contact_type = models.CharField(
        max_length=20,
        blank=True,
        help_text="Optional contact type filter for automatic enrollment.",
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_campaigns",
    )

    class Meta:
        ordering = ["name"]
        unique_together = [("organization", "name")]

    def __str__(self):
        return self.name


class DripCampaignStep(models.Model):
    campaign = models.ForeignKey(DripCampaign, on_delete=models.CASCADE, related_name="steps")
    order = models.PositiveSmallIntegerField(default=1)
    delay_days = models.PositiveSmallIntegerField(
        default=0,
        help_text="Days to wait before this step runs after the previous step.",
    )
    template = models.ForeignKey(
        MessageTemplate,
        on_delete=models.PROTECT,
        related_name="campaign_steps",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["campaign", "order"]
        unique_together = [("campaign", "order")]

    def __str__(self):
        return f"{self.campaign.name} Step {self.order}"


class CampaignEnrollment(OrgScopedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        PAUSED = "paused", "Paused"
        UNSUBSCRIBED = "unsubscribed", "Unsubscribed"

    campaign = models.ForeignKey(DripCampaign, on_delete=models.CASCADE, related_name="enrollments")
    contact = models.ForeignKey("contacts.Contact", on_delete=models.CASCADE, related_name="campaign_enrollments")
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.ACTIVE)
    last_step_order = models.PositiveSmallIntegerField(default=0)
    next_run_at = models.DateTimeField(null=True, blank=True)
    enrolled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="campaign_enrollments_created",
    )

    class Meta:
        ordering = ["next_run_at", "created_at"]
        unique_together = [("campaign", "contact")]

    def __str__(self):
        return f"{self.contact.full_name} -> {self.campaign.name}"


class CampaignSendLog(OrgScopedModel):
    class Status(models.TextChoices):
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    enrollment = models.ForeignKey(CampaignEnrollment, on_delete=models.CASCADE, related_name="send_logs")
    step = models.ForeignKey(
        DripCampaignStep,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="send_logs",
    )
    contact = models.ForeignKey("contacts.Contact", on_delete=models.CASCADE, related_name="campaign_send_logs")
    channel = models.CharField(max_length=10, choices=DripCampaign.Channel.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SENT)
    detail = models.TextField(blank=True)
    provider_message_id = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.campaign_name} {self.status}"

    @property
    def campaign_name(self):
        return self.enrollment.campaign.name


class OneTimeBroadcast(OrgScopedModel):
    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SCHEDULED = "scheduled", "Scheduled"
        COMPLETED = "completed", "Completed"
        PARTIAL = "partial", "Completed With Failures"
        FAILED = "failed", "Failed"

    class ApprovalStatus(models.TextChoices):
        NOT_REQUIRED = "not_required", "Not Required"
        PENDING = "pending", "Pending Approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    name = models.CharField(max_length=200)
    channel = models.CharField(max_length=10, choices=Channel.choices, default=Channel.EMAIL)
    template = models.ForeignKey(
        MessageTemplate,
        on_delete=models.PROTECT,
        related_name="one_time_broadcasts",
    )
    filter_contact_type = models.CharField(
        max_length=20,
        blank=True,
        help_text="Optional filter by contact type.",
    )
    filter_segment = models.ForeignKey(
        "message_templates.AudienceSegment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="broadcasts",
    )
    filter_assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="one_time_broadcast_filters",
    )
    filter_tags = models.ManyToManyField(
        "contacts.Tag",
        blank=True,
        related_name="one_time_broadcasts",
    )
    filter_city = models.CharField(max_length=100, blank=True)
    filter_state = models.CharField(max_length=50, blank=True)
    filter_zip_code = models.CharField(max_length=20, blank=True)
    filter_inactive_days = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.DRAFT)
    recipient_count = models.PositiveIntegerField(default=0)
    sent_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    launched_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    scheduled_for = models.DateTimeField(null=True, blank=True)
    approval_required = models.BooleanField(default=False)
    approval_status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.NOT_REQUIRED,
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="one_time_broadcasts_approved",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="one_time_broadcasts_created",
    )

    class Meta:
        ordering = ["-created_at"]
        unique_together = [("organization", "name")]

    def __str__(self):
        return self.name


class AudienceSegment(OrgScopedModel):
    name = models.CharField(max_length=180)
    contact_type = models.CharField(max_length=20, blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audience_segments",
    )
    tags = models.ManyToManyField(
        "contacts.Tag",
        blank=True,
        related_name="audience_segments",
    )
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=50, blank=True)
    zip_code = models.CharField(max_length=20, blank=True)
    inactive_days = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        unique_together = [("organization", "name")]

    def __str__(self):
        return self.name


class OneTimeBroadcastDelivery(OrgScopedModel):
    class Status(models.TextChoices):
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    broadcast = models.ForeignKey(
        OneTimeBroadcast,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    contact = models.ForeignKey(
        "contacts.Contact",
        on_delete=models.CASCADE,
        related_name="one_time_broadcast_deliveries",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SENT)
    detail = models.TextField(blank=True)
    provider_message_id = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = [("broadcast", "contact")]

    def __str__(self):
        return f"{self.broadcast.name}: {self.contact.full_name} ({self.status})"
