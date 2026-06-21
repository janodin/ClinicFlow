import json

from django.conf import settings as django_settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.crypto import constant_time_compare
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from clinics.models import Clinic
from clinics.tenant import get_active_membership, user_can_manage_settings

from .models import VoiceSession
from .services import (
    VOICE_RATE_LIMIT_MESSAGE,
    VOICE_SESSION_RATE_LIMIT_MESSAGE,
    create_dashboard_test_session,
    create_widget_voice_session,
    get_or_create_voice_settings,
    handle_voice_turn,
    voice_session_rate_limited,
    voice_settings_enabled,
    voice_settings_for_clinic,
    voice_turn_rate_limited,
    voice_welcome_reply_payload,
)


def _public_clinic_or_404(clinic_slug):
    return get_object_or_404(Clinic, slug=clinic_slug, is_active=True, requires_onboarding=False)


def _client_ip(request):
    return request.META.get("REMOTE_ADDR", "unknown")


def _active_session_or_404(clinic, public_session_id, *, source=None):
    sessions = VoiceSession.objects.select_related("clinic").filter(
        clinic=clinic,
        public_session_id=public_session_id,
        status=VoiceSession.STATUS_ACTIVE,
    )
    if source:
        sessions = sessions.filter(source=source)
    return get_object_or_404(sessions)


def _message_too_long_response(message):
    max_length = getattr(django_settings, "VOICE_TURN_MAX_MESSAGE_LENGTH", 1000)
    if len(message) <= max_length:
        return None
    return JsonResponse({"message": f"Please keep voice messages under {max_length} characters."}, status=400)


def _verify_shared_webhook_secret(request):
    expected_secret = getattr(django_settings, "N8N_WEBHOOK_SECRET", "")
    provided_secret = request.headers.get("X-N8N-Webhook-Secret", "")
    return bool(expected_secret) and constant_time_compare(provided_secret, expected_secret)


@csrf_exempt
@require_POST
def provider_webhook(request):
    if not _verify_shared_webhook_secret(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)
    try:
        json.loads(request.body.decode("utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    return JsonResponse({"received": True})


@require_POST
def widget_session(request, clinic_slug):
    clinic = _public_clinic_or_404(clinic_slug)
    voice_settings = voice_settings_for_clinic(clinic)
    if not voice_settings_enabled(voice_settings):
        return JsonResponse({"message": "Voice assistant is not enabled for this clinic."}, status=403)
    if voice_session_rate_limited(clinic, _client_ip(request)):
        return JsonResponse({"message": VOICE_SESSION_RATE_LIMIT_MESSAGE}, status=429)
    session, voice_settings = create_widget_voice_session(clinic)
    welcome_reply = voice_welcome_reply_payload(voice_settings)
    return JsonResponse({
        "session_id": session.public_session_id,
        "state": session.status,
        "message": welcome_reply.text,
        "provider_payload": welcome_reply.provider_payload,
    })


@require_POST
def widget_turn(request, clinic_slug, public_session_id):
    clinic = _public_clinic_or_404(clinic_slug)
    voice_settings = voice_settings_for_clinic(clinic)
    if not voice_settings_enabled(voice_settings):
        return JsonResponse({"message": "Voice assistant is not enabled for this clinic."}, status=403)
    session = _active_session_or_404(clinic, public_session_id, source=VoiceSession.SOURCE_WIDGET)
    message = (request.POST.get("message") or "").strip()
    too_long = _message_too_long_response(message)
    if too_long:
        return too_long
    if voice_turn_rate_limited(session, _client_ip(request)):
        return JsonResponse({"message": VOICE_RATE_LIMIT_MESSAGE}, status=429)
    reply = handle_voice_turn(session, message)
    return JsonResponse({"message": reply.text, "provider_payload": reply.provider_payload, "state": session.status})


@require_POST
def widget_end(request, clinic_slug, public_session_id):
    clinic = _public_clinic_or_404(clinic_slug)
    session = _active_session_or_404(clinic, public_session_id, source=VoiceSession.SOURCE_WIDGET)
    session.end()
    return JsonResponse({"state": session.STATUS_ENDED})


def _dashboard_clinic_for_voice(request):
    membership = get_active_membership(request.user)
    if not user_can_manage_settings(membership):
        raise PermissionDenied
    return membership.clinic


@login_required
@require_POST
def dashboard_test_session(request):
    clinic = _dashboard_clinic_for_voice(request)
    voice_settings = get_or_create_voice_settings(clinic)
    if not voice_settings.is_test_mode_enabled:
        return JsonResponse({"message": "Dashboard voice tests are disabled for this clinic."}, status=403)
    session, voice_settings = create_dashboard_test_session(clinic)
    welcome_reply = voice_welcome_reply_payload(voice_settings)
    return JsonResponse({
        "session_id": session.public_session_id,
        "state": session.status,
        "message": welcome_reply.text,
        "provider_payload": welcome_reply.provider_payload,
    })


@login_required
@require_POST
def dashboard_test_turn(request, public_session_id):
    clinic = _dashboard_clinic_for_voice(request)
    session = _active_session_or_404(clinic, public_session_id, source=VoiceSession.SOURCE_DASHBOARD_TEST)
    message = (request.POST.get("message") or "").strip()
    too_long = _message_too_long_response(message)
    if too_long:
        return too_long
    if voice_turn_rate_limited(session, request.user.pk):
        return JsonResponse({"message": VOICE_RATE_LIMIT_MESSAGE}, status=429)
    reply = handle_voice_turn(session, message)
    return JsonResponse({"message": reply.text, "provider_payload": reply.provider_payload, "state": session.status})


@login_required
@require_POST
def dashboard_test_end(request, public_session_id):
    clinic = _dashboard_clinic_for_voice(request)
    session = _active_session_or_404(clinic, public_session_id, source=VoiceSession.SOURCE_DASHBOARD_TEST)
    session.end()
    return JsonResponse({"state": session.STATUS_ENDED})
