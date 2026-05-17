from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from appointments.models import Appointment, AppointmentNote
from patients.models import Patient
from scheduling.utils import get_working_window, _inside_break, slot_is_available_for_appointment


_INPUT = "w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm text-slate-800 placeholder:text-slate-400 focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 transition"
_SELECT = "w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm text-slate-800 bg-white focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 transition appearance-none"
_TEXTAREA = "w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm text-slate-800 placeholder:text-slate-400 focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 transition resize-y"


class GuestBookingForm(forms.Form):
    service = forms.ModelChoiceField(queryset=None, widget=forms.Select(attrs={"class": _SELECT}))
    selected_slot = forms.CharField(widget=forms.HiddenInput())
    full_name = forms.CharField(max_length=160, widget=forms.TextInput(attrs={"class": _INPUT, "placeholder": "Juan Dela Cruz"}))
    phone = forms.CharField(max_length=40, widget=forms.TextInput(attrs={"class": _INPUT, "placeholder": "09XXXXXXXXX"}))
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={"class": _INPUT, "placeholder": "patient@email.com"}))
    reason = forms.CharField(widget=forms.Textarea(attrs={"class": _TEXTAREA, "placeholder": "Reason for visit", "rows": 3}), required=False)

    def __init__(self, clinic, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.clinic = clinic
        self.fields["service"].queryset = clinic.services.filter(is_active=True)


class StaffAppointmentForm(forms.ModelForm):
    patient_name = forms.CharField(max_length=160, widget=forms.TextInput(attrs={"class": _INPUT, "placeholder": "Patient name"}))
    patient_phone = forms.CharField(max_length=40, widget=forms.TextInput(attrs={"class": _INPUT, "placeholder": "Phone number"}))
    patient_email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={"class": _INPUT, "placeholder": "patient@email.com"}))
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
        self.fields["service"].queryset = clinic.services.filter(is_active=True)
        if self.instance and self.instance.pk:
            self.fields["date"].initial = self.instance.starts_at.date()
            self.fields["time"].initial = self.instance.starts_at.time()
            self.fields["patient_name"].initial = self.instance.patient.full_name
            self.fields["patient_phone"].initial = self.instance.patient.phone
            self.fields["patient_email"].initial = self.instance.patient.email

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

            window = get_working_window(self.clinic, date)
            if not window:
                raise ValidationError("Clinic is not open on this day.")
            open_time, close_time, break_start, break_end = window
            if starts_at.time() < open_time or ends_at.time() > close_time:
                raise ValidationError("Selected time is outside working hours.")
            if _inside_break(starts_at.time(), ends_at.time(), break_start, break_end):
                raise ValidationError("Selected time overlaps with a scheduled break.")

            exclude = self.instance if self.instance and self.instance.pk else None
            if not slot_is_available_for_appointment(self.clinic, starts_at, ends_at, exclude_appointment=exclude):
                raise ValidationError("This slot is not available.")

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
            if not self.instance.can_transition_to(new_status):
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
