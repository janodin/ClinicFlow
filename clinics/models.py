from django.conf import settings
from django.db import models
from django.utils.text import slugify


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
    widget_accent_color = models.CharField(max_length=16, default="#0891b2")
    widget_welcome_message = models.TextField(default="Welcome! How can we help you book an appointment today?")
    widget_behavior_instructions = models.TextField(default="Guide patients through booking smoothly. Always suggest the nearest available slot.")
    show_reason_field = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


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
