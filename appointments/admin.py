from django.contrib import admin

from clinics.admin_mixins import SuperuserOnlyAdminMixin

from .models import Appointment, AppointmentNote


class AppointmentNoteInline(SuperuserOnlyAdminMixin, admin.TabularInline):
    model = AppointmentNote
    extra = 0


@admin.register(Appointment)
class AppointmentAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("patient", "clinic", "service", "starts_at", "status", "source")
    list_filter = ("clinic", "status", "source")
    search_fields = ("patient__full_name", "patient__phone", "service__name")
    inlines = [AppointmentNoteInline]

# Register your models here.
