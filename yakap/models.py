import calendar
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from clinics.models import Clinic, TimeStampedModel


class FullCleanOnSaveMixin:
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ClinicYakapSettings(FullCleanOnSaveMixin, TimeStampedModel):
    clinic = models.OneToOneField(Clinic, on_delete=models.CASCADE, related_name="yakap_settings")
    is_enabled = models.BooleanField(default=False)
    public_promo_headline = models.CharField(max_length=160, default="Use your PhilHealth YAKAP benefits")
    public_promo_body = models.TextField(
        default="Book eligible YAKAP primary care services, subject to PhilHealth and clinic verification."
    )
    public_disclaimer = models.TextField(
        default="YAKAP eligibility and remaining coverage must be verified by clinic staff."
    )
    internal_disclaimer = models.TextField(
        default="All KliniAssist YAKAP balances are estimates, not official PhilHealth balances."
    )
    verification_instructions = models.TextField(
        blank=True,
        default="Verify eligibility through the clinic's PhilHealth workflow before service.",
    )
    default_annual_credit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("20000.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    reset_month = models.PositiveSmallIntegerField(default=1)
    reset_day = models.PositiveSmallIntegerField(default=1)
    hard_block_exceeded = models.BooleanField(default=False)

    def clean(self):
        super().clean()
        errors = {}
        if self.reset_month is not None and not 1 <= self.reset_month <= 12:
            errors["reset_month"] = "Reset month must be between 1 and 12."
        if self.reset_day is not None and not 1 <= self.reset_day <= 31:
            errors["reset_day"] = "Reset day must be between 1 and 31."
        if not errors.get("reset_month") and not errors.get("reset_day") and self.reset_month and self.reset_day:
            max_day = calendar.monthrange(2024, self.reset_month)[1]
            if self.reset_day > max_day:
                errors["reset_day"] = "Reset day must be valid for the reset month."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"YAKAP settings for {self.clinic}"


class YakapCoverageCategory(FullCleanOnSaveMixin, TimeStampedModel):
    TYPE_PRIMARY_CARE = "primary_care"
    TYPE_LABORATORY = "laboratory"
    TYPE_MEDICINES = "medicines"
    TYPE_CANCER_SCREENING = "cancer_screening"
    TYPE_OTHER = "other"
    TYPE_CHOICES = [
        (TYPE_PRIMARY_CARE, "Primary Care"),
        (TYPE_LABORATORY, "Laboratory"),
        (TYPE_MEDICINES, "Medicines"),
        (TYPE_CANCER_SCREENING, "Cancer Screening"),
        (TYPE_OTHER, "Other"),
    ]

    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="yakap_categories")
    name = models.CharField(max_length=120)
    category_type = models.CharField(max_length=32, choices=TYPE_CHOICES, default=TYPE_OTHER)
    annual_limit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default="")
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["clinic", "name"], name="unique_yakap_category_per_clinic"),
        ]

    def __str__(self):
        return self.name


class ServiceYakapRule(FullCleanOnSaveMixin, TimeStampedModel):
    STATUS_COVERED = "covered"
    STATUS_POSSIBLY_COVERED = "possibly_covered"
    STATUS_NOT_COVERED = "not_covered"
    STATUS_CASH_ONLY = "cash_only"
    STATUS_REQUIRES_VERIFICATION = "requires_verification"
    STATUS_CHOICES = [
        (STATUS_COVERED, "Covered"),
        (STATUS_POSSIBLY_COVERED, "Possibly covered"),
        (STATUS_NOT_COVERED, "Not covered"),
        (STATUS_CASH_ONLY, "Cash only"),
        (STATUS_REQUIRES_VERIFICATION, "Requires verification"),
    ]

    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="yakap_service_rules")
    service = models.OneToOneField("services.Service", on_delete=models.CASCADE, related_name="yakap_rule")
    category = models.ForeignKey(
        YakapCoverageCategory,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="service_rules",
    )
    coverage_status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_REQUIRES_VERIFICATION)
    estimated_covered_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    requires_verification = models.BooleanField(default=True)
    public_badge_label = models.CharField(max_length=80, blank=True, default="")
    staff_notes = models.TextField(blank=True, default="")

    def clean(self):
        super().clean()
        errors = {}
        if self.clinic_id and self.service_id and self.service.clinic_id != self.clinic_id:
            errors["service"] = "Service must belong to the YAKAP rule clinic."
        if self.clinic_id and self.category_id and self.category.clinic_id != self.clinic_id:
            errors["category"] = "Category must belong to the YAKAP rule clinic."
        if errors:
            raise ValidationError(errors)

    @property
    def is_publicly_promotable(self):
        return self.coverage_status in {
            self.STATUS_COVERED,
            self.STATUS_POSSIBLY_COVERED,
            self.STATUS_REQUIRES_VERIFICATION,
        }


