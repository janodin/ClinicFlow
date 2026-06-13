import calendar
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from clinics.models import Clinic, TimeStampedModel


class FullCleanOnSaveMixin:
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ClinicYakapSettings(FullCleanOnSaveMixin, TimeStampedModel):
    clinic = models.OneToOneField(Clinic, on_delete=models.CASCADE, related_name="yakap_settings")
    is_enabled = models.BooleanField(default=False)
    program_label = models.CharField(max_length=40, default="YAKAP")
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
    medicine_annual_limit_default = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("20000.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    default_non_medicine_limit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    low_balance_threshold_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("1000.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    verification_stale_after_days = models.PositiveSmallIntegerField(default=30)
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
        return (
            self.coverage_status in {
                self.STATUS_COVERED,
                self.STATUS_POSSIBLY_COVERED,
                self.STATUS_REQUIRES_VERIFICATION,
            }
            and bool(self.category_id)
            and bool(getattr(self.category, "is_active", False))
        )


class PatientYakapProfile(FullCleanOnSaveMixin, TimeStampedModel):
    STATUS_NOT_ASKED = "not_asked"
    STATUS_INTERESTED = "interested"
    STATUS_PENDING_VERIFICATION = "pending_verification"
    STATUS_REGISTERED_ELSEWHERE = "registered_elsewhere"
    STATUS_REGISTERED_TO_THIS_CLINIC = "registered_to_this_clinic"
    STATUS_FPE_COMPLETED = "fpe_completed"
    STATUS_YES_SIGNED = "yes_signed"
    STATUS_ACTIVE = "active"
    STATUS_INACTIVE = "inactive"
    STATUS_TRANSFERRED = "transferred"
    STATUS_CHOICES = [
        (STATUS_NOT_ASKED, "Not asked"),
        (STATUS_INTERESTED, "Interested"),
        (STATUS_PENDING_VERIFICATION, "Pending verification"),
        (STATUS_REGISTERED_ELSEWHERE, "Registered elsewhere"),
        (STATUS_REGISTERED_TO_THIS_CLINIC, "Registered to this clinic"),
        (STATUS_FPE_COMPLETED, "FPE completed"),
        (STATUS_YES_SIGNED, "YES signed"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_INACTIVE, "Inactive"),
        (STATUS_TRANSFERRED, "Transferred"),
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
    registered_clinic_name = models.CharField(max_length=160, blank=True, default="")
    last_verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="verified_yakap_profiles",
    )
    verification_method = models.CharField(max_length=160, blank=True, default="")
    verification_reference = models.CharField(max_length=160, blank=True, default="")
    consent_note = models.TextField(blank=True, default="")
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
    STATUS_NEEDS_VERIFICATION = "needs_verification"
    STATUS_VERIFIED_FOR_VISIT = "verified_for_visit"
    STATUS_EXCEEDED_ESTIMATE = "exceeded_estimate"
    STATUS_POSTED = "posted"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_NOT_REQUESTED, "Not requested"),
        (STATUS_REQUESTED, "Requested"),
        (STATUS_UNVERIFIED, "Unverified"),
        (STATUS_VERIFIED, "Verified"),
        (STATUS_NOT_ELIGIBLE, "Not eligible"),
        (STATUS_EXCEEDED, "Exceeded"),
        (STATUS_NOT_APPLICABLE, "Not applicable"),
        (STATUS_NEEDS_VERIFICATION, "Needs verification"),
        (STATUS_VERIFIED_FOR_VISIT, "Verified for visit"),
        (STATUS_EXCEEDED_ESTIMATE, "Exceeded estimate"),
        (STATUS_POSTED, "Posted"),
        (STATUS_CANCELLED, "Cancelled"),
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
    estimated_covered_amount_at_booking = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    verified_at = models.DateTimeField(blank=True, null=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="verified_yakap_appointments",
    )
    verification_note = models.TextField(blank=True, default="")

    def clean(self):
        super().clean()
        if self.clinic_id and self.appointment_id and self.appointment.clinic_id != self.clinic_id:
            raise ValidationError({"appointment": "Appointment must belong to the YAKAP snapshot clinic."})


