from django import forms
from django.utils import timezone

from contacts.models import Contact, Tag

from .models import AudienceSegment, DripCampaign, DripCampaignStep, MessageTemplate, OneTimeBroadcast


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


class OneTimeBroadcastForm(forms.ModelForm):
    confirm_consent = forms.BooleanField(
        required=True,
        label="I confirm recipients have consented to receive this communication.",
    )

    class Meta:
        model = OneTimeBroadcast
        fields = [
            "name",
            "channel",
            "template",
            "filter_segment",
            "filter_contact_type",
            "filter_assigned_to",
            "filter_tags",
            "filter_city",
            "filter_state",
            "filter_zip_code",
            "filter_inactive_days",
            "scheduled_for",
            "approval_required",
            "confirm_consent",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input"}),
            "channel": forms.Select(attrs={"class": "input"}),
            "template": forms.Select(attrs={"class": "input"}),
            "filter_segment": forms.Select(attrs={"class": "input"}),
            "filter_contact_type": forms.Select(attrs={"class": "input"}),
            "filter_assigned_to": forms.Select(attrs={"class": "input"}),
            "filter_tags": forms.SelectMultiple(attrs={"class": "input"}),
            "filter_city": forms.TextInput(attrs={"class": "input", "placeholder": "City"}),
            "filter_state": forms.TextInput(attrs={"class": "input", "placeholder": "State"}),
            "filter_zip_code": forms.TextInput(attrs={"class": "input", "placeholder": "ZIP"}),
            "filter_inactive_days": forms.NumberInput(attrs={"class": "input", "min": 1}),
            "scheduled_for": forms.DateTimeInput(attrs={"class": "input", "type": "datetime-local"}),
            "approval_required": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
    save_as_segment = forms.BooleanField(required=False, label="Save this audience as a reusable segment")
    segment_name = forms.CharField(required=False, max_length=180, widget=forms.TextInput(attrs={"class": "input"}))

    def __init__(self, *args, org=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.org = org
        self.fields["filter_segment"].required = False
        self.fields["filter_contact_type"].required = False
        self.fields["filter_tags"].required = False
        self.fields["filter_city"].required = False
        self.fields["filter_state"].required = False
        self.fields["filter_zip_code"].required = False
        self.fields["filter_inactive_days"].required = False
        self.fields["filter_contact_type"].choices = [("", "Any Contact Type")] + list(Contact.ContactType.choices)
        self.fields["filter_assigned_to"].required = False
        if org is not None:
            from django.contrib.auth import get_user_model

            User = get_user_model()
            self.fields["filter_segment"].queryset = AudienceSegment.objects.for_org(org).filter(is_active=True).order_by(
                "name"
            )
            self.fields["template"].queryset = MessageTemplate.objects.for_org(org).filter(is_active=True).order_by(
                "template_type", "category", "name"
            )
            self.fields["filter_tags"].queryset = Tag.objects.filter(organization=org).order_by("name")
            self.fields["filter_assigned_to"].queryset = (
                User.objects.filter(
                    memberships__organization=org,
                    memberships__is_active=True,
                )
                .distinct()
                .order_by("first_name", "last_name", "email")
            )

    def clean(self):
        cleaned = super().clean()
        template = cleaned.get("template")
        channel = cleaned.get("channel")
        scheduled_for = cleaned.get("scheduled_for")
        save_as_segment = cleaned.get("save_as_segment")
        segment_name = (cleaned.get("segment_name") or "").strip()
        if template and channel and template.template_type != channel:
            raise forms.ValidationError("Template type must match the selected channel.")
        if scheduled_for and timezone.is_naive(scheduled_for):
            cleaned["scheduled_for"] = timezone.make_aware(scheduled_for, timezone.get_current_timezone())
        if save_as_segment and not segment_name:
            raise forms.ValidationError("Provide a segment name when saving this audience as a segment.")
        return cleaned
