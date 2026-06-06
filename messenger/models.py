from django.db import models

from clinics.models import Clinic, TimeStampedModel
from .defaults import DEFAULT_MESSENGER_AI_PROMPT


class MessengerConnection(TimeStampedModel):
    clinic = models.OneToOneField(Clinic, on_delete=models.CASCADE, related_name="messenger_connection")
    app_id = models.CharField(max_length=64, blank=True, default="")
    app_secret = models.CharField(max_length=256, blank=True, default="")
    page_id = models.CharField(max_length=64, blank=True, default="")
    page_name = models.CharField(max_length=255, blank=True, default="")
    page_access_token = models.CharField(max_length=512, blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["page_id"],
                condition=~models.Q(page_id=""),
                name="unique_messenger_connection_page_id",
            ),
        ]

    def __str__(self):
        return f"MessengerConnection({self.clinic.name} -> {self.page_id})"


class MessengerAISettings(TimeStampedModel):
    connection = models.OneToOneField(
        MessengerConnection,
        on_delete=models.CASCADE,
        related_name="ai_settings",
    )
    is_ai_enabled = models.BooleanField(default=True)
    instructions = models.TextField(blank=True, default=DEFAULT_MESSENGER_AI_PROMPT)
    fallback_message = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "Messenger AI Settings"
        verbose_name_plural = "Messenger AI Settings"

    def __str__(self):
        return f"MessengerAISettings({self.connection.clinic.name})"


class MessengerSession(TimeStampedModel):
    STATE_GREETING = "greeting"
    STATE_SELECT_SERVICE = "select_service"
    STATE_SELECT_DATE = "select_date"
    STATE_SELECT_TIME = "select_time"
    STATE_COLLECT_INFO = "collect_info"
    STATE_CONFIRM = "confirm"
    STATE_BOOKED = "booked"
    STATE_FAQ = "faq"
    STATE_CHOICES = [
        (STATE_GREETING, "Greeting"),
        (STATE_SELECT_SERVICE, "Select Service"),
        (STATE_SELECT_DATE, "Select Date"),
        (STATE_SELECT_TIME, "Select Time"),
        (STATE_COLLECT_INFO, "Collect Info"),
        (STATE_CONFIRM, "Confirm"),
        (STATE_BOOKED, "Booked"),
        (STATE_FAQ, "FAQ"),
    ]

    connection = models.ForeignKey(MessengerConnection, on_delete=models.CASCADE, related_name="sessions")
    psid = models.CharField(max_length=64, db_index=True)
    state = models.CharField(max_length=32, choices=STATE_CHOICES, default=STATE_GREETING)
    data = models.JSONField(default=dict, blank=True)
    last_activity_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["connection", "psid"], name="unique_messenger_session_psid"),
        ]

    def reset(self):
        self.state = self.STATE_GREETING
        self.data = {}
        self.save(update_fields=["state", "data", "last_activity_at"])

    def __str__(self):
        return f"MessengerSession({self.psid} -> {self.state})"


class MessengerProcessedMessage(TimeStampedModel):
    connection = models.ForeignKey(MessengerConnection, on_delete=models.CASCADE, related_name="processed_messages")
    psid = models.CharField(max_length=64, db_index=True)
    message_id = models.CharField(max_length=128)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["connection", "psid", "message_id"], name="unique_messenger_processed_message"),
        ]

    def __str__(self):
        return f"MessengerProcessedMessage({self.psid} -> {self.message_id})"
