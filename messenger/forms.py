from django import forms

from messenger.models import MessengerConnection


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
