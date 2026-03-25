from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
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
