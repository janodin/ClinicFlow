from django.contrib import admin

from .models import MessengerConnection, MessengerSession


@admin.register(MessengerConnection)
class MessengerConnectionAdmin(admin.ModelAdmin):
    list_display = ["clinic", "page_id", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["clinic__name", "page_id"]


@admin.register(MessengerSession)
class MessengerSessionAdmin(admin.ModelAdmin):
    list_display = ["connection", "psid", "state", "last_activity_at"]
    list_filter = ["state"]
    search_fields = ["psid"]
