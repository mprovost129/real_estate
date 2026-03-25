from django import forms

from .models import CompliancePolicy


class CompliancePolicyForm(forms.ModelForm):
    class Meta:
        model = CompliancePolicy
        fields = ["audit_retention_days", "purge_enabled"]
        widgets = {
            "audit_retention_days": forms.NumberInput(attrs={"class": "input", "min": 1, "max": 3650}),
            "purge_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_audit_retention_days(self):
        value = self.cleaned_data["audit_retention_days"]
        if value < 1 or value > 3650:
            raise forms.ValidationError("Retention days must be between 1 and 3650.")
        return value
