from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils.text import slugify
from django.utils import timezone


class UserManager(BaseUserManager):
    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if not extra_fields["is_staff"]:
            raise ValueError("Superuser must have is_staff=True.")
        if not extra_fields["is_superuser"]:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        INDIVIDUAL_AGENT = "individual_agent", "Individual Agent"
        BUYER_AGENT = "buyer_agent", "Buyer Agent"
        LISTING_AGENT = "listing_agent", "Listing Agent"
        TEAM_LEADER = "team_leader", "Team Leader"
        ISA = "isa", "Inside Sales Agent"
        TRANSACTION_COORDINATOR = "transaction_coordinator", "Transaction Coordinator"
        ADMIN = "admin", "Admin / Assistant"
        BROKER = "broker", "Broker / Manager"
        BROKERAGE_ADMIN = "brokerage_admin", "Brokerage Admin"

    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=30, choices=Role.choices, default=Role.INDIVIDUAL_AGENT)
    phone = models.CharField(max_length=20, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return self.full_name or self.email

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()


class AgentPublicProfile(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="agent_public_profiles",
    )
    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="public_profiles",
    )
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    is_published = models.BooleanField(default=False)

    page_title = models.CharField(max_length=180, blank=True)
    agent_display_name = models.CharField(max_length=180, blank=True)
    agent_headline = models.CharField(max_length=180, blank=True)
    agent_bio = models.TextField(blank=True)
    agent_photo = models.ImageField(upload_to="public_profiles/agent_photos/", blank=True, null=True)

    broker_name = models.CharField(max_length=180, blank=True)
    broker_logo = models.ImageField(upload_to="public_profiles/broker_logos/", blank=True, null=True)

    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    office_address = models.CharField(max_length=255, blank=True)
    website_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    facebook_url = models.URLField(blank=True)
    linkedin_url = models.URLField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["organization", "user"]
        unique_together = [("organization", "user")]

    def __str__(self):
        return f"{self.user.full_name or self.user.email} ({self.organization.name})"

    def save(self, *args, **kwargs):
        if not self.slug:
            base_name = self.agent_display_name or self.user.full_name or self.user.email.split("@")[0]
            base_slug = slugify(base_name)[:150] or f"agent-{self.user_id}"
            slug = base_slug
            n = 1
            while AgentPublicProfile.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def public_name(self):
        return self.agent_display_name or self.user.full_name or self.user.email


class PublicListingCard(models.Model):
    class ListingStatus(models.TextChoices):
        ACTIVE = "active", "Active"
        PENDING = "pending", "Pending"
        COMING_SOON = "coming_soon", "Coming Soon"
        CLOSED = "closed", "Closed"
        OFF_MARKET = "off_market", "Off Market"

    profile = models.ForeignKey(
        AgentPublicProfile,
        on_delete=models.CASCADE,
        related_name="listing_cards",
    )
    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="public_listing_cards",
    )
    mls_id = models.CharField(max_length=80)
    status = models.CharField(max_length=20, choices=ListingStatus.choices, default=ListingStatus.ACTIVE)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)

    title = models.CharField(max_length=255, blank=True)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=50, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    beds = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    baths = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    sqft = models.PositiveIntegerField(null=True, blank=True)
    photo_url = models.URLField(blank=True)
    details_url = models.URLField(blank=True)
    short_description = models.TextField(blank=True)

    last_synced_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_featured", "-created_at"]
        unique_together = [("profile", "mls_id")]
        indexes = [
            models.Index(fields=["profile", "is_active"]),
            models.Index(fields=["profile", "status"]),
        ]

    def __str__(self):
        return f"{self.mls_id} - {self.address or self.title or 'Listing'}"
