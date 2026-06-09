from django import forms

from .models import (
    ClinicYakapSettings,
    PatientYakapProfile,
    ServiceYakapRule,
    YakapCoverageCategory,
    YakapLedgerEntry,
)

_INPUT = "cf-input"
_SELECT = "cf-select"
_TEXTAREA = "cf-textarea"
_CHECKBOX = "cf-checkbox"


class ClinicYakapSettingsForm(forms.ModelForm):
    class Meta:
        model = ClinicYakapSettings
        fields = [
            "is_enabled",
            "public_promo_headline",
            "public_promo_body",
            "public_disclaimer",
            "internal_disclaimer",
            "verification_instructions",
            "default_annual_credit",
            "reset_month",
            "reset_day",
            "hard_block_exceeded",
        ]
        widgets = {
            "is_enabled": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "public_promo_headline": forms.TextInput(attrs={"class": _INPUT}),
            "public_promo_body": forms.Textarea(attrs={"class": _TEXTAREA, "rows": 3}),
            "public_disclaimer": forms.Textarea(attrs={"class": _TEXTAREA, "rows": 3}),
            "internal_disclaimer": forms.Textarea(attrs={"class": _TEXTAREA, "rows": 3}),
            "verification_instructions": forms.Textarea(attrs={"class": _TEXTAREA, "rows": 3}),
            "default_annual_credit": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0"}),
            "reset_month": forms.NumberInput(attrs={"class": _INPUT, "step": "1", "min": "1", "max": "12"}),
            "reset_day": forms.NumberInput(attrs={"class": _INPUT, "step": "1", "min": "1", "max": "31"}),
            "hard_block_exceeded": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
        }


class YakapCoverageCategoryForm(forms.ModelForm):
    def __init__(self, *args, clinic=None, **kwargs):
        self.clinic = clinic
        super().__init__(*args, **kwargs)

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if self.clinic and self.clinic.yakap_categories.filter(name=name).exists():
            raise forms.ValidationError("A YAKAP category with this name already exists for this clinic.")
        return name

    class Meta:
        model = YakapCoverageCategory
        fields = [
            "name",
            "category_type",
            "annual_limit",
            "is_active",
            "notes",
            "sort_order",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": _INPUT}),
            "category_type": forms.Select(attrs={"class": _SELECT}),
            "annual_limit": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0"}),
            "is_active": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "notes": forms.Textarea(attrs={"class": _TEXTAREA, "rows": 3}),
            "sort_order": forms.NumberInput(attrs={"class": _INPUT, "step": "1", "min": "0"}),
        }


class ServiceYakapRuleForm(forms.ModelForm):
    def add_prefix(self, field_name):
        if self.prefix:
            return f"{self.prefix}_{field_name}"
        return field_name

    def __init__(self, clinic, *args, **kwargs):
        self.clinic = clinic
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = clinic.yakap_categories.filter(is_active=True)
        self.fields["category"].required = False

    class Meta:
        model = ServiceYakapRule
        fields = [
            "category",
            "coverage_status",
            "estimated_covered_amount",
            "requires_verification",
            "public_badge_label",
            "staff_notes",
        ]
        widgets = {
            "category": forms.Select(attrs={"class": _SELECT}),
            "coverage_status": forms.Select(attrs={"class": _SELECT}),
            "estimated_covered_amount": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0"}),
            "requires_verification": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "public_badge_label": forms.TextInput(attrs={"class": _INPUT}),
            "staff_notes": forms.Textarea(attrs={"class": _TEXTAREA, "rows": 3}),
        }


class YakapLedgerEntryForm(forms.ModelForm):
    def __init__(self, clinic, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = clinic.yakap_categories.filter(is_active=True)

    class Meta:
        model = YakapLedgerEntry
        fields = [
            "category",
            "entry_type",
            "amount",
            "verification_status",
            "note",
        ]
        widgets = {
            "category": forms.Select(attrs={"class": _SELECT}),
            "entry_type": forms.Select(attrs={"class": _SELECT}),
            "amount": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0.01"}),
            "verification_status": forms.Select(attrs={"class": _SELECT}),
            "note": forms.Textarea(attrs={"class": _TEXTAREA, "rows": 2}),
        }
