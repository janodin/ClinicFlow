from zoneinfo import available_timezones

from django import forms

from .models import Clinic, ClinicAISettings, ClinicFAQ

_INPUT = "cf-input"
_SELECT = "cf-select"
_TEXTAREA = "cf-textarea"
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
            "show_reason_field",
        ]
        widgets = {
            "widget_accent_color": forms.TextInput(attrs={"type": "color", "class": _COLOR}),
            "widget_welcome_message": forms.Textarea(attrs={"class": _TEXTAREA, "placeholder": "Welcome message shown in the widget", "rows": 3}),
            "show_reason_field": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
        }


class SharedAISettingsForm(forms.ModelForm):
    class Meta:
        model = ClinicAISettings
        fields = ["is_ai_enabled", "instructions", "fallback_message"]
        widgets = {
            "is_ai_enabled": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "instructions": forms.Textarea(attrs={
                "class": _TEXTAREA,
                "placeholder": "Tell the shared assistant how to speak, what clinic policies to follow, and what it should avoid.",
                "rows": 8,
            }),
            "fallback_message": forms.Textarea(attrs={
                "class": _TEXTAREA,
                "placeholder": "Example: Our team will help you shortly. Please call the clinic for urgent concerns.",
                "rows": 3,
            }),
        }
        labels = {
            "is_ai_enabled": "Enable AI replies",
            "instructions": "Prompt / Instructions",
            "fallback_message": "Fallback message",
        }
        help_texts = {
            "instructions": "Used by both the website Assistant and Facebook Messenger. Services, prices, and availability still come from ClinicFlow.",
            "fallback_message": "Shown in both channels when AI replies are disabled or unavailable.",
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
