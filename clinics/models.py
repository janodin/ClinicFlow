import re

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.utils.text import slugify

from messenger.defaults import DEFAULT_AI_FALLBACK_MESSAGE, DEFAULT_MESSENGER_AI_PROMPT


DEFAULT_WIDGET_ACCENT_COLOR = "#06b6d4"
HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
hex_color_validator = RegexValidator(
    regex=HEX_COLOR_RE.pattern,
    message="Enter a valid hex color such as #06b6d4.",
)


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ClinicGroup(TimeStampedModel):
    PLAN_FREE = "free"
    PLAN_STARTER = "starter"
    PLAN_PRO = "professional"
    PLAN_ENTERPRISE = "enterprise"
    PLAN_CHOICES = [
        (PLAN_FREE, "Free"),
        (PLAN_STARTER, "Starter"),
        (PLAN_PRO, "Professional"),
        (PLAN_ENTERPRISE, "Enterprise"),
    ]

    STATUS_TRIAL = "trial"
    STATUS_ACTIVE = "active"
    STATUS_PAST_DUE = "past_due"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_TRIAL, "Trial"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_PAST_DUE, "Past due"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    name = models.CharField(max_length=160)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="owned_clinic_groups")
    plan = models.CharField(max_length=32, choices=PLAN_CHOICES, default=PLAN_FREE)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    trial_ends_at = models.DateTimeField(blank=True, null=True)
    appointment_limit = models.PositiveIntegerField(default=50)
    staff_limit = models.PositiveIntegerField(default=1)

    def __str__(self):
        return self.name


