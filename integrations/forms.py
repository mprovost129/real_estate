from django import forms

from .models import IntegrationConnection


class IntegrationConnectionForm(forms.ModelForm):
    class Meta:
        model = IntegrationConnection
        fields = [
            "integration_type",
            "provider",
            "display_name",
            "external_account_id",
            "is_active",
        ]
        widgets = {
            "integration_type": forms.Select(attrs={"class": "input"}),
            "provider": forms.Select(attrs={"class": "input"}),
            "display_name": forms.TextInput(attrs={"class": "input", "placeholder": "Connection label"}),
            "external_account_id": forms.TextInput(attrs={"class": "input", "placeholder": "External account ID (optional)"}),
            "is_active": forms.CheckboxInput(),
        }
