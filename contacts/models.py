from django.conf import settings
from django.db import models

from organizations.mixins import OrgScopedModel


class Tag(OrgScopedModel):
    """Org-scoped labels applied to contacts."""

    name = models.CharField(max_length=50)
    color = models.CharField(max_length=7, default="#6366f1")  # hex color

    class Meta:
        unique_together = [("organization", "name")]
        ordering = ["name"]

    def __str__(self):
        return self.name


class Contact(OrgScopedModel):

    class ContactType(models.TextChoices):
        LEAD = "lead", "Lead"
        PROSPECT = "prospect", "Prospect"
        ACTIVE_BUYER = "active_buyer", "Active Buyer"
        ACTIVE_SELLER = "active_seller", "Active Seller"
        UNDER_CONTRACT = "under_contract", "Under Contract"
        PAST_CLIENT = "past_client", "Past Client"
        SPHERE = "sphere", "Sphere of Influence"
        REFERRAL_PARTNER = "referral_partner", "Referral Partner"
        VENDOR = "vendor", "Vendor"
        INVESTOR = "investor", "Investor"
        RENTER = "renter", "Renter"
        LANDLORD = "landlord", "Landlord"
        OTHER = "other", "Other"

    class Source(models.TextChoices):
        WEBSITE = "website", "Website"
        ZILLOW = "zillow", "Zillow"
        REALTOR_COM = "realtor_com", "Realtor.com"
        FACEBOOK = "facebook", "Facebook / Instagram"
        GOOGLE = "google", "Google Ads"
        OPEN_HOUSE = "open_house", "Open House"
        REFERRAL = "referral", "Referral"
        SPHERE = "sphere", "Sphere / Manual Entry"
        SIGN_CALL = "sign_call", "Sign Call"
        COLD_CALL = "cold_call", "Cold Call"
        TEXT_INQUIRY = "text_inquiry", "Text Inquiry"
        EVENT = "event", "Event"
        QR_CODE = "qr_code", "QR Code"
        IMPORT = "import", "CSV Import"
        OTHER = "other", "Other"

    class BuyerSellerType(models.TextChoices):
        BUYER = "buyer", "Buyer"
        SELLER = "seller", "Seller"
        BOTH = "both", "Buyer & Seller"
        INVESTOR = "investor", "Investor"
        RENTER = "renter", "Renter"

    class FinancingStatus(models.TextChoices):
        UNKNOWN = "unknown", "Unknown"
        NOT_STARTED = "not_started", "Not Started"
        IN_PROGRESS = "in_progress", "In Progress"
        PRE_APPROVED = "pre_approved", "Pre-Approved"
        CASH = "cash", "Cash"

    class TimelineUrgency(models.TextChoices):
        IMMEDIATE = "immediate", "Immediate (0–3 months)"
        SHORT = "short", "Short-Term (3–6 months)"
        MEDIUM = "medium", "Medium-Term (6–12 months)"
        LONG = "long", "Long-Term (12+ months)"
        UNKNOWN = "unknown", "Unknown"

    class MotivationLevel(models.IntegerChoices):
        ONE = 1, "1 – Just browsing"
        TWO = 2, "2"
        THREE = 3, "3"
        FOUR = 4, "4"
        FIVE = 5, "5 – Moderately motivated"
        SIX = 6, "6"
        SEVEN = 7, "7"
        EIGHT = 8, "8"
        NINE = 9, "9"
        TEN = 10, "10 – Must move now"

    # ------------------------------------------------------------------ #
    # Identity
    # ------------------------------------------------------------------ #
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150, blank=True)
    preferred_name = models.CharField(max_length=150, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    home_anniversary = models.DateField(null=True, blank=True)

    # ------------------------------------------------------------------ #
    # Primary contact info (denormalized for fast access)
    # Full lists live in ContactEmail / ContactPhone
    # ------------------------------------------------------------------ #
    primary_email = models.EmailField(blank=True)
    primary_phone = models.CharField(max_length=20, blank=True)

    # ------------------------------------------------------------------ #
    # Address
    # ------------------------------------------------------------------ #
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=50, blank=True)
    zip_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, default="US")

    # ------------------------------------------------------------------ #
    # Communication preferences
    # ------------------------------------------------------------------ #
    timezone = models.CharField(max_length=50, default="America/New_York")
    language_preference = models.CharField(max_length=10, default="en")
    preferred_contact_method = models.CharField(
        max_length=10,
        choices=[("email", "Email"), ("phone", "Phone"), ("text", "Text"), ("any", "Any")],
        default="any",
    )
    do_not_contact = models.BooleanField(default=False)
    opted_out_email = models.BooleanField(default=False)
    opted_out_sms = models.BooleanField(default=False)

    # ------------------------------------------------------------------ #
    # CRM classification
    # ------------------------------------------------------------------ #
    contact_type = models.CharField(max_length=20, choices=ContactType.choices, default=ContactType.LEAD)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.OTHER)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_contacts",
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name="contacts")

    # ------------------------------------------------------------------ #
    # Personal / household details
    # ------------------------------------------------------------------ #
    employer = models.CharField(max_length=200, blank=True)
    profession = models.CharField(max_length=200, blank=True)
    spouse_partner = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="spouse_of",
    )
    children_info = models.TextField(blank=True)
    interests_hobbies = models.TextField(blank=True)

    # ------------------------------------------------------------------ #
    # Social profiles
    # ------------------------------------------------------------------ #
    social_linkedin = models.URLField(blank=True)
    social_facebook = models.URLField(blank=True)
    social_instagram = models.CharField(max_length=100, blank=True)

    # ------------------------------------------------------------------ #
    # Real-estate specific
    # ------------------------------------------------------------------ #
    buyer_seller_type = models.CharField(
        max_length=10, choices=BuyerSellerType.choices, blank=True
    )
    is_first_time_buyer = models.BooleanField(null=True, blank=True)
    financing_status = models.CharField(
        max_length=20, choices=FinancingStatus.choices, default=FinancingStatus.UNKNOWN
    )
    lender_name = models.CharField(max_length=200, blank=True)
    lender_contact = models.CharField(max_length=200, blank=True)
    pre_approval_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    price_min = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    price_max = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    desired_bedrooms_min = models.PositiveSmallIntegerField(null=True, blank=True)
    desired_bathrooms_min = models.DecimalField(
        max_digits=3, decimal_places=1, null=True, blank=True
    )
    desired_sqft_min = models.PositiveIntegerField(null=True, blank=True)
    desired_sqft_max = models.PositiveIntegerField(null=True, blank=True)
    preferred_areas = models.TextField(blank=True, help_text="Neighborhoods, towns, zip codes")
    must_haves = models.TextField(blank=True)
    deal_breakers = models.TextField(blank=True)
    target_move_date = models.DateField(null=True, blank=True)
    current_home_situation = models.TextField(blank=True)
    timeline_urgency = models.CharField(
        max_length=10, choices=TimelineUrgency.choices, default=TimelineUrgency.UNKNOWN
    )
    motivation_level = models.PositiveSmallIntegerField(
        choices=MotivationLevel.choices, null=True, blank=True
    )

    # ------------------------------------------------------------------ #
    # Referral tracking
    # ------------------------------------------------------------------ #
    referred_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="referrals_made",
    )

    # ------------------------------------------------------------------ #
    # Internal notes (quick field; full history via ContactNote)
    # ------------------------------------------------------------------ #
    notes = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def display_name(self):
        return self.preferred_name or self.full_name


