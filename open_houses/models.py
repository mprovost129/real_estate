import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from organizations.mixins import OrgScopedModel


class OpenHouse(OrgScopedModel):

    class Status(models.TextChoices):
        SCHEDULED  = "scheduled",  "Scheduled"
        ACTIVE     = "active",     "Active"
        COMPLETED  = "completed",  "Completed"
        CANCELLED  = "cancelled",  "Cancelled"

    class OpenHouseType(models.TextChoices):
        PUBLIC       = "public",       "Public Open House"
        BROKER_ONLY  = "broker_only",  "Broker Open"
        PRIVATE      = "private",      "Private Showing"
        VIRTUAL      = "virtual",      "Virtual Open House"

    # ------------------------------------------------------------------ #
    # Event details
    # ------------------------------------------------------------------ #
    title     = models.CharField(max_length=255, blank=True,
                                 help_text="Optional title; defaults to the address.")
    event_type = models.CharField(
        max_length=20, choices=OpenHouseType.choices, default=OpenHouseType.PUBLIC
    )
    status = models.CharField(
        max_length=15, choices=Status.choices, default=Status.SCHEDULED
    )
    date       = models.DateField()
    start_time = models.TimeField()
    end_time   = models.TimeField()

    # ------------------------------------------------------------------ #
    # Property link (optional — can also type address manually)
    # ------------------------------------------------------------------ #
    listing = models.ForeignKey(
        "properties.Property",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="open_houses",
    )
    # Fallback address if no property FK
    address  = models.CharField(max_length=255, blank=True)
    city     = models.CharField(max_length=100, blank=True)
    state    = models.CharField(max_length=50, blank=True)
    zip_code = models.CharField(max_length=10, blank=True)

    # ------------------------------------------------------------------ #
    # Host / team
    # ------------------------------------------------------------------ #
    host = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="hosted_open_houses",
    )

    # ------------------------------------------------------------------ #
    # Sign-in / marketing
    # ------------------------------------------------------------------ #
    # Unique token used in the public sign-in URL (QR code)
    public_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    sign_in_message = models.TextField(
        blank=True,
        help_text="Optional welcome message shown on the public sign-in page.",
    )

    # ------------------------------------------------------------------ #
    # Notes & follow-up
    # ------------------------------------------------------------------ #
    notes           = models.TextField(blank=True)
    followup_sent   = models.BooleanField(default=False)

    class Meta:
        ordering = ["-date", "-start_time"]

    def __str__(self):
        return self.display_title

    @property
    def display_title(self):
        if self.title:
            return self.title
        if self.listing:
            return self.listing.short_address
        return self.address or "Open House"

    @property
    def display_address(self):
        if self.listing:
            return self.listing.full_address
        parts = [self.address, self.city, self.state, self.zip_code]
        return ", ".join(p for p in parts if p)

    @property
    def is_past(self):
        return self.date < timezone.localdate()

    @property
    def visitor_count(self):
        return self.visitors.count()


class OpenHouseVisitor(models.Model):
    """A person who signed in at an open house."""

    class VisitorType(models.TextChoices):
        BUYER    = "buyer",    "Buyer"
        NEIGHBOR = "neighbor", "Neighbor"
        AGENT    = "agent",    "Agent / Realtor"
        INVESTOR = "investor", "Investor"
        RENTER   = "renter",   "Renter"
        OTHER    = "other",    "Other"

    open_house   = models.ForeignKey(OpenHouse, on_delete=models.CASCADE, related_name="visitors")

    # Identity
    first_name = models.CharField(max_length=100)
    last_name  = models.CharField(max_length=100, blank=True)
    email      = models.EmailField(blank=True)
    phone      = models.CharField(max_length=30, blank=True)

    # Visitor details
    visitor_type  = models.CharField(
        max_length=15, choices=VisitorType.choices, default=VisitorType.BUYER
    )
    is_pre_approved    = models.BooleanField(default=False)
    pre_approval_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    represented_by_agent = models.BooleanField(
        default=False,
        help_text="Is this buyer already working with an agent?",
    )
    agent_name = models.CharField(max_length=200, blank=True)
    notes      = models.TextField(blank=True)

    # CRM link — set when visitor is converted to a Contact
    contact = models.ForeignKey(
        "contacts.Contact",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="open_house_visits",
    )

    # Tracking
    signed_in_at = models.DateTimeField(auto_now_add=True)
    followed_up  = models.BooleanField(default=False)
    followed_up_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["signed_in_at"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}".strip() or self.email

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or "—"
