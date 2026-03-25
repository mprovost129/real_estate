from django import forms

from .models import Contact, ContactDocument, ContactEmail, ContactNote, ContactPhone, Tag


class TagForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = ["name", "color"]
        widgets = {
            "name":  forms.TextInput(attrs={"class": "input", "placeholder": "Tag name", "maxlength": 50}),
            "color": forms.TextInput(attrs={"type": "color", "class": "input", "style": "width:3rem;padding:.2rem;cursor:pointer;"}),
        }


class ContactForm(forms.ModelForm):
    def __init__(self, *args, org=None, **kwargs):
        super().__init__(*args, **kwargs)
        if org:
            self.fields["tags"].queryset = Tag.objects.filter(organization=org)
            from django.conf import settings
            from django.contrib.auth import get_user_model
            User = get_user_model()
            self.fields["assigned_to"].queryset = User.objects.filter(
                memberships__organization=org,
                memberships__is_active=True,
            ).distinct()
        # Add Bootstrap/theme classes to all inputs
        for name, field in self.fields.items():
            if isinstance(field.widget, (forms.TextInput, forms.EmailInput,
                                         forms.URLInput, forms.NumberInput,
                                         forms.DateInput, forms.TimeInput,
                                         forms.Textarea, forms.Select)):
                existing = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = f"input {existing}".strip()
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs.setdefault("rows", 3)
            if isinstance(field.widget, forms.DateInput):
                field.widget.attrs["type"] = "date"

    class Meta:
        model = Contact
        exclude = ["organization", "created_at", "updated_at"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
            "must_haves": forms.Textarea(attrs={"rows": 2}),
            "deal_breakers": forms.Textarea(attrs={"rows": 2}),
            "current_home_situation": forms.Textarea(attrs={"rows": 2}),
            "children_info": forms.Textarea(attrs={"rows": 2}),
            "interests_hobbies": forms.Textarea(attrs={"rows": 2}),
            "preferred_areas": forms.Textarea(attrs={"rows": 2}),
        }


class LogCallForm(forms.ModelForm):
    body = forms.CharField(
        required=False,
        label="Notes",
        widget=forms.Textarea(attrs={"rows": 3, "class": "input", "placeholder": "Call notes…"}),
    )

    class Meta:
        model = ContactNote
        fields = ["call_direction", "call_outcome", "call_duration_minutes", "body"]
        widgets = {
            "call_direction":        forms.Select(attrs={"class": "input"}),
            "call_outcome":          forms.Select(attrs={"class": "input"}),
            "call_duration_minutes": forms.NumberInput(attrs={"class": "input", "min": 0, "placeholder": "mins"}),
        }


class LogEmailForm(forms.ModelForm):
    body = forms.CharField(
        label="Body",
        widget=forms.Textarea(attrs={"rows": 6, "class": "input", "placeholder": "Email body…"}),
    )

    class Meta:
        model = ContactNote
        fields = ["email_subject", "body"]
        widgets = {
            "email_subject": forms.TextInput(attrs={"class": "input", "placeholder": "Subject line"}),
        }


class LogTextForm(forms.ModelForm):
    body = forms.CharField(
        label="Message",
        widget=forms.Textarea(attrs={"rows": 4, "class": "input", "placeholder": "Text message…"}),
    )

    class Meta:
        model = ContactNote
        fields = ["body"]


class LogNoteForm(forms.ModelForm):
    body = forms.CharField(
        required=False,
        label="",
        widget=forms.Textarea(attrs={
            "rows": 3, "class": "input",
            "placeholder": "Add a note, record a meeting outcome…",
        }),
    )

    class Meta:
        model = ContactNote
        fields = ["note_type", "body", "is_pinned"]
        widgets = {
            "note_type": forms.Select(
                choices=[
                    ("general", "General Note"),
                    ("meeting", "Meeting"),
                    ("showing", "Showing"),
                ],
                attrs={"class": "input"},
            ),
            "is_pinned": forms.CheckboxInput(),
        }


class ContactNoteForm(forms.ModelForm):
    """Legacy simple form — kept for backwards compat."""
    body = forms.CharField(
        widget=forms.Textarea(attrs={
            "rows": 3,
            "placeholder": "Add a note, log a call, record an outcome…",
            "class": "input",
        }),
        label="",
    )

    class Meta:
        model = ContactNote
        fields = ["note_type", "body", "is_pinned"]
        widgets = {
            "note_type": forms.Select(attrs={"class": "input"}),
        }


class ContactDocumentForm(forms.ModelForm):
    class Meta:
        model = ContactDocument
        fields = ["category", "title", "file", "notes"]
        widgets = {
            "category": forms.Select(attrs={"class": "input"}),
            "title": forms.TextInput(attrs={"class": "input", "placeholder": "Document title"}),
            "file": forms.ClearableFileInput(attrs={"class": "input"}),
            "notes": forms.Textarea(attrs={"class": "input", "rows": 2, "placeholder": "Optional notes"}),
        }
