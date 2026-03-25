from django import forms

from contacts.models import Contact

from .models import DripCampaign, DripCampaignStep, MessageTemplate


class DripCampaignForm(forms.ModelForm):
    enroll_contact_type = forms.ChoiceField(
        required=False,
        choices=[("", "Any Contact Type")] + list(Contact.ContactType.choices),
        widget=forms.Select(attrs={"class": "input"}),
    )

    class Meta:
        model = DripCampaign
        fields = ["name", "channel", "category", "enroll_contact_type", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input"}),
            "channel": forms.Select(attrs={"class": "input"}),
            "category": forms.Select(attrs={"class": "input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class DripCampaignStepForm(forms.ModelForm):
    class Meta:
        model = DripCampaignStep
        fields = ["order", "delay_days", "template", "is_active"]
        widgets = {
            "order": forms.NumberInput(attrs={"class": "input", "min": 1}),
            "delay_days": forms.NumberInput(attrs={"class": "input", "min": 0}),
            "template": forms.Select(attrs={"class": "input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, campaign=None, org=None, **kwargs):
        super().__init__(*args, **kwargs)
        if org is not None:
            self.fields["template"].queryset = MessageTemplate.objects.for_org(org).filter(
                is_active=True,
                template_type=campaign.channel if campaign else MessageTemplate.TemplateType.EMAIL,
            ).order_by("category", "name")
