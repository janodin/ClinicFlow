from django import forms

from messenger.models import MessengerConnection


SAVED_SECRET_MASK = "************"


class SavedSecretPasswordInput(forms.PasswordInput):
    def __init__(self, attrs=None):
        super().__init__(attrs=attrs, render_value=True)

    def get_context(self, name, value, attrs):
        safe_value = value if value == SAVED_SECRET_MASK else None
        return super().get_context(name, safe_value, attrs)


class MessengerConnectionForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            if self.instance.app_secret:
                self.initial["app_secret"] = SAVED_SECRET_MASK
            if self.instance.page_access_token:
                self.initial["page_access_token"] = SAVED_SECRET_MASK

    class Meta:
        model = MessengerConnection
        fields = ["app_id", "app_secret", "page_id", "page_access_token"]
        widgets = {
            "app_id": forms.TextInput(attrs={
                "class": "ui-input",
                "placeholder": "e.g. 123456789012345",
            }),
            "app_secret": SavedSecretPasswordInput(attrs={
                "class": "ui-input pr-12",
                "placeholder": "Leave blank to keep saved App Secret",
            }),
            "page_id": forms.TextInput(attrs={
                "class": "ui-input",
                "placeholder": "e.g. 123456789012345",
            }),
            "page_access_token": SavedSecretPasswordInput(attrs={
                "class": "ui-input pr-12",
                "placeholder": "Leave blank to keep saved Page Access Token",
            }),
        }
        labels = {
            "app_id": "Facebook App ID",
            "app_secret": "Facebook App Secret",
            "page_id": "Facebook Page ID",
            "page_access_token": "Page Access Token",
        }

    def clean(self):
        cleaned_data = super().clean()
        if not (cleaned_data.get("page_id") or "").strip():
            self.add_error("page_id", "Facebook Page ID is required to connect Messenger.")
        if not (cleaned_data.get("page_access_token") or "").strip():
            self.add_error("page_access_token", "Page Access Token is required to connect Messenger.")
        return cleaned_data

    def clean_app_secret(self):
        app_secret = self.cleaned_data.get("app_secret", "")
        if app_secret in {"", SAVED_SECRET_MASK} and self.instance and self.instance.pk:
            return self.instance.app_secret
        return app_secret

    def clean_page_access_token(self):
        page_access_token = self.cleaned_data.get("page_access_token", "")
        if page_access_token in {"", SAVED_SECRET_MASK} and self.instance and self.instance.pk:
            return self.instance.page_access_token
        return page_access_token