class YakapLedgerEntry(FullCleanOnSaveMixin, TimeStampedModel):
    TYPE_SERVICE_USAGE = "service_usage"
    TYPE_MEDICINE_USAGE = "medicine_usage"
    TYPE_LABORATORY_USAGE = "laboratory_usage"
    TYPE_SCREENING_USAGE = "screening_usage"
    TYPE_ADJUSTMENT = "adjustment"
    TYPE_REVERSAL = "reversal"
    TYPE_CHOICES = [
        (TYPE_SERVICE_USAGE, "Service usage"),
        (TYPE_MEDICINE_USAGE, "Medicine usage"),
        (TYPE_LABORATORY_USAGE, "Laboratory usage"),
        (TYPE_SCREENING_USAGE, "Screening usage"),
        (TYPE_ADJUSTMENT, "Adjustment"),
        (TYPE_REVERSAL, "Reversal"),
    ]

    SOURCE_MANUAL_DASHBOARD = "manual_dashboard"

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
    occurred_at = models.DateTimeField(default=timezone.now)
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
    verified_at = models.DateTimeField(blank=True, null=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="verified_yakap_ledger_entries",
    )
    source = models.CharField(max_length=40, default=SOURCE_MANUAL_DASHBOARD)
    external_reference = models.CharField(max_length=160, blank=True, default="")
    reversal_of = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="reversals",
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
        if self.reversal_of_id:
            original_entry = self.reversal_of
            if self.entry_type != self.TYPE_REVERSAL:
                errors["reversal_of"] = "Reversal link is only allowed for reversal entries."
            elif self.reversal_of.entry_type == self.TYPE_REVERSAL:
                errors["reversal_of"] = "Reversal cannot reverse another reversal entry."
            if self.clinic_id and original_entry.clinic_id != self.clinic_id:
                errors.setdefault("reversal_of", "Reversal entry must belong to the same clinic.")
            if self.patient_id and original_entry.patient_id != self.patient_id:
                errors.setdefault("reversal_of", "Reversal entry must belong to the same patient.")
            if self.category_id and original_entry.category_id != self.category_id:
                errors.setdefault("reversal_of", "Reversal entry must belong to the same category.")
            if self.entry_type == self.TYPE_REVERSAL:
                if self._period_bounds_for(self.occurred_at, clinic=original_entry.clinic) != self._period_bounds_for(
                    original_entry.occurred_at,
                    clinic=original_entry.clinic,
                ):
                    errors.setdefault("reversal_of", "Reversal must be in the same benefit period as the original entry.")
                reversed_total = original_entry.reversals.filter(entry_type=self.TYPE_REVERSAL).exclude(pk=self.pk).aggregate(
                    total=models.Sum("amount")
                )["total"] or Decimal("0.00")
                if self.amount is not None and reversed_total + self.amount > original_entry.amount:
                    errors["amount"] = "Reversal cannot exceed the remaining amount on the original entry."
        if self.entry_type == self.TYPE_REVERSAL and self.profile_id and self.category_id and self.amount is not None:
            current_used = self._estimated_used_excluding_self()
            if self.amount > current_used:
                errors["amount"] = "Reversal cannot exceed current estimated used for this profile and category."
        if errors:
            raise ValidationError(errors)

    def _estimated_used_excluding_self(self):
        period_start, period_end = self._period_bounds_for_occurred_at()
        clinic_timezone = ZoneInfo(self.clinic.timezone)
        start_at = timezone.make_aware(datetime.combine(period_start, time.min), clinic_timezone)
        end_at = timezone.make_aware(datetime.combine(period_end + timedelta(days=1), time.min), clinic_timezone)
        total = Decimal("0.00")
        entries = self.profile.ledger_entries.filter(
            category=self.category,
            occurred_at__gte=start_at,
            occurred_at__lt=end_at,
        )
        if self.pk:
            entries = entries.exclude(pk=self.pk)
        for entry in entries:
            total += entry.signed_amount
        return total

    def _period_bounds_for_occurred_at(self):
        return self._period_bounds_for(self.occurred_at)

    def _period_bounds_for(self, when, *, clinic=None):
        clinic = clinic or self.clinic
        clinic_timezone = ZoneInfo(clinic.timezone)
        when = when or timezone.now()
        if timezone.is_naive(when):
            when = timezone.make_aware(when, clinic_timezone)
        when = when.astimezone(clinic_timezone).date()
        try:
            yakap_settings = clinic.yakap_settings
            reset_month = yakap_settings.reset_month
            reset_day = yakap_settings.reset_day
        except ClinicYakapSettings.DoesNotExist:
            reset_month = 1
            reset_day = 1
        reset_day = min(reset_day, calendar.monthrange(when.year, reset_month)[1])
        reset_date = when.replace(month=reset_month, day=reset_day)
        period_start_year = when.year if when >= reset_date else when.year - 1
        period_start_day = min(reset_day, calendar.monthrange(period_start_year, reset_month)[1])
        period_start = datetime(period_start_year, reset_month, period_start_day).date()
        next_period_start_day = min(reset_day, calendar.monthrange(period_start_year + 1, reset_month)[1])
        next_period_start = datetime(period_start_year + 1, reset_month, next_period_start_day).date()
        return period_start, next_period_start - timedelta(days=1)

    @property
    def signed_amount(self):
        if self.entry_type == self.TYPE_REVERSAL:
            return -self.amount
        return self.amount

    def __str__(self):
        category = self.category.name if self.category_id else "YAKAP"
        return f"{self.get_entry_type_display()} {self.amount} for {category}"


