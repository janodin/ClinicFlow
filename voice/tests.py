from datetime import time, timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment
from clinics.models import Clinic, ClinicAIProviderSettings, ClinicAISettings, ClinicGroup, ClinicMembership
from scheduling.models import ClinicBusinessHour
from scheduling.utils import generate_slots
from services.models import Service


@pytest.fixture
def voice_clinic(db):
    User = get_user_model()
    user = User.objects.create_user(username="voice-owner@example.com", email="voice-owner@example.com", password="password123")
    group = ClinicGroup.objects.create(name="Voice Group", owner=user)
    clinic = Clinic.objects.create(group=group, name="Voice Clinic", slug="voice-clinic")
    return clinic


def _create_voice_clinic(slug, *, is_active=True, requires_onboarding=False):
    User = get_user_model()
    user = User.objects.create_user(username=f"{slug}-owner@example.com", email=f"{slug}-owner@example.com", password="password123")
    group = ClinicGroup.objects.create(name=f"{slug} Group", owner=user)
    clinic = Clinic.objects.create(
        group=group,
        name=f"{slug} Clinic",
        slug=slug,
        is_active=is_active,
        requires_onboarding=requires_onboarding,
    )
    return clinic, user


def _enable_voice(clinic, **overrides):
    from voice.models import VoiceAgentSettings

    defaults = {"is_enabled": True}
    defaults.update(overrides)
    return VoiceAgentSettings.objects.create(clinic=clinic, **defaults)


def _configure_voice_ai(clinic):
    ClinicAISettings.objects.create(clinic=clinic, is_ai_enabled=True)
    ClinicAIProviderSettings.objects.create(
        clinic=clinic,
        provider=ClinicAIProviderSettings.PROVIDER_OPENAI,
        base_url=ClinicAIProviderSettings.OPENAI_BASE_URL,
        model="gpt-test",
        fallback_model="gpt-test",
        api_key="test-key",
    )


@pytest.mark.django_db
def test_voice_agent_settings_defaults(voice_clinic):
    from voice.models import VoiceAgentSettings

    settings = VoiceAgentSettings.objects.create(clinic=voice_clinic)

    assert settings.is_enabled is False
    assert settings.display_name == "Voice Assistant"
    assert settings.voice_label == VoiceAgentSettings.VOICE_PROFESSIONAL
    assert settings.provider == VoiceAgentSettings.PROVIDER_BROWSER
    assert settings.provider_config == {}
    assert settings.provider_secret_ref == ""
    assert settings.is_test_mode_enabled is True
    assert settings.emotion_mode == VoiceAgentSettings.EMOTION_MODE_ADAPTIVE
    assert settings.emotion_intensity == VoiceAgentSettings.EMOTION_INTENSITY_BALANCED
    assert settings.fixed_emotion == VoiceAgentSettings.EMOTION_WARM
    assert settings.safe_emotion_mode == VoiceAgentSettings.EMOTION_MODE_ADAPTIVE
    assert settings.safe_emotion_intensity == VoiceAgentSettings.EMOTION_INTENSITY_BALANCED
    assert settings.safe_fixed_emotion == VoiceAgentSettings.EMOTION_WARM


@pytest.mark.django_db
def test_voice_agent_settings_invalid_emotion_values_fail_closed(voice_clinic):
    from voice.models import VoiceAgentSettings

    settings = VoiceAgentSettings.objects.create(clinic=voice_clinic)
    VoiceAgentSettings.objects.filter(pk=settings.pk).update(
        emotion_mode="unsafe-mode",
        emotion_intensity="unsafe-intensity",
        fixed_emotion="unsafe-emotion",
    )

    settings.refresh_from_db()

    assert settings.safe_emotion_mode == VoiceAgentSettings.EMOTION_MODE_OFF
    assert settings.safe_emotion_intensity == VoiceAgentSettings.EMOTION_INTENSITY_BALANCED
    assert settings.safe_fixed_emotion == VoiceAgentSettings.EMOTION_WARM


def test_voice_emotion_profile_returns_clamped_speech_hints():
    from voice.emotion import voice_emotion_profile
    from voice.models import VoiceAgentSettings

    expected_profiles = [
        (VoiceAgentSettings.EMOTION_NEUTRAL, {"rate": 1.0, "pitch": 1.0}),
        (VoiceAgentSettings.EMOTION_WARM, {"rate": 0.98, "pitch": 1.04}),
        (VoiceAgentSettings.EMOTION_REASSURING, {"rate": 0.92, "pitch": 0.98}),
        (VoiceAgentSettings.EMOTION_CONCISE, {"rate": 1.06, "pitch": 1.0}),
        (VoiceAgentSettings.EMOTION_CELEBRATORY, {"rate": 1.02, "pitch": 1.08}),
    ]

    for emotion, speech in expected_profiles:
        assert voice_emotion_profile(emotion, VoiceAgentSettings.EMOTION_INTENSITY_BALANCED) == {
            "emotion": emotion,
            "emotion_intensity": VoiceAgentSettings.EMOTION_INTENSITY_BALANCED,
            "speech": speech,
        }


def test_voice_emotion_profile_fails_closed_for_invalid_values():
    from voice.emotion import voice_emotion_profile
    from voice.models import VoiceAgentSettings

    profile = voice_emotion_profile("unsafe", "unsafe")

    assert profile == {
        "emotion": VoiceAgentSettings.EMOTION_NEUTRAL,
        "emotion_intensity": VoiceAgentSettings.EMOTION_INTENSITY_BALANCED,
        "speech": {"rate": 1.0, "pitch": 1.0},
    }


def test_browser_voice_adapter_includes_optional_emotion_payload():
    from voice.adapters import BrowserVoiceAdapter
    from voice.models import VoiceAgentSettings

    reply = BrowserVoiceAdapter().reply_payload(
        "Hello patient.",
        emotion_profile={
            "emotion": VoiceAgentSettings.EMOTION_WARM,
            "emotion_intensity": VoiceAgentSettings.EMOTION_INTENSITY_BALANCED,
            "speech": {"rate": 0.98, "pitch": 1.04},
        },
    )

    assert reply.text == "Hello patient."
    assert reply.provider_payload == {
        "type": "browser_speech",
        "text": "Hello patient.",
        "emotion": VoiceAgentSettings.EMOTION_WARM,
        "emotion_intensity": VoiceAgentSettings.EMOTION_INTENSITY_BALANCED,
        "speech": {"rate": 0.98, "pitch": 1.04},
    }


def test_voice_emotion_profile_fails_closed_for_unhashable_invalid_values():
    from voice.emotion import voice_emotion_profile
    from voice.models import VoiceAgentSettings

    profile = voice_emotion_profile([], {})

    assert profile == {
        "emotion": VoiceAgentSettings.EMOTION_NEUTRAL,
        "emotion_intensity": VoiceAgentSettings.EMOTION_INTENSITY_BALANCED,
        "speech": {"rate": 1.0, "pitch": 1.0},
    }


@pytest.mark.django_db
def test_resolve_voice_emotion_uses_mode_and_adaptive_rules(voice_clinic):
    from voice.emotion import resolve_voice_emotion
    from voice.models import VoiceAgentSettings

    settings = VoiceAgentSettings.objects.create(clinic=voice_clinic)

    assert resolve_voice_emotion("I am confused about booking", "", settings) == VoiceAgentSettings.EMOTION_REASSURING
    assert resolve_voice_emotion("What are your clinic hours?", "", settings) == VoiceAgentSettings.EMOTION_CONCISE
    assert resolve_voice_emotion("Yes confirm", "Your Consultation is booked for Monday.", settings) == VoiceAgentSettings.EMOTION_CELEBRATORY
    assert resolve_voice_emotion("Yes confirm", "Your Consultation appointment has been successfully booked for Monday.", settings) == VoiceAgentSettings.EMOTION_CELEBRATORY
    assert resolve_voice_emotion("Cancel my appointment", "Your appointment has been cancelled.", settings) == VoiceAgentSettings.EMOTION_NEUTRAL
    assert resolve_voice_emotion("Hello there", "I can help with appointments.", settings) == VoiceAgentSettings.EMOTION_WARM

    settings.emotion_mode = VoiceAgentSettings.EMOTION_MODE_FIXED
    settings.fixed_emotion = VoiceAgentSettings.EMOTION_REASSURING
    settings.save(update_fields=["emotion_mode", "fixed_emotion", "updated_at"])
    assert resolve_voice_emotion("What are your hours?", "", settings) == VoiceAgentSettings.EMOTION_REASSURING
    assert resolve_voice_emotion("What happened?", "Your appointment has been cancelled under our policy.", settings) == VoiceAgentSettings.EMOTION_NEUTRAL

    settings.emotion_mode = VoiceAgentSettings.EMOTION_MODE_OFF
    settings.save(update_fields=["emotion_mode", "updated_at"])
    assert resolve_voice_emotion("I am confused", "", settings) == VoiceAgentSettings.EMOTION_NEUTRAL


