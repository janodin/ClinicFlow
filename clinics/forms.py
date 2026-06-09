from zoneinfo import available_timezones

from django import forms

from .ai_provider_validation import validate_ai_provider_base_url
from .models import Clinic, ClinicAIProviderSettings, ClinicAISettings, ClinicFAQ

_INPUT = "cf-input"
_SELECT = "cf-select"
_TEXTAREA = "cf-textarea"
_CHECKBOX = "cf-checkbox"
_COLOR = "h-10 w-20 rounded-xl border border-[var(--cf-line)] p-1 cursor-pointer"

SAVED_PROVIDER_SECRET_MASK = "************"


class SavedProviderSecretInput(forms.PasswordInput):
    def __init__(self, attrs=None):
        super().__init__(attrs=attrs, render_value=True)

    def get_context(self, name, value, attrs):
        safe_value = value if value == SAVED_PROVIDER_SECRET_MASK else None
        return super().get_context(name, safe_value, attrs)


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
        ]
        widgets = {
            "widget_accent_color": forms.TextInput(attrs={"type": "color", "class": _COLOR}),
            "widget_welcome_message": forms.Textarea(attrs={"class": _TEXTAREA, "placeholder": "Welcome message shown in the widget", "rows": 3}),
        }


class SharedAISettingsForm(forms.ModelForm):
    class Meta:
        model = ClinicAISettings
        fields = [
            "is_ai_enabled",
            "messenger_response_mode",
            "communication_tone",
            "custom_tone_instructions",
            "instructions",
            "fallback_message",
        ]
        widgets = {
            "is_ai_enabled": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "messenger_response_mode": forms.RadioSelect(attrs={"class": _CHECKBOX}),
            "communication_tone": forms.Select(attrs={"class": _SELECT}),
            "custom_tone_instructions": forms.Textarea(attrs={"class": f"{_TEXTAREA} cf-textarea-compact", "rows": 2, "maxlength": 500}),
            "instructions": forms.Textarea(attrs={
                "class": _TEXTAREA,
                "placeholder": "Tell the shared assistant what clinic policies to follow, what it should avoid, and how to handle common patient questions.",
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
            "messenger_response_mode": "Messenger response mode",
            "communication_tone": "Communication tone",
            "custom_tone_instructions": "Custom tone notes",
            "instructions": "Prompt / Instructions",
            "fallback_message": "Fallback message",
        }
        help_texts = {
            "communication_tone": "Sets the assistant's patient-facing style for website Assistant and Messenger AI mode.",
            "custom_tone_instructions": "Optional style-only notes. Tone cannot override services, prices, availability, booking rules, or safety checks.",
            "instructions": "Used by the website Assistant and Messenger AI mode for broader clinic policies. Tone is controlled above. Services, prices, and availability still come from KliniAssist.",
            "fallback_message": "Shown when AI replies are disabled or unavailable.",
        }


class AIProviderSettingsForm(forms.ModelForm):
    base_url = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.URLInput(attrs={"class": _INPUT, "placeholder": "https://api.openai.com/v1"}),
        label="Base URL",
    )
    openai_model = forms.ChoiceField(
        choices=ClinicAIProviderSettings.OPENAI_MODEL_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": _SELECT}),
        label="Primary model",
    )
    openai_fallback_model = forms.ChoiceField(
        choices=ClinicAIProviderSettings.OPENAI_MODEL_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": _SELECT}),
        label="Fallback model",
    )

    class Meta:
        model = ClinicAIProviderSettings
        fields = [
            "provider",
            "base_url",
            "openai_model",
            "openai_fallback_model",
            "api_key",
            "is_enabled",
        ]
        widgets = {
            "provider": forms.Select(attrs={"class": _SELECT}),
            "api_key": SavedProviderSecretInput(attrs={"class": f"{_INPUT} pr-12", "placeholder": "Leave blank to keep saved API key"}),
            "is_enabled": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
        }
        labels = {
            "provider": "AI provider",
            "api_key": "API key",
            "is_enabled": "Enable clinic-owned AI provider",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            if self.instance.api_key:
                self.initial["api_key"] = SAVED_PROVIDER_SECRET_MASK
            self.initial["openai_model"] = self.instance.model or ClinicAIProviderSettings.DEFAULT_OPENAI_MODEL
            self.initial["openai_fallback_model"] = self.instance.fallback_model or ClinicAIProviderSettings.DEFAULT_OPENAI_MODEL

    def clean_api_key(self):
        api_key = self.cleaned_data.get("api_key", "")
        if api_key in {"", SAVED_PROVIDER_SECRET_MASK} and self.instance and self.instance.pk:
            return self.instance.api_key
        return api_key

    def clean(self):
        cleaned = super().clean()
        provider = cleaned.get("provider")
        enabled = cleaned.get("is_enabled")
        base_url_invalid = False
        selected_model = cleaned.get("openai_model") or ""
        selected_fallback_model = cleaned.get("openai_fallback_model") or ""
        if provider == ClinicAIProviderSettings.PROVIDER_OPENAI:
            cleaned["base_url"] = ClinicAIProviderSettings.OPENAI_BASE_URL
            cleaned["model"] = selected_model
            cleaned["fallback_model"] = selected_fallback_model
        elif provider == ClinicAIProviderSettings.PROVIDER_OPENAI_COMPATIBLE:
            base_url = cleaned.get("base_url") or ""
            if base_url:
                try:
                    cleaned["base_url"] = validate_ai_provider_base_url(base_url)
                except forms.ValidationError as exc:
                    base_url_invalid = True
                    self.add_error("base_url", exc)
            cleaned["model"] = selected_model
            cleaned["fallback_model"] = selected_fallback_model
        else:
            self.add_error("provider", "Choose a supported AI provider.")

        if enabled:
            if not (cleaned.get("api_key") or "").strip():
                self.add_error("api_key", "API key is required when the AI provider is enabled.")
            if not (cleaned.get("model") or "").strip():
                self.add_error("openai_model", "Model is required when the AI provider is enabled.")
            if not (cleaned.get("fallback_model") or "").strip():
                self.add_error("openai_fallback_model", "Fallback model is required when the AI provider is enabled.")
            if not base_url_invalid and not (cleaned.get("base_url") or "").strip():
                self.add_error("base_url", "Base URL is required when the AI provider is enabled.")
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.model = self.cleaned_data.get("model", instance.model)
        instance.fallback_model = self.cleaned_data.get("fallback_model", instance.fallback_model)
        if instance.provider == ClinicAIProviderSettings.PROVIDER_OPENAI:
            instance.base_url = ClinicAIProviderSettings.OPENAI_BASE_URL
        else:
            instance.base_url = self.cleaned_data.get("base_url", instance.base_url)
        if commit:
            instance.save()
        return instance


class ClinicFAQForm(forms.ModelForm):
    class Meta:
        model = ClinicFAQ
        fields = ["question", "answer", "is_active"]
        widgets = {
            "question": forms.TextInput(attrs={"class": _INPUT, "placeholder": "e.g. What are your business hours?"}),
            "answer": forms.Textarea(attrs={"class": _TEXTAREA, "placeholder": "e.g. We are open Monday to Friday, 9 AM to 5 PM.", "rows": 3}),
            "is_active": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
        }
