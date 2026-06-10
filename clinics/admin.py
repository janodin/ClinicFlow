from django.contrib import admin

from .admin_mixins import SuperuserOnlyAdminMixin
from .models import Clinic, ClinicAIProviderSettings, ClinicFAQ, ClinicGroup, ClinicMembership


@admin.register(ClinicGroup)
class ClinicGroupAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("name", "owner", "plan", "status", "appointment_limit")
    search_fields = ("name", "owner__email")


@admin.register(Clinic)
class ClinicAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("name", "slug", "group", "timezone", "booking_approval_mode", "is_active")
    list_filter = ("is_active", "booking_approval_mode")
    search_fields = ("name", "slug", "email", "phone")


@admin.register(ClinicAIProviderSettings)
class ClinicAIProviderSettingsAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("clinic", "provider", "model", "has_api_key")
    list_filter = ("provider",)
    search_fields = ("clinic__name", "clinic__slug", "model")
    readonly_fields = ("has_api_key",)
    exclude = ("api_key",)


@admin.register(ClinicMembership)
class ClinicMembershipAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("user", "clinic", "role")
    list_filter = ("role",)


@admin.register(ClinicFAQ)
class ClinicFAQAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("question", "clinic", "is_active")

# Register your models here.
