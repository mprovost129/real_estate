from django.conf import settings
from django.db import models
from django.utils.text import slugify


class Organization(models.Model):
    class OrgType(models.TextChoices):
        INDIVIDUAL = "individual", "Individual Agent"
        TEAM = "team", "Real Estate Team"
        BROKERAGE = "brokerage", "Brokerage"

    class Plan(models.TextChoices):
        FREE = "free", "Free"
        STARTER = "starter", "Starter"
        TEAM = "team", "Team"
        BROKERAGE = "brokerage", "Brokerage"

    # Identity
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    org_type = models.CharField(max_length=20, choices=OrgType.choices, default=OrgType.INDIVIDUAL)
    plan = models.CharField(max_length=20, choices=Plan.choices, default=Plan.FREE)

    # Contact & branding
    logo = models.ImageField(upload_to="org_logos/", blank=True, null=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    website = models.URLField(blank=True)

    # Address
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=50, blank=True)
    zip_code = models.CharField(max_length=20, blank=True)

    # Ownership & status
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_organizations",
    )
    is_active = models.BooleanField(default=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "organization"
        verbose_name_plural = "organizations"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            n = 1
            while Organization.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)


class Membership(models.Model):
    """Links a User to an Organization with a permission level."""

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"
        VIEWER = "viewer", "Viewer"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(auto_now_add=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invitations_sent",
    )

    class Meta:
        verbose_name = "membership"
        verbose_name_plural = "memberships"
        unique_together = [("user", "organization")]
        ordering = ["organization", "role", "user"]

    def __str__(self):
        return f"{self.user} — {self.organization} ({self.get_role_display()})"
