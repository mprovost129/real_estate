from django import forms

from contacts.models import Contact
from .models import Deal, Pipeline, PipelineStage


class DealForm(forms.ModelForm):
    def __init__(self, *args, org=None, **kwargs):
        super().__init__(*args, **kwargs)
        if org:
            self.fields["contact"].queryset = (
                Contact.objects.filter(organization=org, is_active=True)
                .order_by("last_name", "first_name")
            )
            self.fields["pipeline"].queryset = Pipeline.objects.filter(
                organization=org, is_active=True
            )
            self.fields["stage"].queryset = PipelineStage.objects.filter(
                pipeline__organization=org, is_active=True
            )
            from django.contrib.auth import get_user_model
            User = get_user_model()
            self.fields["assigned_to"].queryset = User.objects.filter(
                memberships__organization=org, memberships__is_active=True
            ).distinct()
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, (
                forms.TextInput, forms.EmailInput, forms.URLInput,
                forms.NumberInput, forms.DateInput, forms.Select, forms.Textarea,
            )):
                existing = widget.attrs.get("class", "")
                widget.attrs["class"] = f"input {existing}".strip()
            if isinstance(widget, forms.DateInput):
                widget.attrs["type"] = "date"

    class Meta:
        model = Deal
        fields = [
            "title", "contact", "pipeline", "stage", "assigned_to",
            "value", "expected_close_date", "notes",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


class DealMoveForm(forms.Form):
    stage = forms.ModelChoiceField(queryset=PipelineStage.objects.none())
    note = forms.CharField(required=False, widget=forms.TextInput(
        attrs={"placeholder": "Optional note about this move…", "class": "input"}
    ))

    def __init__(self, *args, pipeline=None, **kwargs):
        super().__init__(*args, **kwargs)
        if pipeline:
            self.fields["stage"].queryset = pipeline.stages.filter(is_active=True).order_by("order")
