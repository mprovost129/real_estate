import uuid

from django.conf import settings
from django.db import models

from organizations.mixins import OrgScopedModel


class LeadCaptureForm(OrgScopedModel):
    """A public-facing form that creates Contact records on submission."""

    class FormType(models.TextChoices):
        BUYER       = "buyer",      "Buyer Inquiry"
        SELLER      = "seller",     "Seller / Home Valuation"
        GENERAL     = "general",    "General Contact"
        OPEN_HOUSE  = "open_house", "Open House Sign-in"
        VALUATION   = "valuation",  "Home Valuation Request"
        INVESTMENT  = "investment", "Investor Inquiry"

    class ContactSource(models.TextChoices):
        WEBSITE  = "website",  "Website"
        FACEBOOK = "facebook", "Facebook / Instagram"
        GOOGLE   = "google",   "Google Ads"
        OTHER    = "other",    "Other"

    slug            = models.SlugField(unique=True, default=uuid.uuid4, editable=False)
    name            = models.CharField(max_length=200, help_text="Internal name for this form")
    form_type       = models.CharField(max_length=20, choices=FormType.choices, default=FormType.GENERAL)
    contact_source  = models.CharField(
        max_length=20, choices=ContactSource.choices, default=ContactSource.WEBSITE,
        help_text="Source tag applied to contacts created by this form",
    )

    # Display content
    headline        = models.CharField(max_length=200, default="Get in touch")
    subheadline     = models.TextField(blank=True, help_text="Optional intro text shown above the form")
    button_text     = models.CharField(max_length=80, default="Submit")
    thank_you_title = models.CharField(max_length=200, default="Thank you!")
    thank_you_body  = models.TextField(
        default="We received your info and will be in touch shortly.",
    )
    redirect_url    = models.URLField(
        blank=True,
        help_text="If set, redirect here after submission instead of showing the thank-you message.",
    )

    # Which optional fields to show
    show_phone      = models.BooleanField(default=True)
    show_message    = models.BooleanField(default=True)
    show_address    = models.BooleanField(default=False,  help_text="Property address of interest")
    show_budget     = models.BooleanField(default=False)
    show_timeline   = models.BooleanField(default=False)
    require_phone   = models.BooleanField(default=False)
    require_message = models.BooleanField(default=False)

    # Routing
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="lead_forms",
        help_text="New contacts from this form are assigned to this user",
    )

    is_active   = models.BooleanField(default=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def public_url(self, request=None):
        from django.urls import reverse
        path = reverse("lead_forms:public_form", kwargs={"slug": self.slug})
        if request:
            return request.build_absolute_uri(path)
        return path


class LeadFormSubmission(models.Model):
    """Records each submission of a LeadCaptureForm."""

    form        = models.ForeignKey(LeadCaptureForm, on_delete=models.CASCADE, related_name="submissions")
    contact     = models.ForeignKey(
        "contacts.Contact",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="lead_submissions",
    )

    # Raw submitted data
    first_name  = models.CharField(max_length=100, blank=True)
    last_name   = models.CharField(max_length=100, blank=True)
    email       = models.EmailField(blank=True)
    phone       = models.CharField(max_length=30, blank=True)
    message     = models.TextField(blank=True)
    address     = models.CharField(max_length=255, blank=True)
    budget      = models.CharField(max_length=100, blank=True)
    timeline    = models.CharField(max_length=100, blank=True)

    ip_address  = models.GenericIPAddressField(null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    converted   = models.BooleanField(
        default=False,
        help_text="True when a Contact record was successfully created",
    )

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.first_name} {self.last_name} via {self.form.name}"
