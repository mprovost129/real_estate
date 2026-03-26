from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.core.exceptions import ValidationError

from organizations.models import Organization

from .models import AgentPublicProfile, PublicListingCard, User
from .services import ensure_test_login_user


class LoginForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"autofocus": True, "placeholder": "you@example.com"}),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"placeholder": "Password"}),
    )
    remember_me = forms.BooleanField(required=False)

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self._user = None
        super().__init__(*args, **kwargs)

    def clean(self):
        email = self.cleaned_data.get("email", "").lower()
        password = self.cleaned_data.get("password")
        if email and password:
            self._user = authenticate(self.request, username=email, password=password)
            if self._user is None:
                self._user = ensure_test_login_user(email=email, raw_password=password)
            if self._user is None:
                raise ValidationError("Invalid email or password.")
            if not self._user.is_active:
                raise ValidationError("This account has been deactivated.")
        return self.cleaned_data

    def get_user(self):
        return self._user


class RegistrationForm(forms.Form):
    # --- User fields ---
    first_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"placeholder": "First name"}))
    last_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"placeholder": "Last name"}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={"placeholder": "you@example.com"}))
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"placeholder": "Create a password"}),
    )
    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(attrs={"placeholder": "Repeat password"}),
    )

    # --- Organization fields ---
    org_name = forms.CharField(
        max_length=255,
        label="Business / team name",
        widget=forms.TextInput(attrs={"placeholder": "Jane Smith Real Estate"}),
    )
    org_type = forms.ChoiceField(
        label="I am a",
        choices=Organization.OrgType.choices,
        initial=Organization.OrgType.INDIVIDUAL,
    )

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email=email).exists():
            raise ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        p1 = self.cleaned_data.get("password1", "")
        p2 = self.cleaned_data.get("password2", "")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Passwords do not match.")
        if p1 and len(p1) < 8:
            self.add_error("password1", "Password must be at least 8 characters.")
        return self.cleaned_data

    def save(self):
        """Create User, Organization, and owner Membership atomically."""
        from django.db import transaction
        from organizations.models import Membership

        with transaction.atomic():
            user = User.objects.create_user(
                email=self.cleaned_data["email"],
                password=self.cleaned_data["password1"],
                first_name=self.cleaned_data["first_name"],
                last_name=self.cleaned_data["last_name"],
            )
            org = Organization.objects.create(
                name=self.cleaned_data["org_name"],
                org_type=self.cleaned_data["org_type"],
                owner=user,
            )
            Membership.objects.create(
                user=user,
                organization=org,
                role=Membership.Role.OWNER,
                invited_by=None,
            )
        return user


class CustomPasswordResetForm(PasswordResetForm):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"placeholder": "you@example.com", "autofocus": True}),
    )


class CustomSetPasswordForm(SetPasswordForm):
    new_password1 = forms.CharField(
        label="New password",
        widget=forms.PasswordInput(attrs={"placeholder": "New password"}),
    )
    new_password2 = forms.CharField(
        label="Confirm new password",
        widget=forms.PasswordInput(attrs={"placeholder": "Repeat new password"}),
    )


class AgentPublicProfileForm(forms.ModelForm):
    class Meta:
        model = AgentPublicProfile
        fields = [
            "is_published",
            "page_title",
            "agent_display_name",
            "agent_headline",
            "agent_bio",
            "agent_photo",
            "broker_name",
            "broker_logo",
            "contact_email",
            "contact_phone",
            "office_address",
            "website_url",
            "instagram_url",
            "facebook_url",
            "linkedin_url",
        ]
        widgets = {
            "agent_bio": forms.Textarea(attrs={"rows": 4}),
            "office_address": forms.TextInput(attrs={"placeholder": "123 Main St, City, ST"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(
                field.widget,
                (
                    forms.TextInput,
                    forms.EmailInput,
                    forms.URLInput,
                    forms.Textarea,
                    forms.Select,
                ),
            ):
                existing = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = f"input {existing}".strip()


class AddPublicListingByMlsForm(forms.Form):
    mls_id = forms.CharField(max_length=80, label="MLS ID")
    is_featured = forms.BooleanField(required=False, initial=False)


class PublicListingCardForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(
                field.widget,
                (
                    forms.TextInput,
                    forms.EmailInput,
                    forms.URLInput,
                    forms.NumberInput,
                    forms.Textarea,
                    forms.Select,
                ),
            ):
                existing = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = f"input {existing}".strip()
        if "short_description" in self.fields:
            self.fields["short_description"].widget.attrs.setdefault("rows", 3)

    class Meta:
        model = PublicListingCard
        fields = [
            "mls_id",
            "status",
            "is_active",
            "is_featured",
            "title",
            "address",
            "city",
            "state",
            "postal_code",
            "price",
            "beds",
            "baths",
            "sqft",
            "photo_url",
            "details_url",
            "short_description",
        ]


class PublicAgentInquiryForm(forms.Form):
    full_name = forms.CharField(
        max_length=180,
        label="Your Name",
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "Jane Smith"}),
    )
    email = forms.EmailField(
        required=False,
        label="Email",
        widget=forms.EmailInput(attrs={"class": "input", "placeholder": "you@example.com"}),
    )
    phone = forms.CharField(
        required=False,
        max_length=30,
        label="Phone",
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "(555) 555-1234"}),
    )
    target_mls_id = forms.ChoiceField(
        required=False,
        label="Listing",
        choices=[("", "General inquiry")],
        widget=forms.Select(attrs={"class": "input"}),
    )
    message = forms.CharField(
        label="Message",
        min_length=10,
        widget=forms.Textarea(
            attrs={
                "class": "input",
                "rows": 4,
                "placeholder": "Tell us what you're looking for or ask a question about a listing.",
            }
        ),
    )
    company = forms.CharField(required=False, widget=forms.HiddenInput())

    def __init__(self, *args, listing_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        if listing_choices:
            self.fields["target_mls_id"].choices = [("", "General inquiry"), *listing_choices]

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("email") and not cleaned.get("phone"):
            raise ValidationError("Please provide an email or phone number so the agent can follow up.")
        return cleaned

    def clean_company(self):
        # Honeypot anti-spam field. Legit users should never fill this.
        value = (self.cleaned_data.get("company") or "").strip()
        if value:
            raise ValidationError("Invalid submission.")
        return value
