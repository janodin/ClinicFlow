from django.contrib import admin

from .models import BlockedTime, ClinicBusinessHour, UnavailableDate


@admin.register(ClinicBusinessHour)
class ClinicBusinessHourAdmin(admin.ModelAdmin):
    list_display = ("clinic", "weekday", "is_open", "open_time", "close_time")


@admin.register(BlockedTime)
class BlockedTimeAdmin(admin.ModelAdmin):
    list_display = ("clinic", "starts_at", "ends_at", "reason")


@admin.register(UnavailableDate)
class UnavailableDateAdmin(admin.ModelAdmin):
    list_display = ("clinic", "date", "reason")

# Register your models here.