class PatientYakapProfile(FullCleanOnSaveMixin, TimeStampedModel):
    STATUS_NOT_ASKED = "not_asked"
    STATUS_INTERESTED = "interested"
    STATUS_REGISTERED_ELSEWHERE = "registered_elsewhere"
    STATUS_REGISTERED_TO_THIS_CLINIC = "registered_to_this_clinic"
    STATUS_FPE_COMPLETED = "fpe_completed"
    STATUS_YES_SIGNED = "yes_signed"
    STATUS_ACTIVE = "active"
    STATUS_INACTIVE = "inactive"
    STATUS_CHOICES = [
        (STATUS_NOT_ASKED, "Not asked"),
        (STATUS_INTERESTED, "Interested"),
        (STATUS_REGISTERED_ELSEWHERE, "Registered elsewhere"),
        (STATUS_REGISTERED_TO_THIS_CLINIC, "Registered to this clinic"),
        (STATUS_FPE_COMPLETED, "FPE completed"),
        (STATUS_YES_SIGNED, "YES signed"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_INACTIVE, "Inactive"),
    ]

    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="yakap_patient_profiles")
    patient = models.OneToOneField("patients.Patient", on_delete=models.CASCADE, related_name="yakap_profile")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_INTERESTED)
    annual_limit_override = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    last_verified_at = models.DateTimeField(blank=True, null=True)
    staff_notes = models.TextField(blank=True, default="")

    def clean(self):
        super().clean()
        if self.clinic_id and self.patient_id and self.patient.clinic_id != self.clinic_id:
            raise ValidationError({"patient": "Patient must belong to the YAKAP profile clinic."})


class AppointmentYakapSnapshot(FullCleanOnSaveMixin, TimeStampedModel):
    STATUS_NOT_REQUESTED = "not_requested"
    STATUS_REQUESTED = "requested"
    STATUS_UNVERIFIED = "unverified"
    STATUS_VERIFIED = "verified"
    STATUS_NOT_ELIGIBLE = "not_eligible"
    STATUS_EXCEEDED = "exceeded"
    STATUS_NOT_APPLICABLE = "not_applicable"
    STATUS_CHOICES = [
        (STATUS_NOT_REQUESTED, "Not requested"),
        (STATUS_REQUESTED, "Requested"),
        (STATUS_UNVERIFIED, "Unverified"),
        (STATUS_VERIFIED, "Verified"),
        (STATUS_NOT_ELIGIBLE, "Not eligible"),
        (STATUS_EXCEEDED, "Exceeded"),
        (STATUS_NOT_APPLICABLE, "Not applicable"),
    ]

    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="yakap_appointment_snapshots")
    appointment = models.OneToOneField(
        "appointments.Appointment",
        on_delete=models.CASCADE,
        related_name="yakap_snapshot",
    )
    requested = models.BooleanField(default=False)
    coverage_status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_NOT_REQUESTED)
    category_name = models.CharField(max_length=120, blank=True, default="")
    service_rule_status = models.CharField(max_length=32, blank=True, default="")
    estimated_remaining_at_booking = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    def clean(self):
        super().clean()
        if self.clinic_id and self.appointment_id and self.appointment.clinic_id != self.clinic_id:
            raise ValidationError({"appointment": "Appointment must belong to the YAKAP snapshot clinic."})


