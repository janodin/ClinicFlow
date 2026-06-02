import secrets
import string

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from clinics.models import Clinic, TimeStampedModel


class Appointment(TimeStampedModel):
    STATUS_PENDING = "pending"
    STATUS_CONFIRMED = "confirmed"
    STATUS_CANCELLED = "cancelled"
    STATUS_COMPLETED = "completed"
    STATUS_NO_SHOW = "no_show"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Booked"),
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_NO_SHOW, "No Show"),
    ]

    PAYMENT_UNPAID = "unpaid"
    PAYMENT_PAID_AT_CLINIC = "paid_at_clinic"
    PAYMENT_RESERVED = "reserved"
    PAYMENT_CHOICES = [
        (PAYMENT_UNPAID, "Unpaid"),
        (PAYMENT_PAID_AT_CLINIC, "Paid at clinic"),
        (PAYMENT_RESERVED, "Reserved"),
    ]

    SOURCE_DIRECT = "direct"
    SOURCE_EMBED = "embed"
    SOURCE_CHAT_WIDGET = "chat_widget"
    SOURCE_STAFF = "staff"
    SOURCE_WALK_IN = "walk_in"
    SOURCE_PHONE = "phone"
    SOURCE_MESSENGER = "messenger"
    SOURCE_CHOICES = [
        (SOURCE_DIRECT, "Direct booking"),
        (SOURCE_EMBED, "Embed"),
        (SOURCE_CHAT_WIDGET, "Chat widget"),
        (SOURCE_STAFF, "Staff"),
        (SOURCE_WALK_IN, "Walk-in"),
        (SOURCE_PHONE, "Phone"),
        (SOURCE_MESSENGER, "Messenger"),
    ]

    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="appointments")
    patient = models.ForeignKey("patients.Patient", on_delete=models.PROTECT, related_name="appointments")
    service = models.ForeignKey("services.Service", on_delete=models.PROTECT, related_name="appointments")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_PENDING)
    payment_state = models.CharField(max_length=32, choices=PAYMENT_CHOICES, default=PAYMENT_UNPAID)
    source = models.CharField(max_length=32, choices=SOURCE_CHOICES, default=SOURCE_DIRECT)
    messenger_psid = models.CharField(max_length=64, blank=True)
    messenger_reminder_24h_sent_at = models.DateTimeField(blank=True, null=True)
    messenger_reminder_1h_sent_at = models.DateTimeField(blank=True, null=True)
    reason = models.TextField(blank=True)
    cancellation_reason = models.TextField(blank=True)
    reference_code = models.CharField(max_length=16, unique=True, blank=True)

    class Meta:
        ordering = ["starts_at"]
        indexes = [models.Index(fields=["clinic", "starts_at"])]

    VALID_TRANSITIONS = {
        STATUS_PENDING: [STATUS_CONFIRMED, STATUS_CANCELLED],
        STATUS_CONFIRMED: [STATUS_COMPLETED, STATUS_CANCELLED, STATUS_NO_SHOW, STATUS_PENDING],
        STATUS_NO_SHOW: [STATUS_CONFIRMED, STATUS_PENDING],
        STATUS_COMPLETED: [],
        STATUS_CANCELLED: [STATUS_PENDING],
    }

    def can_transition_to(self, new_status):
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])

    def clean(self):
        errors = {}
        if self.clinic_id and self.patient_id and self.patient.clinic_id != self.clinic_id:
            errors["patient"] = "Patient must belong to the appointment clinic."
        if self.clinic_id and self.service_id and self.service.clinic_id != self.clinic_id:
            errors["service"] = "Service must belong to the appointment clinic."
        if self.starts_at and self.ends_at and self.starts_at >= self.ends_at:
            errors["ends_at"] = "Appointment end time must be after start time."
        if errors:
            raise ValidationError(errors)
        if not self.clinic_id:
            return
        overlaps = Appointment.objects.filter(
            clinic=self.clinic,
            starts_at__lt=self.ends_at,
            ends_at__gt=self.starts_at,
        ).exclude(status=self.STATUS_CANCELLED)
        if self.pk:
            overlaps = overlaps.exclude(pk=self.pk)
        if overlaps.exists():
            raise ValidationError("This clinic already has an appointment at that time.")

    def _generate_reference_code(self):
        while True:
            code = "CF-" + "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
            if not Appointment.objects.filter(reference_code=code).exists():
                return code

    def save(self, *args, **kwargs):
        if not self.reference_code:
            self.reference_code = self._generate_reference_code()
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.patient} - {self.service} at {self.starts_at}"


class AppointmentNote(TimeStampedModel):
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True)
    body = models.TextField()
    is_internal = models.BooleanField(default=True)

    def __str__(self):
        return f"Note for {self.appointment_id}"

# Create your models here.
