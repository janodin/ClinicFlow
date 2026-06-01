from django.contrib import admin

from .models import ClinicBusinessHour, UnavailableDate


@admin.register(ClinicBusinessHour)
class ClinicBusinessHourAdmin(admin.ModelAdmin):
    list_display = ("clinic", "weekday", "is_open", "open_time", "close_time")


@admin.register(UnavailableDate)
class UnavailableDateAdmin(admin.ModelAdmin):
    list_display = ("clinic", "date", "reason")

# Register your models here.
