from django.contrib import admin

from .models import Contact, ContactDocument, ContactEmail, ContactNote, ContactPhone, Tag


class ContactEmailInline(admin.TabularInline):
    model = ContactEmail
    extra = 1
    fields = ["email", "label", "is_primary"]


class ContactPhoneInline(admin.TabularInline):
    model = ContactPhone
    extra = 1
    fields = ["phone", "label", "is_primary", "can_text", "can_call"]


class ContactNoteInline(admin.StackedInline):
    model = ContactNote
    extra = 0
    fields = ["note_type", "author", "body", "is_pinned"]
    readonly_fields = ["created_at"]
    ordering = ["-created_at"]


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = [
        "full_name", "primary_email", "primary_phone",
        "contact_type", "source", "assigned_to", "organization", "is_active",
    ]
    list_filter = [
        "contact_type", "source", "buyer_seller_type",
        "financing_status", "timeline_urgency", "is_active", "organization",
    ]
    search_fields = [
        "first_name", "last_name", "preferred_name",
        "primary_email", "primary_phone", "employer",
    ]
    autocomplete_fields = ["organization", "assigned_to", "spouse_partner", "referred_by"]
    filter_horizontal = ["tags"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [ContactEmailInline, ContactPhoneInline, ContactNoteInline]

    fieldsets = (
        ("Identity", {
            "fields": (
                ("first_name", "last_name", "preferred_name"),
                ("date_of_birth", "home_anniversary"),
            ),
        }),
        ("Primary Contact", {
            "fields": (("primary_email", "primary_phone"),),
        }),
        ("Address", {
            "fields": ("address", ("city", "state", "zip_code"), "country"),
        }),
        ("Communication Preferences", {
            "fields": (
                ("timezone", "language_preference", "preferred_contact_method"),
                ("do_not_contact", "opted_out_email", "opted_out_sms"),
            ),
            "classes": ("collapse",),
        }),
        ("CRM", {
            "fields": (
                ("contact_type", "source"),
                ("organization", "assigned_to"),
                "tags",
            ),
        }),
        ("Personal & Household", {
            "fields": (
                ("employer", "profession"),
                "spouse_partner",
                "children_info",
                "interests_hobbies",
            ),
            "classes": ("collapse",),
        }),
        ("Social Profiles", {
            "fields": ("social_linkedin", "social_facebook", "social_instagram"),
            "classes": ("collapse",),
        }),
        ("Real Estate Details", {
            "fields": (
                ("buyer_seller_type", "is_first_time_buyer"),
                ("financing_status", "lender_name", "lender_contact"),
                "pre_approval_amount",
                ("price_min", "price_max"),
                ("desired_bedrooms_min", "desired_bathrooms_min"),
                ("desired_sqft_min", "desired_sqft_max"),
                "preferred_areas",
                "must_haves",
                "deal_breakers",
                ("target_move_date", "timeline_urgency", "motivation_level"),
                "current_home_situation",
            ),
            "classes": ("collapse",),
        }),
        ("Referral", {
            "fields": ("referred_by",),
            "classes": ("collapse",),
        }),
        ("Notes", {
            "fields": ("notes",),
        }),
        ("Metadata", {
            "fields": ("is_active", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ["name", "color", "organization"]
    search_fields = ["name"]
    list_filter = ["organization"]


@admin.register(ContactNote)
class ContactNoteAdmin(admin.ModelAdmin):
    list_display = ["contact", "note_type", "author", "is_pinned", "created_at"]
    list_filter = ["note_type", "is_pinned"]
    search_fields = ["contact__first_name", "contact__last_name", "body"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(ContactDocument)
class ContactDocumentAdmin(admin.ModelAdmin):
    list_display = ["title", "contact", "category", "uploaded_by", "created_at"]
    list_filter = ["category", "organization"]
    search_fields = ["title", "contact__first_name", "contact__last_name"]
