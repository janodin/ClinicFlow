from django.db import models

from clinics.models import Clinic, TimeStampedModel


class MessengerConnection(TimeStampedModel):
    clinic = models.OneToOneField(Clinic, on_delete=models.CASCADE, related_name="messenger_connection")
    page_id = models.CharField(max_length=64)
    page_access_token = models.CharField(max_length=512)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"MessengerConnection({self.clinic.name} -> {self.page_id})"


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
        unique_together = [("connection", "psid")]

    def reset(self):
        self.state = self.STATE_GREETING
        self.data = {}
        self.save(update_fields=["state", "data", "last_activity_at"])

    def __str__(self):
        return f"MessengerSession({self.psid} -> {self.state})"
