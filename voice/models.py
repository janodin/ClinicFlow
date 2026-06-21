import secrets

from django.db import models
from django.utils import timezone

from clinics.models import Clinic, TimeStampedModel


def _public_session_id():
    return secrets.token_urlsafe(32)


class VoiceAgentSettings(TimeStampedModel):
    PROVIDER_BROWSER = "browser"
    PROVIDER_VAPI = "vapi"
    PROVIDER_RETELL = "retell"
    PROVIDER_TWILIO_OPENAI = "twilio_openai"
    PROVIDER_CUSTOM = "custom"
    PROVIDER_CHOICES = [
        (PROVIDER_BROWSER, "Browser"),
        (PROVIDER_VAPI, "Vapi"),
        (PROVIDER_RETELL, "Retell"),
        (PROVIDER_TWILIO_OPENAI, "Twilio OpenAI"),
        (PROVIDER_CUSTOM, "Custom"),
    ]

    VOICE_PROFESSIONAL = "professional"
    VOICE_WARM = "warm"
    VOICE_CONCISE = "concise"
    VOICE_CHOICES = [
        (VOICE_PROFESSIONAL, "Professional"),
        (VOICE_WARM, "Warm"),
        (VOICE_CONCISE, "Concise"),
    ]

    EMOTION_MODE_ADAPTIVE = "adaptive"
    EMOTION_MODE_FIXED = "fixed"
    EMOTION_MODE_OFF = "off"
    EMOTION_MODE_CHOICES = [
        (EMOTION_MODE_ADAPTIVE, "Adaptive"),
        (EMOTION_MODE_FIXED, "Fixed"),
        (EMOTION_MODE_OFF, "Off"),
    ]

    EMOTION_INTENSITY_SUBTLE = "subtle"
    EMOTION_INTENSITY_BALANCED = "balanced"
    EMOTION_INTENSITY_EXPRESSIVE = "expressive"
    EMOTION_INTENSITY_CHOICES = [
        (EMOTION_INTENSITY_SUBTLE, "Subtle"),
        (EMOTION_INTENSITY_BALANCED, "Balanced"),
        (EMOTION_INTENSITY_EXPRESSIVE, "Expressive"),
    ]

    EMOTION_NEUTRAL = "neutral"
    EMOTION_WARM = "warm"
    EMOTION_REASSURING = "reassuring"
    EMOTION_CONCISE = "concise"
    EMOTION_CELEBRATORY = "celebratory"
    EMOTION_CHOICES = [
        (EMOTION_NEUTRAL, "Neutral"),
        (EMOTION_WARM, "Warm"),
        (EMOTION_REASSURING, "Reassuring"),
        (EMOTION_CONCISE, "Concise"),
        (EMOTION_CELEBRATORY, "Celebratory"),
    ]

    clinic = models.OneToOneField(Clinic, on_delete=models.CASCADE, related_name="voice_agent_settings")
    is_enabled = models.BooleanField(default=False)
    display_name = models.CharField(max_length=80, default="Voice Assistant")
    voice_label = models.CharField(max_length=32, choices=VOICE_CHOICES, default=VOICE_PROFESSIONAL)
    emotion_mode = models.CharField(max_length=24, choices=EMOTION_MODE_CHOICES, default=EMOTION_MODE_ADAPTIVE)
    emotion_intensity = models.CharField(max_length=24, choices=EMOTION_INTENSITY_CHOICES, default=EMOTION_INTENSITY_BALANCED)
    fixed_emotion = models.CharField(max_length=24, choices=EMOTION_CHOICES, default=EMOTION_WARM)
    welcome_message = models.TextField(default="Hi, I can help with clinic questions and appointments. How can I help?")
    provider = models.CharField(max_length=32, choices=PROVIDER_CHOICES, default=PROVIDER_BROWSER)
    provider_config = models.JSONField(default=dict, blank=True)
    provider_secret_ref = models.CharField(max_length=255, blank=True, default="")
    is_test_mode_enabled = models.BooleanField(default=True)

    @property
    def voice_label_display(self):
        return self.get_voice_label_display()

    @property
    def safe_emotion_mode(self):
        valid_modes = {choice[0] for choice in self.EMOTION_MODE_CHOICES}
        if self.emotion_mode in valid_modes:
            return self.emotion_mode
        return self.EMOTION_MODE_OFF

    @property
    def safe_emotion_intensity(self):
        valid_intensities = {choice[0] for choice in self.EMOTION_INTENSITY_CHOICES}
        if self.emotion_intensity in valid_intensities:
            return self.emotion_intensity
        return self.EMOTION_INTENSITY_BALANCED

    @property
    def safe_fixed_emotion(self):
        valid_emotions = {choice[0] for choice in self.EMOTION_CHOICES}
        if self.fixed_emotion in valid_emotions:
            return self.fixed_emotion
        return self.EMOTION_WARM

    def __str__(self):
        return f"VoiceAgentSettings({self.clinic.name})"