@pytest.mark.django_db
def test_resolve_voice_emotion_uses_reassuring_for_booked_conflicts(voice_clinic):
    from voice.emotion import resolve_voice_emotion
    from voice.models import VoiceAgentSettings

    settings = VoiceAgentSettings.objects.create(clinic=voice_clinic)

    conflict_replies = [
        "That appointment time is already booked.",
        "That appointment time is booked.",
        "Your appointment could not be booked because that time is booked.",
        "Your appointment couldn't be successfully booked for Tuesday.",
        "Your appointment didn't get successfully booked for Tuesday.",
        "Your appointment was unable to be successfully booked.",
        "Your appointment was not successfully booked.",
        "Your appointment wasn't successfully booked.",
        "Your appointment is booked by another patient.",
        "Your requested slot is booked by another patient.",
    ]
    for reply_text in conflict_replies:
        assert resolve_voice_emotion("Can I book?", reply_text, settings) == VoiceAgentSettings.EMOTION_REASSURING


@pytest.mark.django_db
def test_fixed_voice_emotion_keeps_failure_replies_reassuring(voice_clinic):
    from voice.emotion import resolve_voice_emotion
    from voice.models import VoiceAgentSettings

    settings = VoiceAgentSettings.objects.create(
        clinic=voice_clinic,
        emotion_mode=VoiceAgentSettings.EMOTION_MODE_FIXED,
        fixed_emotion=VoiceAgentSettings.EMOTION_CELEBRATORY,
    )

    assert (
        resolve_voice_emotion(
            "Please book this slot",
            "Your appointment couldn't be successfully booked for Tuesday.",
            settings,
        )
        == VoiceAgentSettings.EMOTION_REASSURING
    )


@pytest.mark.django_db
def test_fixed_voice_emotion_keeps_out_of_scope_replies_neutral(voice_clinic):
    from voice.emotion import resolve_voice_emotion
    from voice.models import VoiceAgentSettings

    settings = VoiceAgentSettings.objects.create(
        clinic=voice_clinic,
        emotion_mode=VoiceAgentSettings.EMOTION_MODE_FIXED,
        fixed_emotion=VoiceAgentSettings.EMOTION_CELEBRATORY,
    )

    assert (
        resolve_voice_emotion(
            "How is your system integrated?",
            "I can help with Voice Clinic services, FAQs, and appointments. I don't have information about system integrations or technical implementation.",
            settings,
        )
        == VoiceAgentSettings.EMOTION_NEUTRAL
    )


def test_voice_style_guidance_is_style_only():
    from voice.emotion import voice_style_guidance
    from voice.models import VoiceAgentSettings

    guidance = voice_style_guidance(
        VoiceAgentSettings.EMOTION_REASSURING,
        VoiceAgentSettings.EMOTION_INTENSITY_BALANCED,
    )

    assert "Voice delivery style:" in guidance
    assert "Current emotion: reassuring" in guidance
    assert "Emotion affects wording only" in guidance
    assert "must not override clinic data" in guidance
    assert "appointment confirmation" in guidance


@pytest.mark.django_db
def test_voice_session_and_transcript_are_clinic_scoped_and_ordered(voice_clinic):
    from voice.models import VoiceSession, VoiceTranscriptTurn

    session = VoiceSession.objects.create(
        clinic=voice_clinic,
        source=VoiceSession.SOURCE_WIDGET,
        status=VoiceSession.STATUS_ACTIVE,
        started_at=timezone.now(),
    )
    first = VoiceTranscriptTurn.objects.create(session=session, role=VoiceTranscriptTurn.ROLE_USER, text="Hello", sequence=1)
    second = VoiceTranscriptTurn.objects.create(session=session, role=VoiceTranscriptTurn.ROLE_ASSISTANT, text="Hi", sequence=2)

    assert session.public_session_id
    assert session.conversation_id == session.public_session_id
    assert list(session.transcript_turns.values_list("id", flat=True)) == [first.id, second.id]

    with pytest.raises(IntegrityError):
        VoiceTranscriptTurn.objects.create(session=session, role=VoiceTranscriptTurn.ROLE_USER, text="Duplicate", sequence=1)


def test_appointment_source_includes_voice_widget():
    assert Appointment.SOURCE_VOICE_WIDGET == "voice_widget"
    assert (Appointment.SOURCE_VOICE_WIDGET, "Voice widget") in Appointment.SOURCE_CHOICES


@pytest.mark.django_db
def test_voice_session_create_rejects_disabled_clinic(voice_clinic, client):
    from voice.models import VoiceAgentSettings

    VoiceAgentSettings.objects.create(clinic=voice_clinic, is_enabled=False)

    response = client.post(reverse("voice:widget_session", args=[voice_clinic.slug]))

    assert response.status_code == 403
    assert response.json()["message"] == "Voice assistant is not enabled for this clinic."


@pytest.mark.django_db
def test_voice_session_create_returns_session_for_enabled_clinic(voice_clinic, client):
    from voice.models import VoiceAgentSettings, VoiceSession

    VoiceAgentSettings.objects.create(clinic=voice_clinic, is_enabled=True, welcome_message="Hi from voice.")

    response = client.post(reverse("voice:widget_session", args=[voice_clinic.slug]))

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "Hi from voice."
    assert payload["state"] == "active"
    assert payload["provider_payload"] == {
        "type": "browser_speech",
        "text": "Hi from voice.",
        "emotion": "warm",
        "emotion_intensity": "balanced",
        "speech": {"rate": 0.98, "pitch": 1.04},
    }
    assert VoiceSession.objects.filter(
        clinic=voice_clinic,
        public_session_id=payload["session_id"],
        source=VoiceSession.SOURCE_WIDGET,
    ).exists()


@pytest.mark.django_db
def test_voice_turn_rejects_oversized_message(voice_clinic, client, settings):
    from voice.models import VoiceAgentSettings, VoiceSession

    settings.VOICE_TURN_MAX_MESSAGE_LENGTH = 10
    VoiceAgentSettings.objects.create(clinic=voice_clinic, is_enabled=True)
    session = VoiceSession.objects.create(
        clinic=voice_clinic,
        status=VoiceSession.STATUS_ACTIVE,
        source=VoiceSession.SOURCE_WIDGET,
    )

    response = client.post(
        reverse("voice:widget_turn", args=[voice_clinic.slug, session.public_session_id]),
        {"message": "x" * 11},
    )

    assert response.status_code == 400
    assert response.json()["message"] == "Please keep voice messages under 10 characters."


@pytest.mark.django_db
def test_voice_session_create_returns_404_for_inactive_or_onboarding_clinic(client):
    inactive_clinic, _inactive_user = _create_voice_clinic("inactive-voice", is_active=False)
    onboarding_clinic, _onboarding_user = _create_voice_clinic("onboarding-voice", requires_onboarding=True)
    _enable_voice(inactive_clinic)
    _enable_voice(onboarding_clinic)

    inactive_response = client.post(reverse("voice:widget_session", args=[inactive_clinic.slug]))
    onboarding_response = client.post(reverse("voice:widget_session", args=[onboarding_clinic.slug]))

    assert inactive_response.status_code == 404
    assert onboarding_response.status_code == 404


