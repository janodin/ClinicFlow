from django.contrib import admin

from clinics.admin_mixins import SuperuserOnlyAdminMixin

from .models import Patient


@admin.register(Patient)
class PatientAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("full_name", "clinic", "phone", "email")
    search_fields = ("full_name", "phone", "email")
    list_filter = ("clinic",)

# Register your models here.
