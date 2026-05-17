from django.contrib import admin

from .models import Service


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "clinic", "duration_minutes", "price", "is_active")
    list_filter = ("clinic", "is_active")
    search_fields = ("name",)

# Register your models here.