class Clinic(TimeStampedModel):
    APPROVAL_AUTO = "auto_confirm"
    APPROVAL_MANUAL = "manual"
    APPROVAL_CHOICES = [(APPROVAL_AUTO, "Auto confirm"), (APPROVAL_MANUAL, "Manual approval")]

    group = models.ForeignKey(ClinicGroup, on_delete=models.CASCADE, related_name="clinics")
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True)
    logo = models.ImageField(upload_to="clinic-logos/", blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    timezone = models.CharField(max_length=64, default="Asia/Manila")
    default_appointment_duration = models.PositiveIntegerField(default=30)
    booking_approval_mode = models.CharField(max_length=32, choices=APPROVAL_CHOICES, default=APPROVAL_AUTO)
    widget_accent_color = models.CharField(max_length=7, default=DEFAULT_WIDGET_ACCENT_COLOR, validators=[hex_color_validator])
    widget_welcome_message = models.TextField(default="Welcome! How can we help you book an appointment today?")
    widget_behavior_instructions = models.TextField(default="Guide patients through booking smoothly. Always suggest the nearest available slot.")
    requires_onboarding = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    @property
    def safe_widget_accent_color(self):
        value = self.widget_accent_color or DEFAULT_WIDGET_ACCENT_COLOR
        return value if HEX_COLOR_RE.fullmatch(value) else DEFAULT_WIDGET_ACCENT_COLOR


class ClinicAISettingsManager(models.Manager):
    def create_from_messenger_settings(self, messenger_ai_settings):
        settings, _created = self.update_or_create(
            clinic=messenger_ai_settings.connection.clinic,
            defaults={
                "is_ai_enabled": messenger_ai_settings.is_ai_enabled,
                "instructions": messenger_ai_settings.instructions,
                "fallback_message": messenger_ai_settings.fallback_message,
            },
        )
        return settings


class ClinicAISettings(TimeStampedModel):
    MESSENGER_MODE_QUICK_REPLIES = "quick_replies"
    MESSENGER_MODE_AI = "ai"
    MESSENGER_RESPONSE_MODE_CHOICES = [
        (MESSENGER_MODE_QUICK_REPLIES, "Quick replies"),
        (MESSENGER_MODE_AI, "AI mode"),
    ]

    TONE_PROFESSIONAL = "professional"
    TONE_WARM = "warm"
    TONE_EMPATHETIC = "empathetic"
    TONE_CONCISE = "concise"
    TONE_FRIENDLY = "friendly"
    COMMUNICATION_TONE_CHOICES = [
        (TONE_PROFESSIONAL, "Professional"),
        (TONE_WARM, "Warm"),
        (TONE_EMPATHETIC, "Empathetic"),
        (TONE_CONCISE, "Concise"),
        (TONE_FRIENDLY, "Friendly"),
    ]

    clinic = models.OneToOneField(Clinic, on_delete=models.CASCADE, related_name="ai_settings")
    is_ai_enabled = models.BooleanField(default=True)
    messenger_response_mode = models.CharField(
        max_length=24,
        choices=MESSENGER_RESPONSE_MODE_CHOICES,
        default=MESSENGER_MODE_QUICK_REPLIES,
    )
    communication_tone = models.CharField(
        max_length=24,
        choices=COMMUNICATION_TONE_CHOICES,
        default=TONE_PROFESSIONAL,
    )
    custom_tone_instructions = models.TextField(blank=True, default="", max_length=500)
    instructions = models.TextField(blank=True, default=DEFAULT_MESSENGER_AI_PROMPT)
    fallback_message = models.TextField(blank=True, default=DEFAULT_AI_FALLBACK_MESSAGE)

    objects = ClinicAISettingsManager()

    class Meta:
        verbose_name = "Clinic AI Settings"
        verbose_name_plural = "Clinic AI Settings"

    @property
    def safe_messenger_response_mode(self):
        valid_modes = {choice[0] for choice in self.MESSENGER_RESPONSE_MODE_CHOICES}
        if self.messenger_response_mode in valid_modes:
            return self.messenger_response_mode
        return self.MESSENGER_MODE_QUICK_REPLIES

    @property
    def safe_communication_tone(self):
        valid_tones = {choice[0] for choice in self.COMMUNICATION_TONE_CHOICES}
        if self.communication_tone in valid_tones:
            return self.communication_tone
        return self.TONE_PROFESSIONAL

    @property
    def communication_tone_label(self):
        labels = dict(self.COMMUNICATION_TONE_CHOICES)
        return labels[self.safe_communication_tone]

    def __str__(self):
        return f"ClinicAISettings({self.clinic.name})"


class ClinicAIProviderSettings(TimeStampedModel):
    PROVIDER_OPENAI = "openai"
    PROVIDER_OPENAI_COMPATIBLE = "openai_compatible"
    PROVIDER_CHOICES = [
        (PROVIDER_OPENAI, "OpenAI"),
        (PROVIDER_OPENAI_COMPATIBLE, "OpenAI-compatible"),
    ]

    OPENAI_BASE_URL = "https://api.openai.com/v1"
    DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
    OPENAI_MODEL_GPT_4O_MINI = "gpt-4o-mini"
    OPENAI_MODEL_GPT_4O = "gpt-4o"
    OPENAI_MODEL_CHOICES = [
        (OPENAI_MODEL_GPT_4O_MINI, "GPT-4o mini - recommended"),
        (OPENAI_MODEL_GPT_4O, "GPT-4o - higher quality"),
    ]

    clinic = models.OneToOneField(Clinic, on_delete=models.CASCADE, related_name="ai_provider_settings")
    provider = models.CharField(max_length=32, choices=PROVIDER_CHOICES, default=PROVIDER_OPENAI)
    base_url = models.URLField(max_length=255, default=OPENAI_BASE_URL)
    model = models.CharField(max_length=120, default=DEFAULT_OPENAI_MODEL)
    fallback_model = models.CharField(max_length=120, default=DEFAULT_OPENAI_MODEL)
    api_key = models.CharField(max_length=512, blank=True, default="")
    is_enabled = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Clinic AI Provider Settings"
        verbose_name_plural = "Clinic AI Provider Settings"

    @property
    def has_api_key(self):
        return bool((self.api_key or "").strip())

    @property
    def is_configured(self):
        return bool(
            self.is_enabled
            and self.provider in {self.PROVIDER_OPENAI, self.PROVIDER_OPENAI_COMPATIBLE}
            and (self.base_url or "").strip()
            and (self.model or "").strip()
            and (self.fallback_model or "").strip()
            and self.has_api_key
        )

    def __str__(self):
        return f"ClinicAIProviderSettings({self.clinic.name})"


class ClinicMembership(TimeStampedModel):
    ROLE_OWNER = "owner"
    ROLE_STAFF = "staff"
    ROLE_CHOICES = [
        (ROLE_OWNER, "Clinic Admin/Owner"),
        (ROLE_STAFF, "Receptionist/Staff"),
    ]

    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="clinic_memberships")
    role = models.CharField(max_length=24, choices=ROLE_CHOICES)

    class Meta:
        unique_together = [("clinic", "user")]

    def __str__(self):
        return f"{self.user} - {self.clinic} ({self.role})"


class ClinicFAQ(TimeStampedModel):
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="faqs")
    question = models.CharField(max_length=255)
    answer = models.TextField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.question

# Create your models here.
