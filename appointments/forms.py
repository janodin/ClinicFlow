from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django import forms
from django.utils import timezone

from appointments.models import Appointment, AppointmentNote
from patients.utils import normalize_phone
from scheduling.utils import validate_slot


_INPUT = "cf-input"
_SELECT = "cf-select"
_TEXTAREA = "cf-textarea"
MIN_PATIENT_PHONE_DIGITS = 7


class GuestBookingForm(forms.Form):
    service = forms.ModelChoiceField(queryset=None, widget=forms.Select(attrs={"class": _SELECT}))
    selected_slot = forms.CharField(widget=forms.HiddenInput())
    full_name = forms.CharField(max_length=160, widget=forms.TextInput(attrs={"class": _INPUT, "placeholder": "Juan Dela Cruz"}))
    phone = forms.CharField(max_length=40, widget=forms.TextInput(attrs={"class": _INPUT, "placeholder": "09XXXXXXXXX"}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": _INPUT, "placeholder": "patient@email.com"}))
    reason = forms.CharField(widget=forms.Textarea(attrs={"class": _TEXTAREA, "placeholder": "Reason for visit", "rows": 3}), required=False)

    def __init__(self, clinic, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.clinic = clinic
        self.fields["service"].queryset = clinic.services.filter(is_active=True, is_archived=False)


class StaffAppointmentForm(forms.ModelForm):
    patient_name = forms.CharField(max_length=160, widget=forms.TextInput(attrs={"class": _INPUT, "placeholder": "Patient name"}))
    patient_phone = forms.CharField(max_length=40, widget=forms.TextInput(attrs={"class": _INPUT, "placeholder": "Phone number"}))
    patient_email = forms.EmailField(widget=forms.EmailInput(attrs={"class": _INPUT, "placeholder": "patient@email.com"}))
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date", "class": _INPUT}))
    time = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time", "class": _INPUT}))

    class Meta:
        model = Appointment
        fields = ["service", "status", "payment_state", "source", "reason"]
        widgets = {
            "service": forms.Select(attrs={"class": _SELECT}),
            "status": forms.Select(attrs={"class": _SELECT}),
            "payment_state": forms.Select(attrs={"class": _SELECT}),
            "source": forms.Select(attrs={"class": _SELECT}),
            "reason": forms.Textarea(attrs={"class": _TEXTAREA, "placeholder": "Reason for visit", "rows": 3}),
        }

    def __init__(self, clinic, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.clinic = clinic
        self.fields["service"].queryset = clinic.services.filter(is_active=True, is_archived=False)
        if self.instance and self.instance.pk:
            starts_at = self.instance.starts_at.astimezone(ZoneInfo(self.clinic.timezone))
            self.fields["date"].initial = starts_at.date()
            self.fields["time"].initial = starts_at.time().replace(second=0, microsecond=0)
            self.fields["patient_name"].initial = self.instance.patient.full_name
            self.fields["patient_phone"].initial = self.instance.patient.phone
            self.fields["patient_email"].initial = self.instance.patient.email

    def clean_patient_phone(self):
        phone = self.cleaned_data.get("patient_phone", "")
        if len(normalize_phone(phone)) < MIN_PATIENT_PHONE_DIGITS:
            raise forms.ValidationError("Phone number must contain at least 7 digits.")
        return phone

    def clean_status(self):
        status = self.cleaned_data.get("status")
        if self.instance and self.instance.pk and status != self.instance.status:
            if not self.instance.can_transition_to(status):
                raise forms.ValidationError(
                    f"Cannot change status from {self.instance.get_status_display()} to {dict(Appointment.STATUS_CHOICES).get(status)}."
                )
        return status

    def clean(self):
        cleaned_data = super().clean()
        date = cleaned_data.get("date")
        time = cleaned_data.get("time")
        service = cleaned_data.get("service")
        if date and time and service:
            tz = ZoneInfo(self.clinic.timezone)
            starts_at = timezone.make_aware(datetime.combine(date, time), tz)
            duration = service.effective_duration()
            ends_at = starts_at + timedelta(minutes=duration)

            exclude = self.instance if self.instance and self.instance.pk else None
            validate_slot(self.clinic, starts_at, ends_at, exclude_appointment=exclude)

            cleaned_data["starts_at"] = starts_at
            cleaned_data["ends_at"] = ends_at
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.starts_at = self.cleaned_data["starts_at"]
        instance.ends_at = self.cleaned_data["ends_at"]
        if commit:
            instance.save()
        return instance


class AppointmentStatusForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = ["status", "payment_state"]
        widgets = {
            "status": forms.Select(attrs={"class": _SELECT}),
            "payment_state": forms.Select(attrs={"class": _SELECT}),
        }

    def clean_status(self):
        new_status = self.cleaned_data["status"]
        if self.instance and self.instance.pk:
            if new_status != self.instance.status and not self.instance.can_transition_to(new_status):
                raise forms.ValidationError(
                    f"Cannot change status from {self.instance.get_status_display()} to {dict(Appointment.STATUS_CHOICES).get(new_status)}."
                )
        return new_status


class AppointmentNoteForm(forms.ModelForm):
    class Meta:
        model = AppointmentNote
        fields = ["body"]
        widgets = {
            "body": forms.Textarea(attrs={"class": _TEXTAREA, "placeholder": "Add a note...", "rows": 3}),
        }
