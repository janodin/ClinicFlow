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


class MessengerConversation(TimeStampedModel):
    connection = models.ForeignKey(MessengerConnection, on_delete=models.CASCADE, related_name="ai_conversations")
    psid = models.CharField(max_length=64, db_index=True)
    last_sequence = models.PositiveIntegerField(default=0)
    completed_sequence = models.PositiveIntegerField(default=0)
    active_turn_token = models.CharField(max_length=64, blank=True, default="")
    active_input_sequence = models.PositiveIntegerField(default=0)
    history = models.JSONField(default=list, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["connection", "psid"], name="unique_messenger_ai_conversation_psid"),
        ]

    def __str__(self):
        return f"MessengerConversation({self.psid} -> {self.last_sequence}/{self.completed_sequence})"


class MessengerInboundMessage(TimeStampedModel):
    conversation = models.ForeignKey(MessengerConversation, on_delete=models.CASCADE, related_name="inbound_messages")
    message_id = models.CharField(max_length=128, blank=True, default="")
    sequence = models.PositiveIntegerField()
    text = models.TextField(blank=True, default="")
    postback = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(fields=["conversation", "sequence"], name="unique_messenger_inbound_sequence"),
            models.UniqueConstraint(
                fields=["conversation", "message_id"],
                condition=~models.Q(message_id=""),
                name="unique_messenger_inbound_message_id",
            ),
        ]

    def __str__(self):
        return f"MessengerInboundMessage({self.conversation_id} #{self.sequence})"


class MessengerAITurn(TimeStampedModel):
    STATUS_ACTIVE = "active"
    STATUS_CLAIMED = "claimed"
    STATUS_SENDING = "sending"
    STATUS_SUPERSEDED = "superseded"
    STATUS_COMPLETED = "completed"
    STATUS_STALE = "stale"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_CLAIMED, "Claimed"),
        (STATUS_SENDING, "Sending"),
        (STATUS_SUPERSEDED, "Superseded"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_STALE, "Stale"),
    ]

    conversation = models.ForeignKey(MessengerConversation, on_delete=models.CASCADE, related_name="ai_turns")
    token = models.CharField(max_length=64, unique=True)
    input_sequence = models.PositiveIntegerField()
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    reply_text = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"MessengerAITurn({self.conversation_id} #{self.input_sequence} {self.status})"


class MessengerOutboundMessage(TimeStampedModel):
    STATUS_PENDING = "pending"
    STATUS_SENDING = "sending"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUS_UNKNOWN = "unknown"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_SENDING, "Sending"),
        (STATUS_SENT, "Sent"),
        (STATUS_FAILED, "Failed"),
        (STATUS_UNKNOWN, "Delivery Unknown"),
    ]

    turn = models.ForeignKey(MessengerAITurn, on_delete=models.CASCADE, related_name="outbound_messages")
    body_index = models.PositiveIntegerField()
    body_hash = models.CharField(max_length=64)
    body = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["body_index"]
        constraints = [
            models.UniqueConstraint(fields=["turn", "body_index"], name="unique_messenger_outbound_turn_body"),
        ]

    def __str__(self):
        return f"MessengerOutboundMessage({self.turn_id} #{self.body_index} {self.status})"
