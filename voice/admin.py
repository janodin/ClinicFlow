from django.contrib import admin

from clinics.admin_mixins import SuperuserOnlyAdminMixin

from .models import VoiceAgentSettings, VoiceSession, VoiceTranscriptTurn


@admin.register(VoiceAgentSettings)
class VoiceAgentSettingsAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    exclude = ("provider_secret_ref",)
    list_display = ("clinic", "is_enabled", "provider", "voice_label", "is_test_mode_enabled", "updated_at")
    list_filter = ("is_enabled", "provider", "voice_label", "is_test_mode_enabled")
    search_fields = ("clinic__name", "clinic__slug", "display_name")


@admin.register(VoiceSession)
class VoiceSessionAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("clinic", "public_session_id", "status", "source", "is_test", "last_activity_at")
    list_filter = ("status", "source", "is_test", "provider")
    search_fields = ("clinic__name", "clinic__slug", "public_session_id", "conversation_id", "provider_session_id")


@admin.register(VoiceTranscriptTurn)
class VoiceTranscriptTurnAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("session", "sequence", "role", "status", "created_at")
    list_filter = ("role", "status")
    search_fields = ("session__public_session_id", "session__clinic__name", "text", "provider_event_id")
