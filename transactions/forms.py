from django import forms

from .models import Transaction, TransactionChecklistItem, TransactionDocument, TransactionNote


def _date_widget():
    return forms.DateInput(attrs={"type": "date", "class": "input"})


class TransactionForm(forms.ModelForm):
    contract_date = forms.DateField(required=False, widget=_date_widget())
    earnest_money_due = forms.DateField(required=False, widget=_date_widget())
    inspection_deadline = forms.DateField(required=False, widget=_date_widget())
    inspection_objection_deadline = forms.DateField(required=False, widget=_date_widget())
    inspection_resolution_deadline = forms.DateField(required=False, widget=_date_widget())
    appraisal_deadline = forms.DateField(required=False, widget=_date_widget())
    financing_deadline = forms.DateField(required=False, widget=_date_widget())
    title_deadline = forms.DateField(required=False, widget=_date_widget())
    closing_date = forms.DateField(required=False, widget=_date_widget())
    possession_date = forms.DateField(required=False, widget=_date_widget())
    closed_at = forms.DateField(required=False, widget=_date_widget())

    class Meta:
        model = Transaction
        fields = [
            "transaction_type", "status", "financing_type", "mls_number",
            "deal", "buyer_contact", "seller_contact", "linked_property", "property_address",
            "listing_agent", "buyers_agent", "transaction_coordinator",
            "purchase_price", "earnest_money", "earnest_money_due", "earnest_received",
            "down_payment", "loan_amount", "commission_pct", "commission_amount", "referral_fee",
            "lender_name", "lender_contact", "lender_email", "lender_phone",
            "title_company", "title_officer", "title_email", "title_phone",
            "closing_attorney", "closing_email",
            "contract_date", "inspection_deadline", "inspection_objection_deadline",
            "inspection_resolution_deadline", "appraisal_deadline", "financing_deadline",
            "title_deadline", "closing_date", "possession_date",
            "inspection_completed", "appraisal_completed", "financing_approved",
            "title_clear", "final_walkthrough_done", "closed_at",
            "notes",
        ]
        widgets = {
            "transaction_type": forms.Select(attrs={"class": "input"}),
            "status": forms.Select(attrs={"class": "input"}),
            "financing_type": forms.Select(attrs={"class": "input"}),
            "mls_number": forms.TextInput(attrs={"class": "input"}),
            "deal": forms.Select(attrs={"class": "input"}),
            "buyer_contact": forms.Select(attrs={"class": "input"}),
            "seller_contact": forms.Select(attrs={"class": "input"}),
            "linked_property": forms.Select(attrs={"class": "input"}),
            "property_address": forms.TextInput(attrs={"class": "input"}),
            "listing_agent": forms.Select(attrs={"class": "input"}),
            "buyers_agent": forms.Select(attrs={"class": "input"}),
            "transaction_coordinator": forms.Select(attrs={"class": "input"}),
            "purchase_price": forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
            "earnest_money": forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
            "down_payment": forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
            "loan_amount": forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
            "commission_pct": forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
            "commission_amount": forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
            "referral_fee": forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
            "lender_name": forms.TextInput(attrs={"class": "input"}),
            "lender_contact": forms.TextInput(attrs={"class": "input"}),
            "lender_email": forms.EmailInput(attrs={"class": "input"}),
            "lender_phone": forms.TextInput(attrs={"class": "input"}),
            "title_company": forms.TextInput(attrs={"class": "input"}),
            "title_officer": forms.TextInput(attrs={"class": "input"}),
            "title_email": forms.EmailInput(attrs={"class": "input"}),
            "title_phone": forms.TextInput(attrs={"class": "input"}),
            "closing_attorney": forms.TextInput(attrs={"class": "input"}),
            "closing_email": forms.EmailInput(attrs={"class": "input"}),
            "notes": forms.Textarea(attrs={"class": "input", "rows": 3}),
        }

    def __init__(self, org, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from contacts.models import Contact
        from pipelines.models import Deal
        from properties.models import Property
        from users.models import User

        contacts = Contact.objects.for_org(org).filter(is_active=True).order_by("last_name", "first_name")
        self.fields["buyer_contact"].queryset = contacts
        self.fields["seller_contact"].queryset = contacts
        self.fields["buyer_contact"].required = False
        self.fields["seller_contact"].required = False

        self.fields["linked_property"].queryset = (
            Property.objects.for_org(org).filter(is_active=True).order_by("address")
        )
        self.fields["linked_property"].required = False

        self.fields["deal"].queryset = Deal.objects.for_org(org).order_by("-created_at")
        self.fields["deal"].required = False

        members = User.objects.filter(
            memberships__organization=org, memberships__is_active=True
        ).distinct()
        for field_name in ("listing_agent", "buyers_agent", "transaction_coordinator"):
            self.fields[field_name].queryset = members
            self.fields[field_name].required = False


class ChecklistItemUpdateForm(forms.ModelForm):
    due_date = forms.DateField(required=False, widget=_date_widget())

    class Meta:
        model = TransactionChecklistItem
        fields = ["status", "due_date", "assigned_to", "notes"]
        widgets = {
            "status": forms.Select(attrs={"class": "input"}),
            "assigned_to": forms.Select(attrs={"class": "input"}),
            "notes": forms.Textarea(attrs={"class": "input", "rows": 2}),
        }

    def __init__(self, org, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from users.models import User

        members = User.objects.filter(
            memberships__organization=org, memberships__is_active=True
        ).distinct()
        self.fields["assigned_to"].queryset = members
        self.fields["assigned_to"].required = False


class TransactionNoteForm(forms.ModelForm):
    class Meta:
        model = TransactionNote
        fields = ["body"]
        widgets = {
            "body": forms.Textarea(attrs={
                "class": "input",
                "rows": 2,
                "placeholder": "Add a note...",
            })
        }


class TransactionDocumentForm(forms.ModelForm):
    class Meta:
        model = TransactionDocument
        fields = ["category", "title", "file", "notes"]
        widgets = {
            "category": forms.Select(attrs={"class": "input"}),
            "title": forms.TextInput(attrs={"class": "input", "placeholder": "Document title"}),
            "file": forms.ClearableFileInput(attrs={"class": "input"}),
            "notes": forms.Textarea(attrs={"class": "input", "rows": 2, "placeholder": "Optional notes"}),
        }
