from django.contrib import admin

from clinics.admin_mixins import SuperuserOnlyAdminMixin

from .models import ClinicBusinessHour, UnavailableDate


@admin.register(ClinicBusinessHour)
class ClinicBusinessHourAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("clinic", "weekday", "is_open", "open_time", "close_time")


@admin.register(UnavailableDate)
class UnavailableDateAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("clinic", "date", "reason")

# Register your models here.
