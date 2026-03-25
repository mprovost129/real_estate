from django.contrib import admin

from .models import Membership, Organization


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    fields = ["user", "role", "is_active", "date_joined", "invited_by"]
    readonly_fields = ["date_joined"]
    autocomplete_fields = ["user"]


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ["name", "org_type", "plan", "owner", "is_active", "created_at"]
    list_filter = ["org_type", "plan", "is_active"]
    search_fields = ["name", "email", "phone", "owner__email"]
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ["owner"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [MembershipInline]

    fieldsets = (
        (None, {"fields": ("name", "slug", "org_type", "plan", "owner", "is_active")}),
        ("Contact & Branding", {"fields": ("logo", "email", "phone", "website")}),
        ("Address", {"fields": ("address", "city", "state", "zip_code")}),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "organization", "role", "is_active", "date_joined"]
    list_filter = ["role", "is_active", "organization"]
    search_fields = ["user__email", "user__first_name", "user__last_name", "organization__name"]
    autocomplete_fields = ["user", "organization"]
    readonly_fields = ["date_joined"]
