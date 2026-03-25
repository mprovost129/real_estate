from django import forms

from .models import Membership, Organization


class OrganizationSettingsForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = [
            "name", "org_type",
            "email", "phone", "website",
            "address", "city", "state", "zip_code",
            "logo",
        ]
        widgets = {
            "name":     forms.TextInput(attrs={"class": "input"}),
            "org_type": forms.Select(attrs={"class": "input"}),
            "email":    forms.EmailInput(attrs={"class": "input"}),
            "phone":    forms.TextInput(attrs={"class": "input"}),
            "website":  forms.URLInput(attrs={"class": "input"}),
            "address":  forms.TextInput(attrs={"class": "input"}),
            "city":     forms.TextInput(attrs={"class": "input"}),
            "state":    forms.TextInput(attrs={"class": "input"}),
            "zip_code": forms.TextInput(attrs={"class": "input"}),
        }


class InviteMemberForm(forms.Form):
    first_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "First name"}),
    )
    last_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "Last name"}),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"class": "input", "placeholder": "email@example.com"}),
    )
    role = forms.ChoiceField(
        choices=Membership.Role.choices,
        initial=Membership.Role.MEMBER,
        widget=forms.Select(attrs={"class": "input"}),
    )


class UserProfileForm(forms.Form):
    first_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": "input"}),
    )
    last_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": "input"}),
    )
    phone = forms.CharField(
        required=False,
        max_length=20,
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "e.g. (555) 555-5555"}),
    )
    role = forms.ChoiceField(
        widget=forms.Select(attrs={"class": "input"}),
    )

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from users.models import User
        self.fields["role"].choices = User.Role.choices
        # Seed initial values
        if not args and not kwargs.get("data"):
            self.fields["first_name"].initial = user.first_name
            self.fields["last_name"].initial  = user.last_name
            self.fields["phone"].initial      = user.phone
            self.fields["role"].initial       = user.role
