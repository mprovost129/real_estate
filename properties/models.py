from django.conf import settings
from django.db import models
from django.utils import timezone

from organizations.mixins import OrgScopedModel


class Property(OrgScopedModel):

    class PropertyType(models.TextChoices):
        SINGLE_FAMILY  = "single_family",  "Single Family"
        CONDO          = "condo",          "Condo / Co-op"
        TOWNHOUSE      = "townhouse",      "Townhouse"
        MULTI_FAMILY   = "multi_family",   "Multi-Family"
        LAND           = "land",           "Land / Lot"
        COMMERCIAL     = "commercial",     "Commercial"
        MOBILE_HOME    = "mobile_home",    "Mobile / Manufactured"
        NEW_CONSTRUCT  = "new_construct",  "New Construction"
        OTHER          = "other",          "Other"

    class Status(models.TextChoices):
        OFF_MARKET     = "off_market",     "Off Market"
        COMING_SOON    = "coming_soon",    "Coming Soon"
        ACTIVE         = "active",         "Active"
        PENDING        = "pending",        "Pending"
        UNDER_CONTRACT = "under_contract", "Under Contract"
        SOLD           = "sold",           "Sold"
        WITHDRAWN      = "withdrawn",      "Withdrawn"
        EXPIRED        = "expired",        "Expired"
        CANCELLED      = "cancelled",      "Cancelled"

    class LockboxType(models.TextChoices):
        NONE      = "none",      "None"
        COMBO     = "combo",     "Combo"
        SUPRA     = "supra",     "Supra"
        BLUETOOTH = "bluetooth", "Bluetooth"
        OTHER     = "other",     "Other"

    # ------------------------------------------------------------------ #
    # Address
    # ------------------------------------------------------------------ #
    address         = models.CharField(max_length=255)
    unit            = models.CharField(max_length=20, blank=True)
    city            = models.CharField(max_length=100)
    state           = models.CharField(max_length=50)
    zip_code        = models.CharField(max_length=10)
    county          = models.CharField(max_length=100, blank=True)
    neighborhood    = models.CharField(max_length=100, blank=True)
    school_district = models.CharField(max_length=100, blank=True)

    # ------------------------------------------------------------------ #
    # MLS & listing identity
    # ------------------------------------------------------------------ #
    mls_number    = models.CharField(max_length=50, blank=True)
    property_type = models.CharField(
        max_length=20, choices=PropertyType.choices, default=PropertyType.SINGLE_FAMILY
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OFF_MARKET
    )

    # ------------------------------------------------------------------ #
    # Pricing
    # ------------------------------------------------------------------ #
    list_price          = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    original_list_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    sold_price          = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    tax_assessed_value  = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    annual_taxes        = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    hoa_fee             = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text="Monthly HOA fee"
    )

    # ------------------------------------------------------------------ #
    # Physical characteristics
    # ------------------------------------------------------------------ #
    bedrooms       = models.SmallIntegerField(null=True, blank=True)
    bathrooms_full = models.SmallIntegerField(null=True, blank=True)
    bathrooms_half = models.SmallIntegerField(null=True, blank=True)
    square_feet    = models.PositiveIntegerField(null=True, blank=True)
    lot_size_sqft  = models.PositiveIntegerField(null=True, blank=True)
    garage_spaces  = models.SmallIntegerField(null=True, blank=True)
    year_built     = models.SmallIntegerField(null=True, blank=True)
    stories        = models.SmallIntegerField(null=True, blank=True)

    # ------------------------------------------------------------------ #
    # Listing dates
    # ------------------------------------------------------------------ #
    list_date       = models.DateField(null=True, blank=True)
    expiration_date = models.DateField(null=True, blank=True)
    sold_date       = models.DateField(null=True, blank=True)

    # ------------------------------------------------------------------ #
    # People
    # ------------------------------------------------------------------ #
    owner_contact = models.ForeignKey(
        "contacts.Contact",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="owned_properties",
        help_text="Contact record for the property owner/seller",
    )
    listing_agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="listings",
    )

    # ------------------------------------------------------------------ #
    # Showing & access
    # ------------------------------------------------------------------ #
    lockbox_type         = models.CharField(
        max_length=15, choices=LockboxType.choices, default=LockboxType.NONE
    )
    lockbox_code         = models.CharField(max_length=50, blank=True)
    showing_instructions = models.TextField(blank=True)

    # ------------------------------------------------------------------ #
    # Description & notes
    # ------------------------------------------------------------------ #
    description = models.TextField(blank=True)
    notes       = models.TextField(blank=True, help_text="Internal notes")
    is_active   = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "properties"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["organization", "status"]),
        ]

    def __str__(self):
        return self.full_address

    # ------------------------------------------------------------------ #
    # Computed helpers
    # ------------------------------------------------------------------ #
    @property
    def full_address(self):
        parts = [self.address]
        if self.unit:
            parts.append(f"#{self.unit}")
        parts.append(f"{self.city}, {self.state} {self.zip_code}")
        return " ".join(parts)

    @property
    def short_address(self):
        unit = f" #{self.unit}" if self.unit else ""
        return f"{self.address}{unit}"

    @property
    def beds_baths(self):
        b    = self.bedrooms or 0
        full = self.bathrooms_full or 0
        half = self.bathrooms_half or 0
        if half:
            return f"{b} bd / {full}.5 ba"
        return f"{b} bd / {full} ba"

    @property
    def days_on_market(self):
        if not self.list_date:
            return None
        end = self.sold_date or timezone.localdate()
        return (end - self.list_date).days

    @property
    def price_per_sqft(self):
        price = self.sold_price or self.list_price
        if price and self.square_feet:
            return round(float(price) / self.square_feet, 2)
        return None


class PropertyNote(models.Model):
    """Internal notes attached to a property."""

    property   = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="prop_notes")
    author     = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    body       = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Note on {self.property.short_address}"


class PropertyPhoto(models.Model):
    """Photos attached to a property listing."""

    property    = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="photos")
    image       = models.ImageField(upload_to="property_photos/")
    caption     = models.CharField(max_length=200, blank=True)
    order       = models.SmallIntegerField(default=0)
    is_primary  = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_primary", "order", "uploaded_at"]
