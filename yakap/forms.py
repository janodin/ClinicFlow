from django import forms
from django.db.models import Q

from .models import (
    AppointmentYakapSnapshot,
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
_MONTH_CHOICES = [
    (1, "January"),
    (2, "February"),
    (3, "March"),
    (4, "April"),
    (5, "May"),
    (6, "June"),
    (7, "July"),
    (8, "August"),
    (9, "September"),
    (10, "October"),
    (11, "November"),
    (12, "December"),
]


class ClinicYakapSettingsForm(forms.ModelForm):
    class Meta:
        model = ClinicYakapSettings
        fields = [
            "is_enabled",
            "low_balance_threshold_amount",
            "verification_stale_after_days",
            "reset_month",
            "reset_day",
            "hard_block_exceeded",
        ]
        widgets = {
            "is_enabled": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "low_balance_threshold_amount": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0"}),
            "verification_stale_after_days": forms.NumberInput(attrs={"class": _INPUT, "step": "1", "min": "0"}),
            "reset_month": forms.Select(choices=_MONTH_CHOICES, attrs={"class": _SELECT}),
            "reset_day": forms.NumberInput(attrs={"class": _INPUT, "step": "1", "min": "1", "max": "31"}),
            "hard_block_exceeded": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
        }
        labels = {
            "reset_day": "Reset date",
        }


class PatientYakapProfileForm(forms.ModelForm):
    class Meta:
        model = PatientYakapProfile
        fields = [
            "status",
            "registered_clinic_name",
            "verification_method",
            "verification_reference",
            "consent_note",
            "staff_notes",
        ]
        widgets = {
            "status": forms.Select(attrs={"class": _SELECT}),
            "registered_clinic_name": forms.TextInput(attrs={"class": _INPUT}),
            "verification_method": forms.TextInput(attrs={"class": _INPUT}),
            "verification_reference": forms.TextInput(attrs={"class": _INPUT}),
            "consent_note": forms.Textarea(attrs={"class": _TEXTAREA, "rows": 3}),
            "staff_notes": forms.Textarea(attrs={"class": _TEXTAREA, "rows": 3}),
        }


APPOINTMENT_YAKAP_STAFF_STATUS_CHOICES = [
    (AppointmentYakapSnapshot.STATUS_NEEDS_VERIFICATION, "Needs verification"),
    (AppointmentYakapSnapshot.STATUS_VERIFIED_FOR_VISIT, "Verified for this visit"),
    (AppointmentYakapSnapshot.STATUS_NOT_ELIGIBLE, "Not eligible for this visit"),
    (AppointmentYakapSnapshot.STATUS_CANCELLED, "Cancel YAKAP request"),
]
APPOINTMENT_YAKAP_STAFF_STATUS_VALUES = {value for value, _label in APPOINTMENT_YAKAP_STAFF_STATUS_CHOICES}
APPOINTMENT_YAKAP_EDITABLE_SOURCE_STATUS_VALUES = APPOINTMENT_YAKAP_STAFF_STATUS_VALUES | {
    AppointmentYakapSnapshot.STATUS_REQUESTED,
}


class AppointmentYakapStatusForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_coverage_status = self.instance.coverage_status if self.instance.pk else None
        self._preserve_original_coverage_status = (
            self._original_coverage_status
            and self._original_coverage_status not in APPOINTMENT_YAKAP_EDITABLE_SOURCE_STATUS_VALUES
        )
        choices = list(APPOINTMENT_YAKAP_STAFF_STATUS_CHOICES)
        if self._preserve_original_coverage_status:
            status_labels = dict(AppointmentYakapSnapshot.STATUS_CHOICES)
            choices.insert(
                0,
                (self._original_coverage_status, status_labels.get(self._original_coverage_status, self._original_coverage_status)),
            )
        self.fields["coverage_status"].choices = choices

    def clean_coverage_status(self):
        coverage_status = self.cleaned_data["coverage_status"]
        if self._preserve_original_coverage_status and coverage_status != self._original_coverage_status:
            raise forms.ValidationError("Current YAKAP status cannot be changed from this form.")
        return coverage_status

    class Meta:
        model = AppointmentYakapSnapshot
        fields = [
            "coverage_status",
            "verification_note",
        ]
        widgets = {
            "coverage_status": forms.Select(attrs={"class": _SELECT}),
            "verification_note": forms.Textarea(attrs={"class": _TEXTAREA, "rows": 3}),
        }


class YakapCoverageCategoryForm(forms.ModelForm):
    def __init__(self, *args, clinic=None, **kwargs):
        self.clinic = clinic
        super().__init__(*args, **kwargs)

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        duplicate_categories = (
            self.clinic.yakap_categories.filter(name__iexact=name)
            if self.clinic
            else YakapCoverageCategory.objects.none()
        )
        if self.instance.pk:
            duplicate_categories = duplicate_categories.exclude(pk=self.instance.pk)
        if duplicate_categories.exists():
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
    def __init__(
        self,
        clinic,
        *args,
        patient=None,
        appointment=None,
        category=None,
        allow_privileged_entries=False,
        allow_inactive_category=False,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        category_queryset = clinic.yakap_categories.filter(is_active=True)
        if allow_inactive_category and category and category.pk:
            category_queryset = clinic.yakap_categories.filter(Q(is_active=True) | Q(pk=category.pk))
        self.fields["category"].queryset = category_queryset
        self.fields["reversal_of"].queryset = YakapLedgerEntry.objects.none()
        self.fields["reversal_of"].required = False
        if category:
            self.fields["category"].initial = category
        if patient:
            reversal_choices = clinic.yakap_ledger_entries.filter(patient=patient).exclude(
                entry_type=YakapLedgerEntry.TYPE_REVERSAL
            )
            if appointment:
                reversal_choices = reversal_choices.filter(appointment=appointment)
            if category:
                reversal_choices = reversal_choices.filter(category=category)
            self.fields["reversal_of"].queryset = reversal_choices
        if not allow_privileged_entries:
            self.fields["entry_type"].choices = [(YakapLedgerEntry.TYPE_SERVICE_USAGE, "Service usage")]
            self.fields["verification_status"].choices = [(YakapLedgerEntry.VERIFICATION_VERIFIED, "Verified")]
            self.fields["reversal_of"].queryset = YakapLedgerEntry.objects.none()

    class Meta:
        model = YakapLedgerEntry
        fields = [
            "category",
            "entry_type",
            "amount",
            "verification_status",
            "occurred_at",
            "external_reference",
            "reversal_of",
            "note",
        ]
        widgets = {
            "category": forms.Select(attrs={"class": _SELECT}),
            "entry_type": forms.Select(attrs={"class": _SELECT}),
            "amount": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0.01"}),
            "verification_status": forms.Select(attrs={"class": _SELECT}),
            "occurred_at": forms.DateTimeInput(
                attrs={"class": _INPUT, "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "external_reference": forms.TextInput(attrs={"class": _INPUT}),
            "reversal_of": forms.Select(attrs={"class": _SELECT}),
            "note": forms.Textarea(attrs={"class": _TEXTAREA, "rows": 2}),
        }


class YakapExportForm(forms.Form):
    started_at = forms.DateField(widget=forms.DateInput(attrs={"class": _INPUT, "type": "date"}))
    ended_at = forms.DateField(widget=forms.DateInput(attrs={"class": _INPUT, "type": "date"}))

    def clean(self):
        cleaned_data = super().clean()
        started_at = cleaned_data.get("started_at")
        ended_at = cleaned_data.get("ended_at")
        if started_at and ended_at and ended_at < started_at:
            self.add_error("ended_at", "End date must be on or after the start date.")
        return cleaned_data
