from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import AgentPublicProfile, PublicListingCard, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["email"]
    list_display = ["email", "first_name", "last_name", "role", "is_active", "is_staff", "date_joined"]
    list_filter = ["role", "is_active", "is_staff"]
    search_fields = ["email", "first_name", "last_name", "phone"]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name", "phone", "avatar")}),
        (_("Role"), {"fields": ("role",)}),
        (_("Permissions"), {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "first_name", "last_name", "role", "password1", "password2"),
        }),
    )

    # email is the USERNAME_FIELD - no username column
    filter_horizontal = ("groups", "user_permissions")


@admin.register(AgentPublicProfile)
class AgentPublicProfileAdmin(admin.ModelAdmin):
    list_display = ["slug", "user", "organization", "is_published", "updated_at"]
    list_filter = ["is_published", "organization"]
    search_fields = ["slug", "agent_display_name", "user__email", "organization__name", "broker_name"]


@admin.register(PublicListingCard)
class PublicListingCardAdmin(admin.ModelAdmin):
    list_display = ["mls_id", "profile", "status", "is_active", "is_featured", "updated_at"]
    list_filter = ["status", "is_active", "is_featured"]
    search_fields = ["mls_id", "address", "city", "state", "profile__slug", "profile__user__email"]