@pytest.mark.django_db
def test_voice_turn_rejects_session_from_another_clinic(voice_clinic, client):
    from voice.models import VoiceSession

    other_clinic, _other_user = _create_voice_clinic("other-voice")
    _enable_voice(voice_clinic)
    _enable_voice(other_clinic)
    session = VoiceSession.objects.create(
        clinic=other_clinic,
        status=VoiceSession.STATUS_ACTIVE,
        source=VoiceSession.SOURCE_WIDGET,
    )

    response = client.post(
        reverse("voice:widget_turn", args=[voice_clinic.slug, session.public_session_id]),
        {"message": "Hello"},
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_voice_turn_rejects_dashboard_test_source_session(voice_clinic, client):
    from voice.models import VoiceSession

    _enable_voice(voice_clinic)
    session = VoiceSession.objects.create(
        clinic=voice_clinic,
        status=VoiceSession.STATUS_ACTIVE,
        source=VoiceSession.SOURCE_DASHBOARD_TEST,
        is_test=True,
    )

    response = client.post(
        reverse("voice:widget_turn", args=[voice_clinic.slug, session.public_session_id]),
        {"message": "Hello"},
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_handle_voice_turn_sends_latest_prior_history_without_current_message(voice_clinic):
    from voice.models import VoiceSession, VoiceTranscriptTurn
    from voice.services import handle_voice_turn

    session = VoiceSession.objects.create(
        clinic=voice_clinic,
        status=VoiceSession.STATUS_ACTIVE,
        source=VoiceSession.SOURCE_WIDGET,
    )
    prior_turns = []
    for sequence in range(1, 21):
        role = VoiceTranscriptTurn.ROLE_USER if sequence % 2 else VoiceTranscriptTurn.ROLE_ASSISTANT
        prior_turns.append(
            VoiceTranscriptTurn.objects.create(
                session=session,
                role=role,
                text=f"Prior final turn {sequence:02d}",
                sequence=sequence,
            )
        )

    with patch("voice.services.build_gateway_reply", return_value={"reply": "Assistant reply."}) as mock_gateway:
        handle_voice_turn(session, "Current user message")

    payload = mock_gateway.call_args.args[0]
    expected_history = [{"role": turn.role, "content": turn.text} for turn in prior_turns[-16:]]
    assert payload["message"] == "Current user message"
    assert payload["history"] == expected_history
    assert all(turn["content"] != "Current user message" for turn in payload["history"])


@pytest.mark.django_db
def test_handle_voice_turn_sends_style_guidance_to_gateway_and_returns_emotion_payload(voice_clinic):
    from voice.models import VoiceAgentSettings, VoiceSession
    from voice.services import handle_voice_turn

    VoiceAgentSettings.objects.create(
        clinic=voice_clinic,
        emotion_mode=VoiceAgentSettings.EMOTION_MODE_ADAPTIVE,
        emotion_intensity=VoiceAgentSettings.EMOTION_INTENSITY_BALANCED,
    )
    session = VoiceSession.objects.create(
        clinic=voice_clinic,
        status=VoiceSession.STATUS_ACTIVE,
        source=VoiceSession.SOURCE_WIDGET,
    )

    with patch("voice.services.build_gateway_reply", return_value={"reply": "I can help. That slot is not available, but we can find another time."}) as mock_gateway:
        reply = handle_voice_turn(session, "I am confused about booking")

    payload = mock_gateway.call_args.args[0]
    assert payload["voice_style"].startswith("Voice delivery style:")
    assert "Current emotion: reassuring" in payload["voice_style"]
    assert "Emotion affects wording only" in payload["voice_style"]
    assert reply.provider_payload == {
        "type": "browser_speech",
        "text": "I can help. That slot is not available, but we can find another time.",
        "emotion": "reassuring",
        "emotion_intensity": "balanced",
        "speech": {"rate": 0.92, "pitch": 0.98},
    }


@pytest.mark.django_db
def test_handle_voice_turn_does_not_send_celebratory_gateway_style_before_booking_result(voice_clinic):
    from voice.models import VoiceAgentSettings, VoiceSession
    from voice.services import handle_voice_turn

    VoiceAgentSettings.objects.create(
        clinic=voice_clinic,
        emotion_mode=VoiceAgentSettings.EMOTION_MODE_FIXED,
        fixed_emotion=VoiceAgentSettings.EMOTION_CELEBRATORY,
    )
    session = VoiceSession.objects.create(
        clinic=voice_clinic,
        status=VoiceSession.STATUS_ACTIVE,
        source=VoiceSession.SOURCE_WIDGET,
    )

    with patch(
        "voice.services.build_gateway_reply",
        return_value={"reply": "Your appointment couldn't be successfully booked for Tuesday."},
    ) as mock_gateway:
        reply = handle_voice_turn(session, "Please book this slot")

    payload = mock_gateway.call_args.args[0]
    assert "Current emotion: celebratory" not in payload["voice_style"]
    assert "Current emotion: warm" in payload["voice_style"]
    assert reply.provider_payload["emotion"] == VoiceAgentSettings.EMOTION_REASSURING


@pytest.mark.django_db
def test_dashboard_test_session_rejects_staff_member(voice_clinic, client):
    User = get_user_model()
    staff = User.objects.create_user(username="voice-staff@example.com", email="voice-staff@example.com", password="password123")
    ClinicMembership.objects.create(clinic=voice_clinic, user=staff, role=ClinicMembership.ROLE_STAFF)
    _enable_voice(voice_clinic, is_test_mode_enabled=True)
    client.force_login(staff)

    response = client.post(reverse("voice:dashboard_test_session"))

    assert response.status_code == 403


@pytest.mark.django_db
def test_dashboard_voice_test_session_requires_owner(voice_clinic, client):
    from clinics.models import ClinicMembership

    owner = voice_clinic.group.owner
    ClinicMembership.objects.create(clinic=voice_clinic, user=owner, role=ClinicMembership.ROLE_OWNER)
    client.force_login(owner)

    response = client.post(reverse("voice:dashboard_test_session"))

    assert response.status_code == 200
    assert response.json()["state"] == "active"


@pytest.mark.django_db
def test_dashboard_voice_test_page_contains_endpoint_urls(voice_clinic, client):
    from clinics.models import ClinicMembership

    owner = voice_clinic.group.owner
    ClinicMembership.objects.create(clinic=voice_clinic, user=owner, role=ClinicMembership.ROLE_OWNER)
    client.force_login(owner)

    response = client.get(reverse("dashboard:voice_agent"))
    content = response.content.decode()

    assert reverse("voice:dashboard_test_session") in content
    assert "dashboard/test/session/VOICE_SESSION_ID/turn/" in content
    assert "dashboard/test/session/VOICE_SESSION_ID/end/" in content
    assert ':data-lucide="isListening ? \'square\' : \'mic\'"' not in content
    assert 'data-lucide="mic" x-show="!isSpeaking"' in content
    assert 'x-show="isSpeaking"' in content


@pytest.mark.django_db
def test_dashboard_voice_test_page_hardens_live_test_javascript(voice_clinic, client):
    from clinics.models import ClinicMembership

    owner = voice_clinic.group.owner
    ClinicMembership.objects.create(clinic=voice_clinic, user=owner, role=ClinicMembership.ROLE_OWNER)
    client.force_login(owner)

    response = client.get(reverse("dashboard:voice_agent"))
    content = response.content.decode()
    compact_content = " ".join(content.split())
    start_test_start = content.index("async startTestSession()")
    start_test_end = content.index("async toggleListening()", start_test_start)
    start_test_block = content[start_test_start:start_test_end]
    end_test_start = content.index("async endTest()")
    end_test_end = content.index("clearTranscript()", end_test_start)
    end_test_block = content[end_test_start:end_test_end]

    assert "requestVersion: 0" in content
    assert "async responseJson(response)" in content
    assert "return await response.json();" in content
    assert "return {};" in content
    assert content.count("await this.responseJson(response)") >= 3
    assert "const requestVersion = this.requestVersion;" in content
    assert "if (!this.isCurrentRequest(requestVersion, sessionId)) return;" in content
    assert "this.isCurrentRequest(requestVersion, sessionId)" in content
    assert "async endTest() { this.requestVersion += 1;" in compact_content
    assert "clearTranscript() { this.requestVersion += 1;" in compact_content
    assert "this.requestVersion += 1;" in start_test_block
    assert "const requestVersion = this.requestVersion;" in start_test_block
    assert "if (this.requestVersion !== requestVersion) {" in start_test_block
    assert "if (data.session_id) await this.endStaleTestSession(data.session_id);" in start_test_block
    assert start_test_block.index("const requestVersion = this.requestVersion;") < start_test_block.index("await fetch")
    assert start_test_block.index("if (this.requestVersion !== requestVersion) {") < start_test_block.index("this.sessionId = data.session_id;")
    assert "const requestVersion = this.requestVersion;" in end_test_block
    assert "if (!response.ok && this.requestVersion === requestVersion) this.error = data.message || 'Could not end voice test.';" in end_test_block
    assert "if (this.requestVersion === requestVersion) this.error = 'Could not end voice test.';" in end_test_block
    assert "if (this.requestVersion === requestVersion) {" in end_test_block
    assert "!window.speechSynthesis || !window.SpeechSynthesisUtterance || !text" in content
    assert "new window.SpeechSynthesisUtterance(text)" in content


@pytest.mark.django_db
def test_dashboard_voice_test_applies_provider_speech_hints(voice_clinic, client):
    from clinics.models import ClinicMembership

    owner = voice_clinic.group.owner
    ClinicMembership.objects.create(clinic=voice_clinic, user=owner, role=ClinicMembership.ROLE_OWNER)
    client.force_login(owner)

    response = client.get(reverse("dashboard:voice_agent"))
    content = response.content.decode()
    start_block = content[content.index("async startTestSession()"):content.index("async toggleListening()")]
    send_block = content[content.index("async sendTurn(text)"):content.index("speakTestReply(text")]
    speak_block = content[content.index("speakTestReply(text"):content.index("interruptTest()", content.index("speakTestReply(text"))]

    assert "providerPayload" in content
    assert "this.speakTestReply(data.message, data.provider_payload, requestVersion, data.session_id, () => {" in start_block
    assert "this.speakTestReply(data.message, data.provider_payload, requestVersion, sessionId, () => {" in send_block
    assert "speechHintNumber(value, fallback, minimum, maximum)" in content
    assert "applySpeechHints(utterance, providerPayload)" in content
    assert "utterance.rate = this.speechHintNumber(speech.rate, 1, 0.85, 1.12);" in speak_block
    assert "utterance.pitch = this.speechHintNumber(speech.pitch, 1, 0.92, 1.12);" in speak_block


@pytest.mark.django_db
def test_dashboard_voice_test_start_ignores_duplicate_start_and_ends_stale_response(voice_clinic, client):
    from clinics.models import ClinicMembership

    owner = voice_clinic.group.owner
    ClinicMembership.objects.create(clinic=voice_clinic, user=owner, role=ClinicMembership.ROLE_OWNER)
    client.force_login(owner)

    response = client.get(reverse("dashboard:voice_agent"))
    content = response.content.decode()
    start_block = content[content.index("async startTestSession()"):content.index("async toggleListening()")]
    toggle_block = content[content.index("async toggleListening()") : content.index("startTestListening", content.index("async toggleListening()"))]
    end_block = content[content.index("async endTest()") : content.index("clearTranscript()")]
    clear_block = content[content.index("clearTranscript()") : content.index("</script>", content.index("clearTranscript()"))]

    assert "isStarting: false," in content
    assert "if (this.isStarting) return;" in start_block
    assert "this.isStarting = true;" in start_block
    assert "if (data.session_id) await this.endStaleTestSession(data.session_id);" in start_block
    assert "async endStaleTestSession(sessionId) {" in content
    assert "/voice/dashboard/test/session/VOICE_SESSION_ID/end/" in content
    assert "if (this.requestVersion === requestVersion) {" in start_block
    assert "this.isStarting = false;" in start_block
    assert "if (this.isStarting) {" in toggle_block
    assert "this.statusLabel = 'Starting test';" in toggle_block
    assert toggle_block.index("if (this.isStarting) {") < toggle_block.index("if (!this.sessionId) {")
    assert "this.isStarting = false;" in end_block
    assert "this.isStarting = false;" in clear_block


@pytest.mark.django_db
def test_dashboard_voice_test_speaks_welcome_then_auto_listens_and_supports_barge_in(voice_clinic, client):
    from clinics.models import ClinicMembership

    owner = voice_clinic.group.owner
    ClinicMembership.objects.create(clinic=voice_clinic, user=owner, role=ClinicMembership.ROLE_OWNER)
    client.force_login(owner)

    response = client.get(reverse("dashboard:voice_agent"))
    content = response.content.decode()
    start_block = content[content.index("async startTestSession()"):content.index("async toggleListening()")]
    toggle_block = content[content.index("async toggleListening()"):content.index("startTestListening", content.index("async toggleListening()"))]
    listen_block = content[content.index("startTestListening({ auto = false } = {})"):content.index("async sendTurn(text)")]
    send_block = content[content.index("async sendTurn(text)"):content.index("speakTestReply(text")]
    speak_block = content[content.index("speakTestReply(text"):content.index("async endTest()")]
    finish_block = speak_block[speak_block.index("const finishSpeaking = () => {"):speak_block.index("utterance.onend", speak_block.index("const finishSpeaking = () => {"))]
    interrupt_block = content[content.index("interruptTest() {"):content.index("continueTestLoop", content.index("interruptTest() {"))]
    end_block = content[content.index("async endTest()"):content.index("clearTranscript()")]

    assert "isSpeaking: false," in content
    assert "autoListen: false," in content
    assert "bargeInRecognition: null," in content
    assert "currentSpokenText: ''," in content
    assert "this.autoListen = true;" in start_block
    assert "this.speakTestReply(data.message, data.provider_payload, requestVersion, data.session_id, () => {" in start_block
    assert "this.continueTestLoop(requestVersion, data.session_id);" in start_block
    assert "Tap the mic to speak, or end the test." not in content
    assert "Talk to interrupt or tap the mic." in content
    assert "if (this.isProcessing) {" in toggle_block
    assert "if (this.isSpeaking) {" in toggle_block
    assert "this.interruptTest();" in toggle_block
    assert "this.autoListen = true;" in toggle_block
    assert "if (!this.isProcessing && !heardSpeech && this.autoListen) {" in listen_block
    assert "this.speakTestReply(data.message, data.provider_payload, requestVersion, sessionId, () => {" in send_block
    assert "this.continueTestLoop(requestVersion, sessionId);" in send_block
    assert "this.statusLabel = 'Voice error';" in send_block
    assert "if (!this.isSpeaking && !this.error) this.statusLabel = 'Ready to test';" in send_block
    assert "if (!this.isSpeaking) this.statusLabel = 'Ready to test';" not in send_block
    assert "const utterance = new window.SpeechSynthesisUtterance(text);" in speak_block
    assert "this.startBargeInListening(requestVersion, sessionId, text, speechTurnId);" in speak_block
    assert "utterance.onend = finishSpeaking;" in speak_block
    assert "utterance.onerror = finishSpeaking;" in speak_block
    assert finish_block.index("if (!this.isSpeaking) return;") < finish_block.index("if (afterSpeak) afterSpeak();")
    assert "interruptTest()" in content
    assert interrupt_block.index("this.isSpeaking = false;") < interrupt_block.index("window.speechSynthesis.cancel();")
    assert "this.stopBargeInRecognition();" in interrupt_block
    assert "continueTestLoop" in content
    assert "this.autoListen = false;" in end_block
    assert "this.isSpeaking = false;" in end_block
    assert "this.stopBargeInRecognition();" in end_block
    assert "this.error = '';" in end_block


@pytest.mark.django_db
def test_dashboard_voice_test_defines_barge_in_feedback_filters(voice_clinic, client):
    from clinics.models import ClinicMembership

    owner = voice_clinic.group.owner
    ClinicMembership.objects.create(clinic=voice_clinic, user=owner, role=ClinicMembership.ROLE_OWNER)
    client.force_login(owner)

    response = client.get(reverse("dashboard:voice_agent"))
    content = response.content.decode()
    normalize_start = content.index("normalizeVoiceText(text) {")
    normalize_end = content.index("isNoiseVoiceText(text) {", normalize_start)
    normalize_block = content[normalize_start:normalize_end]
    noise_start = content.index("isNoiseVoiceText(text) {")
    noise_end = content.index("isAssistantSelfFeedback(transcript, assistantText) {", noise_start)
    noise_block = content[noise_start:noise_end]
    feedback_start = content.index("isAssistantSelfFeedback(transcript, assistantText) {")
    feedback_end = content.index("isValidBargeInTranscript(transcript, assistantText) {", feedback_start)
    feedback_block = content[feedback_start:feedback_end]
    valid_start = content.index("isValidBargeInTranscript(transcript, assistantText) {")
    valid_end = content.index("stopBargeInRecognition() {", valid_start)
    valid_block = content[valid_start:valid_end]

    assert ".toLowerCase()" in normalize_block
    assert ".replace(/[^a-z0-9\\s]/g, ' ')" in normalize_block
    assert ".replace(/\\s+/g, ' ')" in normalize_block
    assert "const noise = ['uh', 'um', 'er', 'ah', 'hmm'];" in noise_block
    assert "return !normalized || normalized.length < 2 || noise.includes(normalized);" in noise_block
    assert "if (heard === spoken) return true;" in feedback_block
    assert "if (heard.length >= 12 && spoken.includes(heard)) return true;" in feedback_block
    assert "if (heardWords.length >= 3 && spoken.includes(heard)) return true;" in feedback_block
    assert "return !this.isNoiseVoiceText(transcript) && !this.isAssistantSelfFeedback(transcript, assistantText);" in valid_block


@pytest.mark.django_db
def test_dashboard_voice_test_barge_in_recognition_interrupts_speech_and_sends_turn(voice_clinic, client):
    from clinics.models import ClinicMembership

    owner = voice_clinic.group.owner
    ClinicMembership.objects.create(clinic=voice_clinic, user=owner, role=ClinicMembership.ROLE_OWNER)
    client.force_login(owner)

    response = client.get(reverse("dashboard:voice_agent"))
    content = response.content.decode()
    barge_start = content.index("async startBargeInListening")
    barge_end = content.index("async acceptBargeInTurn", barge_start)
    barge_block = content[barge_start:barge_end]
    accept_start = content.index("async acceptBargeInTurn")
    accept_end = content.index("async sendTurn(text)", accept_start)
    accept_block = content[accept_start:accept_end]

    assert "if (!this.autoListen || !this.isSpeaking || this.isProcessing) return;" in barge_block
    assert "this.stopBargeInRecognition();" in barge_block
    assert "let acceptedBargeIn = false;" in barge_block
    assert "let bargeInPermissionDenied = false;" in barge_block
    assert "let bargeInTerminalError = false;" in barge_block
    assert "bargeInStream = await this.selectedMicrophoneStreamForRecognition();" in barge_block
    assert "const blocked = error && (error.name === 'NotAllowedError' || error.name === 'SecurityError');" in barge_block
    assert "this.statusLabel = 'Microphone blocked';" in barge_block
    assert "this.error = 'Microphone access was blocked.';" in barge_block
    assert "this.restartBargeInListening(requestVersion, sessionId, assistantText, speechTurnId);" in barge_block
    assert "acceptedBargeIn = true;" in barge_block
    assert "bargeInPermissionDenied = true;" in barge_block
    assert "recognition.continuous = false;" in barge_block
    assert "recognition.interimResults = true;" in barge_block
    assert "const text = this.recognitionEventText(event);" in barge_block
    assert "this.isValidBargeInTranscript(text, assistantText)" in barge_block
    assert "await this.acceptBargeInTurn(text, requestVersion, sessionId, speechTurnId);" in barge_block
    assert "recognition.start(audioTrack);" in barge_block
    assert "recognition.start();" in barge_block
    assert "this.isSpeaking = false;" in accept_block
    assert "this.stopBargeInRecognition();" in accept_block
    assert "this.stopActiveRecognition();" in accept_block
    assert "window.speechSynthesis.cancel();" in accept_block
    assert "await this.sendTurn(text);" in accept_block


@pytest.mark.django_db
def test_dashboard_voice_test_barge_in_restarts_after_filtered_self_feedback(voice_clinic, client):
    from clinics.models import ClinicMembership

    owner = voice_clinic.group.owner
    ClinicMembership.objects.create(clinic=voice_clinic, user=owner, role=ClinicMembership.ROLE_OWNER)
    client.force_login(owner)

    response = client.get(reverse("dashboard:voice_agent"))
    content = response.content.decode()
    restart_start = content.index("restartBargeInListening(requestVersion, sessionId, assistantText, speechTurnId) {")
    restart_end = content.index("async acceptBargeInTurn", restart_start)
    restart_block = content[restart_start:restart_end]
    barge_start = content.index("async startBargeInListening")
    barge_end = content.index("async acceptBargeInTurn", barge_start)
    barge_block = content[barge_start:barge_end]

    assert "window.setTimeout(() => {" in restart_block
    assert "this.speechTurnId !== speechTurnId" in restart_block
    assert "!this.isSpeaking || this.isProcessing || !this.autoListen" in restart_block
    assert "this.startBargeInListening(requestVersion, sessionId, assistantText, speechTurnId);" in restart_block
    assert "if (!this.isValidBargeInTranscript(text, assistantText)) {" in barge_block
    assert "this.restartBargeInListening(requestVersion, sessionId, assistantText, speechTurnId);" in barge_block
    assert "if (!acceptedBargeIn && !bargeInPermissionDenied && !bargeInTerminalError) {" in barge_block


@pytest.mark.django_db
def test_dashboard_voice_test_barge_in_uses_speech_turn_guard_for_stale_callbacks(voice_clinic, client):
    from clinics.models import ClinicMembership

    owner = voice_clinic.group.owner
    ClinicMembership.objects.create(clinic=voice_clinic, user=owner, role=ClinicMembership.ROLE_OWNER)
    client.force_login(owner)

    response = client.get(reverse("dashboard:voice_agent"))
    content = response.content.decode()
    speak_start = content.index("speakTestReply(text")
    speak_end = content.index("interruptTest()", speak_start)
    speak_block = content[speak_start:speak_end]
    barge_start = content.index("async startBargeInListening")
    barge_end = content.index("async acceptBargeInTurn", barge_start)
    barge_block = content[barge_start:barge_end]
    accept_start = content.index("async acceptBargeInTurn")
    accept_end = content.index("async sendTurn(text)", accept_start)
    accept_block = content[accept_start:accept_end]

    assert "speechTurnId: 0," in content
    assert "this.speechTurnId += 1;" in speak_block
    assert "const speechTurnId = this.speechTurnId;" in speak_block
    assert "this.speechTurnId !== speechTurnId" in speak_block
    assert "this.startBargeInListening(requestVersion, sessionId, text, speechTurnId);" in speak_block
    assert "if (!this.isProcessing && !this.error && this.autoListen) this.statusLabel = 'Ready to test';" in speak_block
    assert "if (!this.isProcessing) this.statusLabel = 'Ready to test';" not in speak_block
    assert "async startBargeInListening(requestVersion, sessionId, assistantText, speechTurnId) {" in barge_block
    assert barge_block.count("this.speechTurnId !== speechTurnId") >= 3
    assert "await this.acceptBargeInTurn(text, requestVersion, sessionId, speechTurnId);" in barge_block
    assert "async acceptBargeInTurn(text, requestVersion, sessionId, speechTurnId) {" in accept_block
    assert "this.speechTurnId !== speechTurnId" in accept_block


@pytest.mark.django_db
def test_dashboard_voice_test_main_recognition_stops_before_sending_turn_and_does_not_mark_ready_while_speaking(voice_clinic, client):
    from clinics.models import ClinicMembership

    owner = voice_clinic.group.owner
    ClinicMembership.objects.create(clinic=voice_clinic, user=owner, role=ClinicMembership.ROLE_OWNER)
    client.force_login(owner)

    response = client.get(reverse("dashboard:voice_agent"))
    content = response.content.decode()
    listen_start = content.index("startTestListening({ auto = false } = {})")
    listen_end = content.index("async startBargeInListening", listen_start)
    listen_block = content[listen_start:listen_end]
    result_start = listen_block.index("recognition.onresult = async (event) => {")
    result_block = listen_block[result_start:listen_block.index("};", result_start)]
    end_start = listen_block.index("recognition.onend = () => {")
    end_block = listen_block[end_start:listen_block.index("};", end_start)]
    schedule_start = content.index("schedulePendingTranscriptTurn(recognition, requestVersion, sessionId, text) {")
    schedule_end = content.index("async startTestListening", schedule_start)
    schedule_block = content[schedule_start:schedule_end]

    assert "if (this.recognition === recognition) this.recognition = null;" in end_block
    assert "if (!this.isProcessing && !this.isSpeaking) this.statusLabel = 'Ready to test';" in end_block
    assert "this.schedulePendingTranscriptTurn(recognition, requestVersion, sessionId, text);" in result_block
    assert "this.isListening = false;" in schedule_block
    assert "if (this.recognition === recognition) this.recognition = null;" in schedule_block
    assert "recognition.onend = null;" in schedule_block
    assert "recognition.onerror = null;" in schedule_block
    assert "recognition.onresult = null;" in schedule_block
    assert "recognition.stop();" in schedule_block
    assert "this.stopRecognitionStream();" in schedule_block
    assert schedule_block.index("recognition.onerror = null;") < schedule_block.index("recognition.stop();")
    assert schedule_block.index("recognition.onresult = null;") < schedule_block.index("recognition.stop();")
    assert schedule_block.index("recognition.stop();") < schedule_block.index("await this.sendTurn(text);")


@pytest.mark.django_db
def test_dashboard_voice_test_main_recognition_waits_for_silence_before_sending_turn(voice_clinic, client):
    from clinics.models import ClinicMembership

    owner = voice_clinic.group.owner
    ClinicMembership.objects.create(clinic=voice_clinic, user=owner, role=ClinicMembership.ROLE_OWNER)
    client.force_login(owner)

    response = client.get(reverse("dashboard:voice_agent"))
    content = response.content.decode()
    listen_start = content.index("startTestListening({ auto = false } = {})")
    listen_end = content.index("async startBargeInListening", listen_start)
    listen_block = content[listen_start:listen_end]
    result_start = listen_block.index("recognition.onresult = async (event) => {")
    result_block = listen_block[result_start:listen_block.index("};", result_start)]
    end_start = listen_block.index("recognition.onend = () => {")
    end_block = listen_block[end_start:listen_block.index("};", end_start)]
    schedule_start = content.find("schedulePendingTranscriptTurn(recognition, requestVersion, sessionId, text) {")
    assert schedule_start != -1
    schedule_end = content.index("async startTestListening", schedule_start)
    schedule_block = content[schedule_start:schedule_end]

    assert "pendingTranscriptText: ''," in content
    assert "pendingTranscriptTimeoutId: null," in content
    assert "turnSilenceDelayMs: 1200," in content
    assert "recognition.continuous = true;" in listen_block
    assert "recognition.interimResults = true;" in listen_block
    assert "const text = this.recognitionEventText(event);" in result_block
    assert "this.schedulePendingTranscriptTurn(recognition, requestVersion, sessionId, text);" in result_block
    assert "await this.sendTurn(text);" not in result_block
    assert end_block.index("if (this.pendingTranscriptTimeoutId) return;") < end_block.index("if (this.recognition === recognition) this.recognition = null;")
    assert "this.pendingTranscriptTimeoutId = window.setTimeout(async () => {" in schedule_block
    assert "this.clearPendingTranscriptTurn();" in schedule_block
    assert "await this.sendTurn(text);" in schedule_block


@pytest.mark.django_db
def test_dashboard_voice_test_barge_in_uses_interim_results_for_fast_interruption(voice_clinic, client):
    from clinics.models import ClinicMembership

    owner = voice_clinic.group.owner
    ClinicMembership.objects.create(clinic=voice_clinic, user=owner, role=ClinicMembership.ROLE_OWNER)
    client.force_login(owner)

    response = client.get(reverse("dashboard:voice_agent"))
    content = response.content.decode()
    barge_start = content.index("async startBargeInListening")
    barge_end = content.index("async acceptBargeInTurn", barge_start)
    barge_block = content[barge_start:barge_end]
    result_start = barge_block.index("recognition.onresult = async (event) => {")
    result_block = barge_block[result_start:barge_block.index("};", result_start)]

    assert "recognition.interimResults = true;" in barge_block
    assert "const text = this.recognitionEventText(event);" in result_block
    assert "const hasFinalResult = this.recognitionEventHasFinalResult(event);" in result_block
    assert "if (hasFinalResult) {" in result_block
    assert result_block.index("if (hasFinalResult) {") < result_block.index("this.restartBargeInListening")
    assert "acceptedBargeIn = true;" in result_block


@pytest.mark.django_db
def test_dashboard_voice_test_auto_no_speech_does_not_show_trouble_hearing_error(voice_clinic, client):
    from clinics.models import ClinicMembership

    owner = voice_clinic.group.owner
    ClinicMembership.objects.create(clinic=voice_clinic, user=owner, role=ClinicMembership.ROLE_OWNER)
    client.force_login(owner)

    response = client.get(reverse("dashboard:voice_agent"))
    content = response.content.decode()
    listen_start = content.index("startTestListening({ auto = false } = {})")
    listen_end = content.index("async sendTurn(text)", listen_start)
    listen_block = content[listen_start:listen_end]

    assert "const recognitionError = event.error || '';" in listen_block
    assert "const recoverableRecognitionError = recognitionError === 'no-speech' || recognitionError === 'aborted';" in listen_block
    recoverable_start = listen_block.index("const recoverableRecognitionError = recognitionError === 'no-speech' || recognitionError === 'aborted';")
    recoverable_block = listen_block[recoverable_start:listen_block.index("const blocked =", recoverable_start)]
    assert "if (recoverableRecognitionError) {" in recoverable_block
    assert "this.isListening = false;" in recoverable_block
    assert "this.autoListen = false;" not in recoverable_block
    assert "this.error = '';" in recoverable_block
    assert "return;" in recoverable_block
    assert "Voice recognition had trouble hearing you. Please try again." not in recoverable_block


@pytest.mark.django_db
def test_dashboard_voice_test_auto_aborted_does_not_show_trouble_hearing_error(voice_clinic, client):
    from clinics.models import ClinicMembership

    owner = voice_clinic.group.owner
    ClinicMembership.objects.create(clinic=voice_clinic, user=owner, role=ClinicMembership.ROLE_OWNER)
    client.force_login(owner)

    response = client.get(reverse("dashboard:voice_agent"))
    content = response.content.decode()
    listen_start = content.index("startTestListening({ auto = false } = {})")
    listen_end = content.index("async sendTurn(text)", listen_start)
    listen_block = content[listen_start:listen_end]

    assert "recognitionError === 'aborted'" in listen_block
    recoverable_block = listen_block[listen_block.index("const recoverableRecognitionError"):listen_block.index("const blocked =", listen_block.index("const recoverableRecognitionError"))]
    assert "if (recoverableRecognitionError) {" in recoverable_block
    assert "this.error = '';" in recoverable_block
    assert "return;" in recoverable_block
    assert "Voice recognition had trouble hearing you. Please try again." not in recoverable_block


@pytest.mark.django_db
def test_dashboard_voice_test_terminal_recognition_errors_do_not_reset_ready_on_end(voice_clinic, client):
    from clinics.models import ClinicMembership

    owner = voice_clinic.group.owner
    ClinicMembership.objects.create(clinic=voice_clinic, user=owner, role=ClinicMembership.ROLE_OWNER)
    client.force_login(owner)

    response = client.get(reverse("dashboard:voice_agent"))
    content = response.content.decode()
    listen_start = content.index("startTestListening({ auto = false } = {})")
    listen_end = content.index("async startBargeInListening", listen_start)
    listen_block = content[listen_start:listen_end]
    error_start = listen_block.index("recognition.onerror = (event) => {")
    error_block = listen_block[error_start:listen_block.index("};", error_start)]
    end_start = listen_block.index("recognition.onend = () => {")
    end_block = listen_block[end_start:listen_block.index("};", end_start)]

    assert "let terminalRecognitionError = false;" in listen_block
    assert "terminalRecognitionError = true;" in error_block
    assert "if (terminalRecognitionError) return;" in end_block
    assert end_block.index("if (terminalRecognitionError) return;") < end_block.index("if (!this.isProcessing && !this.isSpeaking)")


@pytest.mark.django_db
def test_dashboard_voice_test_browser_service_errors_stop_auto_loop_and_use_specific_messages(voice_clinic, client):
    from clinics.models import ClinicMembership

    owner = voice_clinic.group.owner
    ClinicMembership.objects.create(clinic=voice_clinic, user=owner, role=ClinicMembership.ROLE_OWNER)
    client.force_login(owner)

    response = client.get(reverse("dashboard:voice_agent"))
    content = response.content.decode()
    listen_start = content.index("startTestListening({ auto = false } = {})")
    listen_end = content.index("async sendTurn(text)", listen_start)
    listen_block = content[listen_start:listen_end]

    assert "this.autoListen = false;" in listen_block
    assert "if (recognitionError === 'audio-capture') {" in listen_block
    assert "this.error = 'Microphone could not be reached. Check your microphone source and try again.';" in listen_block
    assert "if (recognitionError === 'network') {" in listen_block
    assert "this.error = 'Browser voice recognition service is unavailable. Check your connection and try again.';" in listen_block
    assert "if (recognitionError === 'language-not-supported') {" in listen_block
    assert "this.error = 'This browser does not support the selected voice language.';" in listen_block
    assert listen_block.index("if (recognitionError === 'audio-capture') {") < listen_block.index("Voice recognition had trouble hearing you. Please try again.")
    assert listen_block.index("if (recognitionError === 'network') {") < listen_block.index("Voice recognition had trouble hearing you. Please try again.")


@pytest.mark.django_db
def test_dashboard_voice_selected_microphone_stream_is_used_for_recognition(voice_clinic, client):
    from clinics.models import ClinicMembership

    owner = voice_clinic.group.owner
    ClinicMembership.objects.create(clinic=voice_clinic, user=owner, role=ClinicMembership.ROLE_OWNER)
    client.force_login(owner)

    response = client.get(reverse("dashboard:voice_agent"))
    content = response.content.decode()
    listen_start = content.index("startTestListening({ auto = false } = {})")
    listen_end = content.index("async sendTurn(text)", listen_start)
    listen_block = content[listen_start:listen_end]
    end_block = content[content.index("async endTest()"):content.index("clearTranscript()")]
    clear_block = content[content.index("clearTranscript()") : content.index("</script>", content.index("clearTranscript()"))]

    assert "recognitionStream: null," in content
    assert "selectedMicrophoneStreamForRecognition()" in content
    assert "recognitionStream = await this.selectedMicrophoneStreamForRecognition();" in listen_block
    assert "const audioTrack = recognitionStream ? recognitionStream.getAudioTracks()[0] : null;" in listen_block
    assert "this.recognitionStream = recognitionStream;" in listen_block
    assert "recognition.start(audioTrack);" in listen_block
    assert "recognition.start();" in listen_block
    assert "const micReady = await this.activateSelectedMicrophone();" not in listen_block
    assert "this.stopRecognitionStream();" in listen_block
    assert "this.stopRecognitionStream();" in end_block
    assert "this.stopRecognitionStream();" in clear_block


@pytest.mark.django_db
def test_dashboard_voice_test_clear_transcript_stops_audio_and_recognition(voice_clinic, client):
    from clinics.models import ClinicMembership

    owner = voice_clinic.group.owner
    ClinicMembership.objects.create(clinic=voice_clinic, user=owner, role=ClinicMembership.ROLE_OWNER)
    client.force_login(owner)

    response = client.get(reverse("dashboard:voice_agent"))
    content = response.content.decode()
    clear_start = content.index("clearTranscript()")
    clear_block = content[clear_start:content.index("</script>", clear_start)]

    assert "this.requestVersion += 1;" in clear_block
    assert "this.autoListen = false;" in clear_block
    assert "this.stopBargeInRecognition();" in clear_block
    assert "this.currentSpokenText = '';" in clear_block
    assert "this.stopTimer();" in clear_block
    assert "this.elapsedSeconds = 0;" in clear_block
    assert "this.error = '';" in clear_block
    assert "const recognition = this.recognition;" in clear_block
    assert "this.recognition = null;" in clear_block
    assert "recognition.onstart = null;" in clear_block
    assert "recognition.onerror = null;" in clear_block
    assert "recognition.onend = null;" in clear_block
    assert "recognition.onresult = null;" in clear_block
    assert "recognition.stop();" in clear_block
    assert "this.isSpeaking = false;" in clear_block
    assert "window.speechSynthesis.cancel();" in clear_block
    assert clear_block.index("this.isSpeaking = false;") < clear_block.index("window.speechSynthesis.cancel();")
    assert "this.isListening = false;" in clear_block
    assert "this.isProcessing = false;" in clear_block


@pytest.mark.django_db
def test_dashboard_voice_test_page_uses_animated_voice_orb(voice_clinic, client):
    from clinics.models import ClinicMembership

    owner = voice_clinic.group.owner
    ClinicMembership.objects.create(clinic=voice_clinic, user=owner, role=ClinicMembership.ROLE_OWNER)
    client.force_login(owner)

    response = client.get(reverse("dashboard:voice_agent"))
    content = response.content.decode()
    orb_start = content.index("voice-orb")
    orb_end = content.index("</button>", orb_start)
    orb_block = content[orb_start:orb_end]

    assert "voice-orb" in orb_block
    assert "voice-orb-listening" in orb_block
    assert "voice-orb-speaking" in orb_block
    assert "voice-orb-thinking" in orb_block
    assert "voice-orb-bars" in orb_block
    assert 'data-lucide="mic" x-show="!isSpeaking"' in orb_block
    assert 'x-show="isSpeaking"' in orb_block
    assert ":data-lucide" not in orb_block


@pytest.mark.django_db
def test_dashboard_test_session_rejects_when_test_mode_disabled(voice_clinic, client):
    owner = voice_clinic.group.owner
    ClinicMembership.objects.create(clinic=voice_clinic, user=owner, role=ClinicMembership.ROLE_OWNER)
    _enable_voice(voice_clinic, is_test_mode_enabled=False)
    client.force_login(owner)

    response = client.post(reverse("voice:dashboard_test_session"))

    assert response.status_code == 403
    assert response.json()["message"] == "Dashboard voice tests are disabled for this clinic."


@pytest.mark.django_db
def test_dashboard_test_session_creates_test_session_for_owner(voice_clinic, client):
    from voice.models import VoiceSession

    owner = voice_clinic.group.owner
    ClinicMembership.objects.create(clinic=voice_clinic, user=owner, role=ClinicMembership.ROLE_OWNER)
    _enable_voice(voice_clinic, is_test_mode_enabled=True, welcome_message="Owner test welcome.")
    client.force_login(owner)

    response = client.post(reverse("voice:dashboard_test_session"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"]
    assert payload["state"] == VoiceSession.STATUS_ACTIVE
    assert payload["message"] == "Owner test welcome."
    assert payload["provider_payload"] == {
        "type": "browser_speech",
        "text": "Owner test welcome.",
        "emotion": "warm",
        "emotion_intensity": "balanced",
        "speech": {"rate": 0.98, "pitch": 1.04},
    }
    assert VoiceSession.objects.filter(
        clinic=voice_clinic,
        public_session_id=payload["session_id"],
        source=VoiceSession.SOURCE_DASHBOARD_TEST,
        is_test=True,
    ).exists()


@pytest.mark.django_db
def test_dashboard_test_session_requires_login_without_mutation(voice_clinic, client):
    from voice.models import VoiceSession

    _enable_voice(voice_clinic, is_test_mode_enabled=True)

    response = client.post(reverse("voice:dashboard_test_session"))

    assert response.status_code == 302
    assert reverse("accounts:login") in response["Location"]
    assert not VoiceSession.objects.filter(clinic=voice_clinic, source=VoiceSession.SOURCE_DASHBOARD_TEST).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("endpoint_name", ["dashboard_test_turn", "dashboard_test_end"])
def test_dashboard_test_turn_and_end_require_login_without_mutation(voice_clinic, client, endpoint_name):
    from voice.models import VoiceSession, VoiceTranscriptTurn

    session = VoiceSession.objects.create(
        clinic=voice_clinic,
        status=VoiceSession.STATUS_ACTIVE,
        source=VoiceSession.SOURCE_DASHBOARD_TEST,
        is_test=True,
    )

    response = client.post(reverse(f"voice:{endpoint_name}", args=[session.public_session_id]), {"message": "Hello"})

    assert response.status_code == 302
    assert reverse("accounts:login") in response["Location"]
    session.refresh_from_db()
    assert session.status == VoiceSession.STATUS_ACTIVE
    assert not VoiceTranscriptTurn.objects.filter(session=session).exists()


@pytest.mark.django_db
def test_dashboard_test_turn_returns_reply_for_owner_and_records_transcript(voice_clinic, client):
    from voice.models import VoiceSession, VoiceTranscriptTurn

    cache.clear()
    owner = voice_clinic.group.owner
    ClinicMembership.objects.create(clinic=voice_clinic, user=owner, role=ClinicMembership.ROLE_OWNER)
    session = VoiceSession.objects.create(
        clinic=voice_clinic,
        status=VoiceSession.STATUS_ACTIVE,
        source=VoiceSession.SOURCE_DASHBOARD_TEST,
        is_test=True,
    )
    client.force_login(owner)

    with patch("voice.services.build_gateway_reply", return_value={"reply": "Dashboard voice reply."}):
        response = client.post(
            reverse("voice:dashboard_test_turn", args=[session.public_session_id]),
            {"message": "Can I book?"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "Dashboard voice reply."
    assert payload["provider_payload"] == {
        "type": "browser_speech",
        "text": "Dashboard voice reply.",
        "emotion": "warm",
        "emotion_intensity": "balanced",
        "speech": {"rate": 0.98, "pitch": 1.04},
    }
    assert payload["state"] == VoiceSession.STATUS_ACTIVE
    assert list(session.transcript_turns.values_list("role", "text")) == [
        (VoiceTranscriptTurn.ROLE_USER, "Can I book?"),
        (VoiceTranscriptTurn.ROLE_ASSISTANT, "Dashboard voice reply."),
    ]


@pytest.mark.django_db
def test_dashboard_test_end_ends_session_for_owner(voice_clinic, client):
    from voice.models import VoiceSession

    owner = voice_clinic.group.owner
    ClinicMembership.objects.create(clinic=voice_clinic, user=owner, role=ClinicMembership.ROLE_OWNER)
    session = VoiceSession.objects.create(
        clinic=voice_clinic,
        status=VoiceSession.STATUS_ACTIVE,
        source=VoiceSession.SOURCE_DASHBOARD_TEST,
        is_test=True,
    )
    client.force_login(owner)

    response = client.post(reverse("voice:dashboard_test_end", args=[session.public_session_id]))

    assert response.status_code == 200
    assert response.json()["state"] == VoiceSession.STATUS_ENDED
    session.refresh_from_db()
    assert session.status == VoiceSession.STATUS_ENDED


@pytest.mark.django_db
def test_voice_turn_rate_limit_uses_atomic_cache_increment(voice_clinic, settings, monkeypatch):
    from voice.models import VoiceSession
    from voice.services import voice_turn_rate_limited

    class RaceyCache:
        def __init__(self):
            self.value = None

        def add(self, key, value, timeout=None):
            if self.value is None:
                self.value = value
                return True
            return False

        def incr(self, key):
            if self.value is None:
                raise ValueError
            self.value += 1
            return self.value

        def get(self, key, default=None):
            return 0

        def set(self, key, value, timeout=None):
            return True

    settings.VOICE_TURN_RATE_LIMIT = 1
    session = VoiceSession.objects.create(
        clinic=voice_clinic,
        status=VoiceSession.STATUS_ACTIVE,
        source=VoiceSession.SOURCE_WIDGET,
    )
    monkeypatch.setattr("voice.services.cache", RaceyCache())

    assert voice_turn_rate_limited(session, "actor") is False
    assert voice_turn_rate_limited(session, "actor") is True


@pytest.mark.django_db
def test_voice_turn_rate_limit_returns_429_on_n_plus_one(voice_clinic, client, settings):
    from voice.models import VoiceSession

    cache.clear()
    settings.VOICE_TURN_RATE_LIMIT = 1
    _enable_voice(voice_clinic)
    session = VoiceSession.objects.create(
        clinic=voice_clinic,
        status=VoiceSession.STATUS_ACTIVE,
        source=VoiceSession.SOURCE_WIDGET,
    )

    with patch("voice.services.build_gateway_reply", return_value={"reply": "Voice reply"}):
        first_response = client.post(
            reverse("voice:widget_turn", args=[voice_clinic.slug, session.public_session_id]),
            {"message": "Hello"},
        )
        second_response = client.post(
            reverse("voice:widget_turn", args=[voice_clinic.slug, session.public_session_id]),
            {"message": "Hello again"},
        )

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert second_response.json()["message"] == "Too many voice messages. Please wait before trying again."


@pytest.mark.django_db
def test_voice_session_create_rate_limit_returns_429_on_n_plus_one(voice_clinic, client, settings):
    cache.clear()
    settings.VOICE_SESSION_RATE_LIMIT = 1
    _enable_voice(voice_clinic)

    first_response = client.post(reverse("voice:widget_session", args=[voice_clinic.slug]))
    second_response = client.post(reverse("voice:widget_session", args=[voice_clinic.slug]))

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert second_response.json()["message"] == "Too many voice sessions. Please wait before trying again."


@pytest.mark.django_db
def test_voice_session_create_rate_limit_is_scoped_per_clinic(voice_clinic, client, settings):
    cache.clear()
    settings.VOICE_SESSION_RATE_LIMIT = 1
    other_clinic, _other_user = _create_voice_clinic("session-other-voice")
    _enable_voice(voice_clinic)
    _enable_voice(other_clinic)

    first_response = client.post(reverse("voice:widget_session", args=[voice_clinic.slug]))
    other_response = client.post(reverse("voice:widget_session", args=[other_clinic.slug]))

    assert first_response.status_code == 200
    assert other_response.status_code == 200


@pytest.mark.django_db
def test_voice_turn_non_empty_message_returns_fallback_reply(voice_clinic, client):
    from voice.models import VoiceSession

    _enable_voice(voice_clinic)
    ClinicAISettings.objects.create(clinic=voice_clinic, fallback_message="Fallback voice reply.")
    session = VoiceSession.objects.create(
        clinic=voice_clinic,
        status=VoiceSession.STATUS_ACTIVE,
        source=VoiceSession.SOURCE_WIDGET,
    )

    with patch("voice.services.build_gateway_reply", return_value={}):
        response = client.post(
            reverse("voice:widget_turn", args=[voice_clinic.slug, session.public_session_id]),
            {"message": "Can I book?"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "Fallback voice reply."
    assert payload["provider_payload"] == {
        "type": "browser_speech",
        "text": "Fallback voice reply.",
        "emotion": "warm",
        "emotion_intensity": "balanced",
        "speech": {"rate": 0.98, "pitch": 1.04},
    }


@pytest.mark.django_db
@patch("messenger.ai_gateway.call_chat_completion")
def test_voice_gateway_uses_voice_channel_and_clinic_context(mock_completion, voice_clinic):
    from messenger.ai_gateway import build_gateway_reply

    _configure_voice_ai(voice_clinic)
    Service.objects.create(clinic=voice_clinic, name="Consultation", duration_minutes=30)
    mock_completion.return_value = {"content": "We offer Consultation.", "tool_calls": []}

    response = build_gateway_reply({"channel": "voice", "clinic_slug": voice_clinic.slug, "message": "What services do you offer?", "history": []})

    assert response["reply"] == "We offer Consultation."
    messages = mock_completion.call_args.args[1]
    assert any('"channel": "voice"' in message["content"] for message in messages if message["role"] == "system")


@pytest.mark.django_db
@patch("messenger.ai_gateway.call_chat_completion")
def test_voice_gateway_booking_records_voice_widget_source(mock_completion, voice_clinic):
    from appointments.models import Appointment
    from messenger.ai_gateway import build_gateway_reply

    _configure_voice_ai(voice_clinic)
    service = Service.objects.create(clinic=voice_clinic, name="Consultation", duration_minutes=30)
    target_date = timezone.localdate() + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=voice_clinic, weekday=target_date.weekday(), is_open=True, open_time=time(9), close_time=time(17))
    slot = generate_slots(voice_clinic, service, target_date)[0]
    date_label = f"{target_date.strftime('%B')} {target_date.day}"
    summary = "Please confirm booking service Consultation date " + date_label + " time " + slot["label"] + " full name Voice Patient phone 09170000000 email voice@example.com."
    mock_completion.side_effect = [
        {"content": "", "tool_calls": [{"id": "call-1", "function": {"name": "book_confirmed_appointment", "arguments": {
            "service_id": service.id,
            "starts_at": slot["starts_at"].isoformat(),
            "full_name": "Voice Patient",
            "phone": "09170000000",
            "email": "voice@example.com",
            "confirmed": True,
        }}}]},
        {"content": "Booked by voice.", "tool_calls": []},
    ]

    response = build_gateway_reply({
        "channel": "voice",
        "clinic_slug": voice_clinic.slug,
        "message": "Yes, confirm.",
        "history": [{"role": "assistant", "content": summary}],
    })

    assert response["reply"].startswith("Your Consultation is booked")
    assert "Reference code:" in response["reply"]
    appointment = Appointment.objects.get(clinic=voice_clinic, patient__full_name="Voice Patient")
    assert appointment.source == Appointment.SOURCE_VOICE_WIDGET
    assert mock_completion.call_count == 1


@pytest.mark.django_db
def test_voice_provider_webhook_rejects_missing_secret(voice_clinic, client, settings):
    settings.N8N_WEBHOOK_SECRET = "strong-secret"

    response = client.post(reverse("voice:provider_webhook"), data='{"event":"transcript"}', content_type="application/json")

    assert response.status_code == 401
    assert response.json()["error"] == "Unauthorized"


@pytest.mark.django_db
def test_voice_provider_webhook_accepts_authenticated_noop(voice_clinic, client, settings):
    settings.N8N_WEBHOOK_SECRET = "strong-secret"

    response = client.post(
        reverse("voice:provider_webhook"),
        data='{"event":"transcript"}',
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="strong-secret",
    )

    assert response.status_code == 200
    assert response.json() == {"received": True}


@pytest.mark.django_db
def test_voice_provider_webhook_rejects_wrong_secret(voice_clinic, client, settings):
    settings.N8N_WEBHOOK_SECRET = "dummy-secret"

    response = client.post(
        reverse("voice:provider_webhook"),
        data='{"event":"transcript"}',
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="wrong-secret",
    )

    assert response.status_code == 401
    assert response.json() == {"error": "Unauthorized"}


@pytest.mark.django_db
def test_voice_provider_webhook_fails_closed_when_secret_unconfigured(voice_clinic, client, settings):
    settings.N8N_WEBHOOK_SECRET = ""

    response = client.post(
        reverse("voice:provider_webhook"),
        data='{"event":"transcript"}',
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="dummy-secret",
    )

    assert response.status_code == 401
    assert response.json() == {"error": "Unauthorized"}


@pytest.mark.django_db
def test_voice_provider_webhook_rejects_authenticated_invalid_json(voice_clinic, client, settings):
    settings.N8N_WEBHOOK_SECRET = "dummy-secret"

    response = client.post(
        reverse("voice:provider_webhook"),
        data="{not-json",
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="dummy-secret",
    )

    assert response.status_code == 400
    assert response.json() == {"error": "Invalid JSON"}


@pytest.mark.django_db
def test_voice_provider_webhook_rejects_unauthenticated_malformed_json_before_parsing(voice_clinic, client, settings):
    settings.N8N_WEBHOOK_SECRET = "dummy-secret"

    response = client.post(reverse("voice:provider_webhook"), data="{not-json", content_type="application/json")

    assert response.status_code == 401
    assert response.json() == {"error": "Unauthorized"}


@pytest.mark.django_db
def test_voice_provider_webhook_accepts_authenticated_empty_body(voice_clinic, client, settings):
    settings.N8N_WEBHOOK_SECRET = "dummy-secret"

    response = client.post(
        reverse("voice:provider_webhook"),
        data="",
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="dummy-secret",
    )

    assert response.status_code == 200
    assert response.json() == {"received": True}


@pytest.mark.django_db
def test_voice_provider_webhook_rejects_get(voice_clinic, client, settings):
    settings.N8N_WEBHOOK_SECRET = "dummy-secret"

    response = client.get(reverse("voice:provider_webhook"), HTTP_X_N8N_WEBHOOK_SECRET="dummy-secret")

    assert response.status_code == 405
