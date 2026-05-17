from zoneinfo import available_timezones

from django import forms

from .models import Clinic, ClinicFAQ

# Text inputs / textareas match PatientForm tailwind styling.
# Selects use ui-input ui-select because <select> elements need
# appearance:none plus a custom arrow and different padding handling.
_INPUT = "w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm text-slate-800 placeholder:text-slate-400 focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 transition"
_SELECT = "w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm text-slate-800 bg-white focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 transition appearance-none"
_TEXTAREA = "w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm text-slate-800 placeholder:text-slate-400 focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 transition resize-y"
_CHECKBOX = "cf-checkbox"
_COLOR = "h-10 w-20 rounded-xl border border-[var(--cf-line)] p-1 cursor-pointer"

_TIMEZONE_CHOICES = sorted([(tz, tz) for tz in available_timezones()])


class ClinicSettingsForm(forms.ModelForm):
    class Meta:
        model = Clinic
        fields = [
            "name",
            "address",
            "phone",
            "email",
            "timezone",
            "default_appointment_duration",
            "booking_approval_mode",
        ]
        labels = {
            "default_appointment_duration": "Default appointment duration (in minutes)",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": _INPUT, "placeholder": "Clinic name"}),
            "address": forms.TextInput(attrs={"class": _INPUT, "placeholder": "Clinic address"}),
            "phone": forms.TextInput(attrs={"class": _INPUT, "placeholder": "Clinic phone"}),
            "email": forms.EmailInput(attrs={"class": _INPUT, "placeholder": "clinic@email.com"}),
            "timezone": forms.Select(attrs={"class": _SELECT}, choices=_TIMEZONE_CHOICES),
            "default_appointment_duration": forms.NumberInput(attrs={"class": _INPUT, "placeholder": "30"}),
            "booking_approval_mode": forms.Select(attrs={"class": _SELECT}),
        }


class WidgetSettingsForm(forms.ModelForm):
    class Meta:
        model = Clinic
        fields = [
            "widget_accent_color",
            "widget_welcome_message",
            "widget_behavior_instructions",
            "show_reason_field",
        ]
        widgets = {
            "widget_accent_color": forms.TextInput(attrs={"type": "color", "class": _COLOR}),
            "widget_welcome_message": forms.Textarea(attrs={"class": _TEXTAREA, "placeholder": "Welcome message shown in the widget", "rows": 3}),
            "widget_behavior_instructions": forms.Textarea(attrs={"class": _TEXTAREA, "placeholder": "Instructions for the booking assistant", "rows": 3}),
            "show_reason_field": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
        }


class ClinicFAQForm(forms.ModelForm):
    class Meta:
        model = ClinicFAQ
        fields = ["question", "answer", "is_active"]
        widgets = {
            "question": forms.TextInput(attrs={"class": _INPUT, "placeholder": "e.g. What are your business hours?"}),
            "answer": forms.Textarea(attrs={"class": _TEXTAREA, "placeholder": "e.g. We are open Monday to Friday, 9 AM to 5 PM.", "rows": 3}),
            "is_active": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
        }