class YakapLedgerEntry(FullCleanOnSaveMixin, TimeStampedModel):
    TYPE_SERVICE_USAGE = "service_usage"
    TYPE_MEDICINE_USAGE = "medicine_usage"
    TYPE_ADJUSTMENT = "adjustment"
    TYPE_REVERSAL = "reversal"
    TYPE_CHOICES = [
        (TYPE_SERVICE_USAGE, "Service usage"),
        (TYPE_MEDICINE_USAGE, "Medicine usage"),
        (TYPE_ADJUSTMENT, "Adjustment"),
        (TYPE_REVERSAL, "Reversal"),
    ]

    VERIFICATION_UNVERIFIED = "unverified"
    VERIFICATION_VERIFIED = "verified"
    VERIFICATION_CHOICES = [
        (VERIFICATION_UNVERIFIED, "Unverified"),
        (VERIFICATION_VERIFIED, "Verified"),
    ]

    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="yakap_ledger_entries")
    patient = models.ForeignKey("patients.Patient", on_delete=models.CASCADE, related_name="yakap_ledger_entries")
    profile = models.ForeignKey(PatientYakapProfile, on_delete=models.CASCADE, related_name="ledger_entries")
    appointment = models.ForeignKey(
        "appointments.Appointment",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="yakap_ledger_entries",
    )
    category = models.ForeignKey(YakapCoverageCategory, on_delete=models.PROTECT, related_name="ledger_entries")
    service = models.ForeignKey(
        "services.Service",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="yakap_ledger_entries",
    )
    entry_type = models.CharField(max_length=32, choices=TYPE_CHOICES)
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    verification_status = models.CharField(
        max_length=32,
        choices=VERIFICATION_CHOICES,
        default=VERIFICATION_UNVERIFIED,
    )
    note = models.TextField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        super().clean()
        errors = {}
        if self.clinic_id and self.patient_id and self.patient.clinic_id != self.clinic_id:
            errors["patient"] = "Patient must belong to the ledger entry clinic."
        if self.clinic_id and self.profile_id and self.profile.clinic_id != self.clinic_id:
            errors["profile"] = "Profile must belong to the ledger entry clinic."
        if self.patient_id and self.profile_id and self.profile.patient_id != self.patient_id:
            errors["profile"] = "Profile must belong to the ledger entry patient."
        if self.clinic_id and self.category_id and self.category.clinic_id != self.clinic_id:
            errors["category"] = "Category must belong to the ledger entry clinic."
        if self.clinic_id and self.appointment_id and self.appointment.clinic_id != self.clinic_id:
            errors["appointment"] = "Appointment must belong to the ledger entry clinic."
        if self.patient_id and self.appointment_id and self.appointment.patient_id != self.patient_id:
            errors["appointment"] = "Appointment patient must match the ledger entry patient."
        if self.clinic_id and self.service_id and self.service.clinic_id != self.clinic_id:
            errors["service"] = "Service must belong to the ledger entry clinic."
        if self.service_id and self.appointment_id and self.appointment.service_id != self.service_id:
            errors["service"] = "Service must match the appointment service."
        if self.entry_type == self.TYPE_REVERSAL and self.profile_id and self.category_id and self.amount is not None:
            current_used = self._estimated_used_excluding_self()
            if self.amount > current_used:
                errors["amount"] = "Reversal cannot exceed current estimated used for this profile and category."
        if errors:
            raise ValidationError(errors)

    def _estimated_used_excluding_self(self):
        total = Decimal("0.00")
        entries = self.profile.ledger_entries.filter(category=self.category)
        if self.pk:
            entries = entries.exclude(pk=self.pk)
        for entry in entries:
            total += entry.signed_amount
        return total

    @property
    def signed_amount(self):
        if self.entry_type == self.TYPE_REVERSAL:
            return -self.amount
        return self.amount