class ContactEmail(models.Model):
    class Label(models.TextChoices):
        HOME = "home", "Home"
        WORK = "work", "Work"
        OTHER = "other", "Other"

    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="emails")
    email = models.EmailField()
    label = models.CharField(max_length=10, choices=Label.choices, default=Label.HOME)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_primary", "label"]

    def __str__(self):
        return f"{self.email} ({self.label})"


class ContactPhone(models.Model):
    class Label(models.TextChoices):
        MOBILE = "mobile", "Mobile"
        HOME = "home", "Home"
        WORK = "work", "Work"
        OTHER = "other", "Other"

    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="phones")
    phone = models.CharField(max_length=20)
    label = models.CharField(max_length=10, choices=Label.choices, default=Label.MOBILE)
    is_primary = models.BooleanField(default=False)
    can_text = models.BooleanField(default=True)
    can_call = models.BooleanField(default=True)

    class Meta:
        ordering = ["-is_primary", "label"]

    def __str__(self):
        return f"{self.phone} ({self.label})"


class ContactNote(OrgScopedModel):
    """Timestamped notes tied to a contact, forming the activity timeline."""

    class NoteType(models.TextChoices):
        GENERAL    = "general",    "General Note"
        CALL       = "call",       "Call"
        TEXT       = "text",       "Text"
        EMAIL      = "email",      "Email"
        MEETING    = "meeting",    "Meeting"
        SHOWING    = "showing",    "Showing"
        OPEN_HOUSE = "open_house", "Open House"
        TASK       = "task",       "Task"
        SYSTEM     = "system",     "System Event"

    class CallDirection(models.TextChoices):
        OUTBOUND = "outbound", "Outbound"
        INBOUND  = "inbound",  "Inbound"

    class CallOutcome(models.TextChoices):
        ANSWERED     = "answered",     "Answered"
        VOICEMAIL    = "voicemail",    "Left Voicemail"
        NO_ANSWER    = "no_answer",    "No Answer"
        BUSY         = "busy",         "Busy"
        LEFT_MESSAGE = "left_message", "Left Message"
        WRONG_NUMBER = "wrong_number", "Wrong Number"

    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="contact_notes")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contact_notes",
    )
    note_type = models.CharField(max_length=20, choices=NoteType.choices, default=NoteType.GENERAL)
    body      = models.TextField(blank=True)
    is_pinned = models.BooleanField(default=False)

    # Call-specific fields
    call_direction       = models.CharField(max_length=10, choices=CallDirection.choices, blank=True)
    call_outcome         = models.CharField(max_length=15, choices=CallOutcome.choices, blank=True)
    call_duration_minutes = models.PositiveSmallIntegerField(null=True, blank=True)

    # Email-specific fields
    email_subject = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_note_type_display()} – {self.contact} ({self.created_at:%Y-%m-%d})"

class ContactDocument(OrgScopedModel):
    class Category(models.TextChoices):
        IDENTITY = "identity", "Identity"
        PREAPPROVAL = "preapproval", "Pre-Approval"
        AGREEMENT = "agreement", "Agreement"
        DISCLOSURE = "disclosure", "Disclosure"
        FINANCIAL = "financial", "Financial"
        COMPLIANCE = "compliance", "Compliance"
        OTHER = "other", "Other"

    contact = models.ForeignKey(
        Contact,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.OTHER,
    )
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to="contacts/documents/%Y/%m/")
    notes = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_contact_documents",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
