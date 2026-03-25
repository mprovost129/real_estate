from django import forms
from django.utils import timezone

from .models import Task


class TaskForm(forms.ModelForm):
    due_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date", "class": "input"}),
    )
    due_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={"type": "time", "class": "input"}),
    )
    recurrence_end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "input"}),
    )
    snooze_until = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={"type": "datetime-local", "class": "input"}),
    )

    class Meta:
        model = Task
        fields = [
            "title",
            "task_type",
            "priority",
            "status",
            "description",
            "assigned_to",
            "contact",
            "deal",
            "due_date",
            "due_time",
            "recurrence",
            "recurrence_end_date",
            "outcome",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "input"}),
            "task_type": forms.Select(attrs={"class": "input"}),
            "priority": forms.Select(attrs={"class": "input"}),
            "status": forms.Select(attrs={"class": "input"}),
            "description": forms.Textarea(attrs={"class": "input", "rows": 3}),
            "assigned_to": forms.Select(attrs={"class": "input"}),
            "contact": forms.Select(attrs={"class": "input"}),
            "deal": forms.Select(attrs={"class": "input"}),
            "recurrence": forms.Select(attrs={"class": "input"}),
            "outcome": forms.Textarea(attrs={"class": "input", "rows": 2}),
        }

    def __init__(self, org, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from contacts.models import Contact
        from pipelines.models import Deal
        from users.models import User

        members = User.objects.filter(
            memberships__organization=org, memberships__is_active=True
        ).distinct()
        self.fields["assigned_to"].queryset = members
        self.fields["assigned_to"].required = False

        self.fields["contact"].queryset = (
            Contact.objects.for_org(org).filter(is_active=True).order_by("last_name", "first_name")
        )
        self.fields["contact"].required = False

        self.fields["deal"].queryset = (
            Deal.objects.for_org(org).select_related("contact", "pipeline")
        )
        self.fields["deal"].required = False

        # hide outcome on create (only meaningful after completion)
        if not self.instance.pk:
            self.fields["outcome"].widget = forms.HiddenInput()
            self.fields["status"].widget = forms.HiddenInput()
            self.fields["status"].initial = Task.Status.PENDING


class TaskCompleteForm(forms.Form):
    outcome = forms.CharField(
        required=False,
        label="Outcome / notes",
        widget=forms.Textarea(attrs={"class": "input", "rows": 3,
                                     "placeholder": "What happened? (optional)"}),
    )


class TaskSnoozeForm(forms.Form):
    SNOOZE_CHOICES = [
        ("1h",  "1 hour"),
        ("3h",  "3 hours"),
        ("1d",  "Tomorrow"),
        ("3d",  "3 days"),
        ("1w",  "1 week"),
    ]
    snooze_for = forms.ChoiceField(
        choices=SNOOZE_CHOICES,
        widget=forms.Select(attrs={"class": "input"}),
        label="Snooze for",
    )
