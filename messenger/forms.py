from django import forms

from clinics.models import ClinicAISettings
from messenger.models import MessengerConnection


class MessengerConnectionForm(forms.ModelForm):
    class Meta:
        model = MessengerConnection
        fields = ["app_id", "app_secret", "page_id", "page_access_token"]
        widgets = {
            "app_id": forms.TextInput(attrs={
                "class": "ui-input",
                "placeholder": "e.g. 123456789012345",
            }),
            "app_secret": forms.PasswordInput(attrs={
                "class": "ui-input",
                "placeholder": "Leave blank to keep saved App Secret",
            }, render_value=False),
            "page_id": forms.TextInput(attrs={
                "class": "ui-input",
                "placeholder": "e.g. 123456789012345",
            }),
            "page_access_token": forms.PasswordInput(attrs={
                "class": "ui-input",
                "placeholder": "Leave blank to keep saved Page Access Token",
            }, render_value=False),
        }
        labels = {
            "app_id": "Facebook App ID",
            "app_secret": "Facebook App Secret",
            "page_id": "Facebook Page ID",
            "page_access_token": "Page Access Token",
        }

    def clean_app_secret(self):
        app_secret = self.cleaned_data.get("app_secret", "")
        if not app_secret and self.instance and self.instance.pk:
            return self.instance.app_secret
        return app_secret

    def clean_page_access_token(self):
        page_access_token = self.cleaned_data.get("page_access_token", "")
        if not page_access_token and self.instance and self.instance.pk:
            return self.instance.page_access_token
        return page_access_token


class MessengerAISettingsForm(forms.ModelForm):
    class Meta:
        model = ClinicAISettings
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
            "instructions": "Used by both Messenger and the website Assistant. Services, prices, and availability still come from ClinicFlow.",
            "fallback_message": "Shown in both Messenger and the website Assistant when AI replies are disabled or unavailable.",
        }
