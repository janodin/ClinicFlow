import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.utils import timezone

from appointments.models import Appointment
from clinics.models import Clinic, ClinicGroup


@pytest.fixture
def voice_clinic(db):
    User = get_user_model()
    user = User.objects.create_user(username="voice-owner@example.com", email="voice-owner@example.com", password="password123")
    group = ClinicGroup.objects.create(name="Voice Group", owner=user)
    clinic = Clinic.objects.create(group=group, name="Voice Clinic", slug="voice-clinic")
    return clinic


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
