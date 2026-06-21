from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from clinics.models import ClinicAISettings
from widget.ai_client import fallback_message_for

from .adapters import get_voice_adapter
from .emotion import resolve_voice_emotion, voice_emotion_profile, voice_style_guidance
from .models import VoiceAgentSettings, VoiceSession, VoiceTranscriptTurn


VOICE_RATE_LIMIT_MESSAGE = "Too many voice messages. Please wait before trying again."
VOICE_SESSION_RATE_LIMIT_MESSAGE = "Too many voice sessions. Please wait before trying again."


def build_gateway_reply(data):
    from messenger.ai_gateway import build_gateway_reply as gateway_reply

    return gateway_reply(data)


def get_or_create_voice_settings(clinic):
    settings_obj, _ = VoiceAgentSettings.objects.get_or_create(clinic=clinic)
    return settings_obj


def voice_settings_for_clinic(clinic):
    return VoiceAgentSettings.objects.filter(clinic=clinic).first()


def voice_enabled_for_clinic(clinic):
    settings_obj = voice_settings_for_clinic(clinic)
    return bool(settings_obj and settings_obj.is_enabled)


def voice_settings_enabled(settings_obj):
    return bool(settings_obj and settings_obj.is_enabled)


def create_widget_voice_session(clinic):
    voice_settings = get_or_create_voice_settings(clinic)
    session = VoiceSession.objects.create(
        clinic=clinic,
        provider=voice_settings.provider,
        source=VoiceSession.SOURCE_WIDGET,
        status=VoiceSession.STATUS_ACTIVE,
        started_at=timezone.now(),
        last_activity_at=timezone.now(),
    )
    return session, voice_settings


def create_dashboard_test_session(clinic):
    voice_settings = get_or_create_voice_settings(clinic)
    session = VoiceSession.objects.create(
        clinic=clinic,
        provider=voice_settings.provider,
        source=VoiceSession.SOURCE_DASHBOARD_TEST,
        status=VoiceSession.STATUS_ACTIVE,
        is_test=True,
        started_at=timezone.now(),
        last_activity_at=timezone.now(),
    )
    return session, voice_settings


def voice_welcome_reply_payload(voice_settings):
    adapter = get_voice_adapter(voice_settings.provider)
    emotion = resolve_voice_emotion("", voice_settings.welcome_message, voice_settings)
    profile = voice_emotion_profile(emotion, voice_settings.safe_emotion_intensity)
    return adapter.reply_payload(voice_settings.welcome_message, emotion_profile=profile)


def _cache_rate_limited(key, limit, window_seconds):
    if limit <= 0:
        return False
    cache.add(key, 0, timeout=window_seconds)
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=window_seconds)
        return False
    return count > limit


def voice_turn_rate_limited(session, actor):
    limit = getattr(settings, "VOICE_TURN_RATE_LIMIT", 20)
    window_seconds = getattr(settings, "VOICE_TURN_RATE_WINDOW_SECONDS", 300)
    key = f"voice_turn_rate:{session.clinic_id}:{actor}"
    return _cache_rate_limited(key, limit, window_seconds)


def voice_session_rate_limited(clinic, actor):
    limit = getattr(settings, "VOICE_SESSION_RATE_LIMIT", 10)
    window_seconds = getattr(settings, "VOICE_SESSION_RATE_WINDOW_SECONDS", 300)
    key = f"voice_session_rate:{clinic.id}:{actor}"
    return _cache_rate_limited(key, limit, window_seconds)


def _next_sequence_for_locked_session(session):
    current = session.transcript_turns.aggregate(value=Max("sequence"))["value"] or 0
    return current + 1


def _history_for_session(session):
    turns = list(
        session.transcript_turns.filter(
            status=VoiceTranscriptTurn.STATUS_FINAL,
            role__in=[VoiceTranscriptTurn.ROLE_USER, VoiceTranscriptTurn.ROLE_ASSISTANT],
        ).order_by("-sequence")[:16]
    )
    return [
        {"role": turn.role, "content": turn.text}
        for turn in reversed(turns)
    ]


def handle_voice_turn(session, message):
    clean_message = str(message or "").strip()
    ai_settings, _ = ClinicAISettings.objects.get_or_create(clinic=session.clinic)
    voice_settings = get_or_create_voice_settings(session.clinic)
    if not clean_message:
        reply = "I did not catch that. Please try again."
    else:
        with transaction.atomic():
            locked_session = VoiceSession.objects.select_for_update().select_related("clinic").get(pk=session.pk)
            history = _history_for_session(locked_session)
            next_sequence = _next_sequence_for_locked_session(locked_session)
            VoiceTranscriptTurn.objects.create(
                session=locked_session,
                role=VoiceTranscriptTurn.ROLE_USER,
                text=clean_message,
                sequence=next_sequence,
            )
            locked_session.last_activity_at = timezone.now()
            locked_session.save(update_fields=["last_activity_at", "updated_at"])
        preliminary_emotion = resolve_voice_emotion(clean_message, "", voice_settings)
        if preliminary_emotion == VoiceAgentSettings.EMOTION_CELEBRATORY:
            preliminary_emotion = VoiceAgentSettings.EMOTION_WARM
        gateway_reply = build_gateway_reply({
            "channel": "voice",
            "clinic_slug": session.clinic.slug,
            "message": clean_message,
            "history": history,
            "conversation_id": session.conversation_id,
            "voice_style": voice_style_guidance(preliminary_emotion, voice_settings.safe_emotion_intensity),
        })
        reply = gateway_reply.get("reply") or fallback_message_for(ai_settings)

    emotion = resolve_voice_emotion(clean_message, reply, voice_settings)
    profile = voice_emotion_profile(emotion, voice_settings.safe_emotion_intensity)
    adapter = get_voice_adapter(session.provider)
    provider_reply = adapter.reply_payload(reply, emotion_profile=profile)
    with transaction.atomic():
        locked_session = VoiceSession.objects.select_for_update().get(pk=session.pk)
        next_sequence = _next_sequence_for_locked_session(locked_session)
        VoiceTranscriptTurn.objects.create(
            session=locked_session,
            role=VoiceTranscriptTurn.ROLE_ASSISTANT,
            text=provider_reply.text,
            sequence=next_sequence,
        )
        locked_session.last_activity_at = timezone.now()
        locked_session.save(update_fields=["last_activity_at", "updated_at"])
    return provider_reply
