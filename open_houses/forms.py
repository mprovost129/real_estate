from django import forms

from .models import OpenHouse, OpenHouseVisitor


class OpenHouseForm(forms.ModelForm):
    date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date", "class": "input"}),
    )
    start_time = forms.TimeField(
        widget=forms.TimeInput(attrs={"type": "time", "class": "input"}),
    )
    end_time = forms.TimeField(
        widget=forms.TimeInput(attrs={"type": "time", "class": "input"}),
    )

    class Meta:
        model = OpenHouse
        fields = [
            "title", "event_type", "status",
            "date", "start_time", "end_time",
            "listing", "address", "city", "state", "zip_code",
            "host",
            "sign_in_message", "notes",
        ]
        widgets = {
            "title":           forms.TextInput(attrs={"class": "input"}),
            "event_type":      forms.Select(attrs={"class": "input"}),
            "status":          forms.Select(attrs={"class": "input"}),
            "listing":         forms.Select(attrs={"class": "input"}),
            "address":         forms.TextInput(attrs={"class": "input"}),
            "city":            forms.TextInput(attrs={"class": "input"}),
            "state":           forms.TextInput(attrs={"class": "input"}),
            "zip_code":        forms.TextInput(attrs={"class": "input"}),
            "host":            forms.Select(attrs={"class": "input"}),
            "sign_in_message": forms.Textarea(attrs={"class": "input", "rows": 2}),
            "notes":           forms.Textarea(attrs={"class": "input", "rows": 3}),
        }

    def __init__(self, org, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from properties.models import Property
        from users.models import User

        self.fields["listing"].queryset = (
            Property.objects.for_org(org).filter(is_active=True).order_by("address")
        )
        self.fields["listing"].required = False

        members = User.objects.filter(
            memberships__organization=org, memberships__is_active=True
        ).distinct()
        self.fields["host"].queryset = members
        self.fields["host"].required = False


class VisitorSignInForm(forms.ModelForm):
    """Used on the public sign-in page (no auth required)."""

    class Meta:
        model = OpenHouseVisitor
        fields = [
            "first_name", "last_name", "email", "phone",
            "visitor_type", "is_pre_approved", "pre_approval_amount",
            "represented_by_agent", "agent_name", "notes",
        ]
        widgets = {
            "first_name":           forms.TextInput(attrs={"class": "input", "placeholder": "First name"}),
            "last_name":            forms.TextInput(attrs={"class": "input", "placeholder": "Last name"}),
            "email":                forms.EmailInput(attrs={"class": "input", "placeholder": "Email address"}),
            "phone":                forms.TextInput(attrs={"class": "input", "placeholder": "Phone number"}),
            "visitor_type":         forms.Select(attrs={"class": "input"}),
            "pre_approval_amount":  forms.NumberInput(attrs={"class": "input", "step": "1000"}),
            "agent_name":           forms.TextInput(attrs={"class": "input", "placeholder": "Agent's name"}),
            "notes":                forms.Textarea(attrs={"class": "input", "rows": 2,
                                                          "placeholder": "Anything you'd like us to know?"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["last_name"].required          = False
        self.fields["email"].required              = False
        self.fields["phone"].required              = False
        self.fields["pre_approval_amount"].required = False
        self.fields["agent_name"].required         = False
        self.fields["notes"].required              = False
