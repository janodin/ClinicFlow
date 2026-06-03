from django.contrib import admin
from django import forms

from clinics.admin_mixins import SuperuserOnlyAdminMixin

from .models import MessengerAISettings, MessengerConnection, MessengerSession


class MessengerConnectionAdminForm(forms.ModelForm):
    class Meta:
        model = MessengerConnection
        fields = "__all__"
        widgets = {
            "app_secret": forms.PasswordInput(render_value=False),
            "page_access_token": forms.PasswordInput(render_value=False),
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


@admin.register(MessengerConnection)
class MessengerConnectionAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    form = MessengerConnectionAdminForm
    list_display = ["clinic", "app_id", "page_name", "page_id", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["clinic__name", "app_id", "page_name", "page_id"]


@admin.register(MessengerAISettings)
class MessengerAISettingsAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ["connection", "is_ai_enabled", "updated_at"]
    list_filter = ["is_ai_enabled"]
    search_fields = ["connection__clinic__name", "connection__page_id"]


@admin.register(MessengerSession)
class MessengerSessionAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ["connection", "psid", "state", "last_activity_at"]
    list_filter = ["state"]
    search_fields = ["psid"]