class VoiceSession(TimeStampedModel):
    STATUS_IDLE = "idle"
    STATUS_ACTIVE = "active"
    STATUS_ENDED = "ended"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_IDLE, "Idle"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_ENDED, "Ended"),
        (STATUS_FAILED, "Failed"),
    ]

    SOURCE_WIDGET = "widget"
    SOURCE_DASHBOARD_TEST = "dashboard_test"
    SOURCE_CHOICES = [
        (SOURCE_WIDGET, "Widget"),
        (SOURCE_DASHBOARD_TEST, "Dashboard test"),
    ]

    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="voice_sessions")
    public_session_id = models.CharField(max_length=64, unique=True, default=_public_session_id)
    conversation_id = models.CharField(max_length=80, blank=True, default="")
    provider = models.CharField(max_length=32, default=VoiceAgentSettings.PROVIDER_BROWSER)
    provider_session_id = models.CharField(max_length=120, blank=True, default="")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_IDLE)
    source = models.CharField(max_length=32, choices=SOURCE_CHOICES, default=SOURCE_WIDGET)
    is_test = models.BooleanField(default=False)
    started_at = models.DateTimeField(blank=True, null=True)
    ended_at = models.DateTimeField(blank=True, null=True)
    last_activity_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [models.Index(fields=["clinic", "status", "last_activity_at"])]

    def save(self, *args, **kwargs):
        if not self.conversation_id:
            self.conversation_id = self.public_session_id
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = set(update_fields) | {"conversation_id"}
        super().save(*args, **kwargs)

    def end(self):
        ended_at = timezone.now()
        self.status = self.STATUS_ENDED
        self.ended_at = ended_at
        self.last_activity_at = ended_at
        self.save(update_fields=["status", "ended_at", "last_activity_at", "updated_at"])

    def __str__(self):
        return f"VoiceSession({self.clinic.name} -> {self.status})"


class VoiceTranscriptTurn(TimeStampedModel):
    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"
    ROLE_SYSTEM = "system"
    ROLE_CHOICES = [
        (ROLE_USER, "User"),
        (ROLE_ASSISTANT, "Assistant"),
        (ROLE_SYSTEM, "System"),
    ]

    STATUS_PARTIAL = "partial"
    STATUS_FINAL = "final"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PARTIAL, "Partial"),
        (STATUS_FINAL, "Final"),
        (STATUS_FAILED, "Failed"),
    ]

    session = models.ForeignKey(VoiceSession, on_delete=models.CASCADE, related_name="transcript_turns")
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    text = models.TextField()
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_FINAL)
    provider_event_id = models.CharField(max_length=120, blank=True, default="")
    sequence = models.PositiveIntegerField()

    class Meta:
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(fields=["session", "sequence"], name="unique_voice_transcript_sequence"),
            models.UniqueConstraint(
                fields=["session", "provider_event_id"],
                condition=~models.Q(provider_event_id=""),
                name="unique_voice_transcript_provider_event",
            ),
        ]

    def __str__(self):
        return f"VoiceTranscriptTurn({self.session_id} #{self.sequence} {self.role})"
