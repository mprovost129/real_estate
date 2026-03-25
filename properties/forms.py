from django import forms

from .models import Property, PropertyNote


class PropertyForm(forms.ModelForm):

    list_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "input"}),
    )
    expiration_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "input"}),
    )
    sold_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "input"}),
    )

    class Meta:
        model = Property
        fields = [
            # Address
            "address", "unit", "city", "state", "zip_code",
            "county", "neighborhood", "school_district",
            # Identity
            "mls_number", "property_type", "status",
            # Pricing
            "list_price", "original_list_price", "sold_price",
            "tax_assessed_value", "annual_taxes", "hoa_fee",
            # Physical
            "bedrooms", "bathrooms_full", "bathrooms_half",
            "square_feet", "lot_size_sqft", "garage_spaces",
            "year_built", "stories",
            # Dates
            "list_date", "expiration_date", "sold_date",
            # People
            "owner_contact", "listing_agent",
            # Showing
            "lockbox_type", "lockbox_code", "showing_instructions",
            # Description
            "description", "notes",
        ]
        widgets = {
            "address":             forms.TextInput(attrs={"class": "input"}),
            "unit":                forms.TextInput(attrs={"class": "input"}),
            "city":                forms.TextInput(attrs={"class": "input"}),
            "state":               forms.TextInput(attrs={"class": "input"}),
            "zip_code":            forms.TextInput(attrs={"class": "input"}),
            "county":              forms.TextInput(attrs={"class": "input"}),
            "neighborhood":        forms.TextInput(attrs={"class": "input"}),
            "school_district":     forms.TextInput(attrs={"class": "input"}),
            "mls_number":          forms.TextInput(attrs={"class": "input"}),
            "property_type":       forms.Select(attrs={"class": "input"}),
            "status":              forms.Select(attrs={"class": "input"}),
            "list_price":          forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
            "original_list_price": forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
            "sold_price":          forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
            "tax_assessed_value":  forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
            "annual_taxes":        forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
            "hoa_fee":             forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
            "bedrooms":            forms.NumberInput(attrs={"class": "input"}),
            "bathrooms_full":      forms.NumberInput(attrs={"class": "input"}),
            "bathrooms_half":      forms.NumberInput(attrs={"class": "input"}),
            "square_feet":         forms.NumberInput(attrs={"class": "input"}),
            "lot_size_sqft":       forms.NumberInput(attrs={"class": "input"}),
            "garage_spaces":       forms.NumberInput(attrs={"class": "input"}),
            "year_built":          forms.NumberInput(attrs={"class": "input"}),
            "stories":             forms.NumberInput(attrs={"class": "input"}),
            "owner_contact":       forms.Select(attrs={"class": "input"}),
            "listing_agent":       forms.Select(attrs={"class": "input"}),
            "lockbox_type":        forms.Select(attrs={"class": "input"}),
            "lockbox_code":        forms.TextInput(attrs={"class": "input"}),
            "showing_instructions": forms.Textarea(attrs={"class": "input", "rows": 3}),
            "description":         forms.Textarea(attrs={"class": "input", "rows": 4}),
            "notes":               forms.Textarea(attrs={"class": "input", "rows": 3}),
        }

    def __init__(self, org, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from contacts.models import Contact
        from users.models import User

        self.fields["owner_contact"].queryset = (
            Contact.objects.for_org(org).filter(is_active=True).order_by("last_name", "first_name")
        )
        self.fields["owner_contact"].required = False

        members = User.objects.filter(
            memberships__organization=org, memberships__is_active=True
        ).distinct()
        self.fields["listing_agent"].queryset = members
        self.fields["listing_agent"].required = False


class PropertyNoteForm(forms.ModelForm):
    class Meta:
        model = PropertyNote
        fields = ["body"]
        widgets = {
            "body": forms.Textarea(attrs={
                "class": "input",
                "rows": 3,
                "placeholder": "Add a note about this property…",
            })
        }