class YakapCreditLinePeriod(FullCleanOnSaveMixin, TimeStampedModel):
    STATUS_OPEN = "open"
    STATUS_CLOSED = "closed"
    STATUS_SUPERSEDED = "superseded"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_CLOSED, "Closed"),
        (STATUS_SUPERSEDED, "Superseded"),
    ]

    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="yakap_credit_line_periods")
    patient = models.ForeignKey("patients.Patient", on_delete=models.CASCADE, related_name="yakap_credit_line_periods")
    profile = models.ForeignKey(PatientYakapProfile, on_delete=models.CASCADE, related_name="credit_line_periods")
    category = models.ForeignKey(YakapCoverageCategory, on_delete=models.PROTECT, related_name="credit_line_periods")
    period_start = models.DateField()
    period_end = models.DateField()
    limit_snapshot = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_OPEN)

    class Meta:
        ordering = ["-period_start", "-period_end", "category__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "category", "period_start", "period_end"],
                name="unique_yakap_credit_period_per_profile_category",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.limit_snapshot is None and self.category_id:
            self.limit_snapshot = self.category.annual_limit
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        errors = {}
        if self.clinic_id and self.patient_id and self.patient.clinic_id != self.clinic_id:
            errors["patient"] = "Patient must belong to the credit line period clinic."
        if self.clinic_id and self.profile_id and self.profile.clinic_id != self.clinic_id:
            errors["profile"] = "Profile must belong to the credit line period clinic."
        if self.patient_id and self.profile_id and self.profile.patient_id != self.patient_id:
            errors["profile"] = "Profile must belong to the credit line period patient."
        if self.clinic_id and self.category_id and self.category.clinic_id != self.clinic_id:
            errors["category"] = "Category must belong to the credit line period clinic."
        if self.period_start and self.period_end and self.period_end < self.period_start:
            errors["period_end"] = "Period end must be on or after period start."
        if errors:
            raise ValidationError(errors)


class YakapAuditEvent(FullCleanOnSaveMixin, TimeStampedModel):
    ACTION_SETTINGS_CHANGED = "settings_changed"
    ACTION_PROFILE_STATUS_CHANGED = "profile_status_changed"
    ACTION_APPOINTMENT_STATUS_CHANGED = "appointment_status_changed"
    ACTION_LEDGER_POSTED = "ledger_posted"
    ACTION_LEDGER_REVERSED = "ledger_reversed"
    ACTION_EXPORT_CREATED = "export_created"
    ACTION_CHOICES = [
        (ACTION_SETTINGS_CHANGED, "Settings changed"),
        (ACTION_PROFILE_STATUS_CHANGED, "Profile status changed"),
        (ACTION_APPOINTMENT_STATUS_CHANGED, "Appointment status changed"),
        (ACTION_LEDGER_POSTED, "Ledger posted"),
        (ACTION_LEDGER_REVERSED, "Ledger reversed"),
        (ACTION_EXPORT_CREATED, "Export created"),
    ]

    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="yakap_audit_events")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="yakap_audit_events",
    )
    action = models.CharField(max_length=40, choices=ACTION_CHOICES)
    object_type = models.CharField(max_length=80)
    object_id = models.CharField(max_length=80)
    summary = models.TextField()

    class Meta:
        ordering = ["-created_at"]
