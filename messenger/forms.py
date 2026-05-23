from django import forms

from messenger.models import MessengerAISettings, MessengerConnection


class MessengerConnectionForm(forms.ModelForm):
    class Meta:
        model = MessengerConnection
        fields = ["page_id", "page_access_token"]
        widgets = {
            "page_id": forms.TextInput(attrs={
                "class": "ui-input",
                "placeholder": "e.g. 123456789012345",
            }),
            "page_access_token": forms.TextInput(attrs={
                "class": "ui-input",
                "placeholder": "Paste your Page Access Token",
                "type": "password",
            }),
        }
        labels = {
            "page_id": "Facebook Page ID",
            "page_access_token": "Page Access Token",
        }


class MessengerAISettingsForm(forms.ModelForm):
    class Meta:
        model = MessengerAISettings
        fields = ["is_ai_enabled", "instructions", "fallback_message"]
        widgets = {
            "is_ai_enabled": forms.CheckboxInput(attrs={
                "class": "h-4 w-4 rounded border-[var(--cf-line)] text-[var(--cf-brand)] focus:ring-[var(--cf-focus)]",
            }),
            "instructions": forms.Textarea(attrs={
                "class": "ui-input min-h-36",
                "placeholder": "Tell the Messenger AI how to speak, what clinic policies to follow, and what it should avoid.",
                "rows": 6,
            }),
            "fallback_message": forms.Textarea(attrs={
                "class": "ui-input min-h-24",
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
            "instructions": "Services, prices, and availability still come from ClinicFlow.",
            "fallback_message": "Shown when AI replies are disabled or the AI cannot safely respond.",
        }
