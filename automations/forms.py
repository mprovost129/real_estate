from django import forms

from .models import AutomationRule
from .validation import validate_actions, validate_conditions


class AutomationRuleForm(forms.ModelForm):
    class Meta:
        model = AutomationRule
        fields = [
            "name",
            "trigger_type",
            "is_active",
            "conditions",
            "actions",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input"}),
            "trigger_type": forms.Select(attrs={"class": "input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "conditions": forms.Textarea(attrs={"class": "input", "rows": 5}),
            "actions": forms.Textarea(attrs={"class": "input", "rows": 8}),
        }
        help_texts = {
            "conditions": "JSON object. Supports leaf keys plus all/any/not groups.",
            "actions": "JSON array. Example: [{\"type\": \"create_task\", \"title\": \"Call lead\", \"due_in_days\": 0}]",
        }

    def clean_conditions(self):
        value = self.cleaned_data.get("conditions")
        if value is None:
            value = {}
        validate_conditions(value)
        return value

    def clean_actions(self):
        value = self.cleaned_data.get("actions")
        if value is None:
            value = []
        return value

    def clean(self):
        cleaned = super().clean()
        actions = cleaned.get("actions", [])
        trigger_type = cleaned.get("trigger_type")
        if "actions" not in self.errors:
            try:
                validate_actions(actions, trigger_type=trigger_type)
            except forms.ValidationError as exc:
                self.add_error("actions", exc)
        return cleaned


class AutomationTestForm(forms.Form):
    trigger_type = forms.ChoiceField(
        choices=AutomationRule.TriggerType.choices,
        widget=forms.Select(attrs={"class": "input"}),
    )
    source = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "website, open_house, task_overdue, ..."}),
        help_text="Optional source string used by conditions like source_in.",
    )
    contact_id = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "input", "placeholder": "Contact ID"}),
    )
    deal_id = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "input", "placeholder": "Deal ID"}),
    )
    task_id = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "input", "placeholder": "Task ID"}),
    )
    to_stage_id = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "input", "placeholder": "To Stage ID"}),
    )
