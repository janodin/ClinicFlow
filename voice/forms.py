from django import forms

from .models import VoiceAgentSettings


_INPUT = "cf-input"
_SELECT = "cf-select"
_TEXTAREA = "cf-textarea"
_CHECKBOX = "cf-checkbox"


class VoiceAgentSettingsForm(forms.ModelForm):
    class Meta:
        model = VoiceAgentSettings
        fields = [
            "is_enabled",
            "display_name",
            "voice_label",
            "welcome_message",
            "provider",
            "is_test_mode_enabled",
        ]
        widgets = {
            "is_enabled": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "display_name": forms.TextInput(attrs={"class": _INPUT, "placeholder": "Voice Assistant"}),
            "voice_label": forms.Select(attrs={"class": _SELECT}),
            "welcome_message": forms.Textarea(attrs={"class": _TEXTAREA, "rows": 3}),
            "provider": forms.Select(attrs={"class": _SELECT}),
            "is_test_mode_enabled": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
        }
        labels = {
            "is_enabled": "Enable website voice agent",
            "display_name": "Display name",
            "voice_label": "Voice style",
            "welcome_message": "Welcome message",
            "provider": "Voice provider",
            "is_test_mode_enabled": "Allow dashboard live tests",
        }
