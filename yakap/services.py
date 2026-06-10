import calendar
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db.models import Case, DecimalField, F, Sum, When
from django.utils import timezone

from .models import (
    AppointmentYakapSnapshot,
    ClinicYakapSettings,
    PatientYakapProfile,
    ServiceYakapRule,
    YakapAuditEvent,
    YakapCoverageCategory,
    YakapCreditLinePeriod,
    YakapLedgerEntry,
)


DEFAULT_CATEGORY_DEFINITIONS = [
    ("Primary Care", YakapCoverageCategory.TYPE_PRIMARY_CARE, 0),
    ("Laboratory", YakapCoverageCategory.TYPE_LABORATORY, 1),
    ("Medicines", YakapCoverageCategory.TYPE_MEDICINES, 2),
    ("Cancer Screening", YakapCoverageCategory.TYPE_CANCER_SCREENING, 3),
]

def ensure_default_yakap_setup(clinic):
    yakap_settings, _created = ClinicYakapSettings.objects.get_or_create(clinic=clinic)
    categories = []
    for name, category_type, sort_order in DEFAULT_CATEGORY_DEFINITIONS:
        annual_limit = (
            yakap_settings.medicine_annual_limit_default
            if category_type == YakapCoverageCategory.TYPE_MEDICINES
            else yakap_settings.default_non_medicine_limit
        )
        category, _created = YakapCoverageCategory.objects.get_or_create(
            clinic=clinic,
            name=name,
            defaults={
                "category_type": category_type,
                "annual_limit": annual_limit,
                "sort_order": sort_order,
            },
        )
        categories.append(category)
    return yakap_settings, categories


def yakap_profile_for_patient(patient):
    profile, _created = PatientYakapProfile.objects.get_or_create(clinic=patient.clinic, patient=patient)
    return profile


def _as_local_date(clinic, value):
    clinic_timezone = ZoneInfo(clinic.timezone)
    if value is None:
        return timezone.localtime(timezone.now(), clinic_timezone).date()
    if isinstance(value, date) and not hasattr(value, "hour"):
        return value
    if timezone.is_naive(value):
        value = timezone.make_aware(value, clinic_timezone)
    return value.astimezone(clinic_timezone).date()


def _reset_date_for_year(yakap_settings, year):
    reset_day = min(yakap_settings.reset_day, calendar.monthrange(year, yakap_settings.reset_month)[1])
    return date(year, yakap_settings.reset_month, reset_day)


def period_bounds_for(clinic, when=None, *, create_settings=True):
    if create_settings:
        yakap_settings, _created = ClinicYakapSettings.objects.get_or_create(clinic=clinic)
    else:
        try:
            yakap_settings = clinic.yakap_settings
        except ClinicYakapSettings.DoesNotExist:
            yakap_settings = ClinicYakapSettings(clinic=clinic)
    when = _as_local_date(clinic, when)
    reset_date = _reset_date_for_year(yakap_settings, when.year)
    period_start_year = when.year if when >= reset_date else when.year - 1
    period_start = _reset_date_for_year(yakap_settings, period_start_year)
    next_period_start = _reset_date_for_year(yakap_settings, period_start_year + 1)
    return period_start, next_period_start - timedelta(days=1)


def active_period_for_profile_category(profile, category, when=None):
    period_start, period_end = period_bounds_for(profile.clinic, when=when)
    limit = profile.annual_limit_override if profile.annual_limit_override is not None else category.annual_limit
    period, _created = YakapCreditLinePeriod.objects.get_or_create(
        clinic=profile.clinic,
        patient=profile.patient,
        profile=profile,
        category=category,
        period_start=period_start,
        period_end=period_end,
        defaults={"limit_snapshot": limit},
    )
    return period


def create_appointment_yakap_snapshot(appointment, requested=False):
    rule = getattr(appointment.service, "yakap_rule", None)
    category = rule.category if rule and rule.category else None
    category_name = category.name if category else ""
    rule_status = rule.coverage_status if rule else ServiceYakapRule.STATUS_REQUIRES_VERIFICATION
    status = AppointmentYakapSnapshot.STATUS_REQUESTED if requested else AppointmentYakapSnapshot.STATUS_NOT_REQUESTED
    estimated_remaining = None
    estimated_covered_amount = None
    if requested and category:
        profile = yakap_profile_for_patient(appointment.patient)
        balance = estimated_remaining_for(profile, category, when=appointment.starts_at)
        estimated_remaining = balance["remaining"]
        estimated_covered_amount = rule.estimated_covered_amount
    return AppointmentYakapSnapshot.objects.create(
        clinic=appointment.clinic,
        appointment=appointment,
        requested=requested,
        coverage_status=status,
        category_name=category_name,
        service_rule_status=rule_status,
        estimated_remaining_at_booking=estimated_remaining,
        estimated_covered_amount_at_booking=estimated_covered_amount,
    )


def _estimated_used_for_bounds(profile, category, clinic, period_start, period_end):
    if not profile.pk:
        return Decimal("0.00")
    clinic_timezone = ZoneInfo(clinic.timezone)
    start_at = timezone.make_aware(datetime.combine(period_start, time.min), clinic_timezone)
    end_at = timezone.make_aware(datetime.combine(period_end + timedelta(days=1), time.min), clinic_timezone)
    total = profile.ledger_entries.filter(
        category=category,
        occurred_at__gte=start_at,
        occurred_at__lt=end_at,
    ).aggregate(
        total=Sum(
            Case(
                When(entry_type=YakapLedgerEntry.TYPE_REVERSAL, then=-F("amount")),
                default=F("amount"),
                output_field=DecimalField(max_digits=10, decimal_places=2),
            )
        )
    )["total"]
    return total or Decimal("0.00")


def _estimated_used_for_period(profile, category, period):
    return _estimated_used_for_bounds(profile, category, period.clinic, period.period_start, period.period_end)


def estimated_used_for(profile, category, when=None):
    period = active_period_for_profile_category(profile, category, when=when)
    return _estimated_used_for_period(profile, category, period)


def estimated_remaining_for(profile, category, when=None, *, create_period=True):
    if create_period:
        period = active_period_for_profile_category(profile, category, when=when)
        used = _estimated_used_for_period(profile, category, period)
        limit = period.limit_snapshot
    else:
        period_start, period_end = period_bounds_for(profile.clinic, when=when, create_settings=False)
        period = None
        if profile.pk:
            period = YakapCreditLinePeriod.objects.filter(
                profile=profile,
                category=category,
                period_start=period_start,
                period_end=period_end,
            ).first()
        used = _estimated_used_for_bounds(profile, category, profile.clinic, period_start, period_end)
        limit = period.limit_snapshot if period else (
            profile.annual_limit_override if profile.annual_limit_override is not None else category.annual_limit
        )
    return {"period": period, "limit": limit, "used": used, "remaining": limit - used}


def ledger_entry_over_limit(entry, *, create_period=True):
    if entry.entry_type == YakapLedgerEntry.TYPE_REVERSAL:
        return False, Decimal("0.00")
    balance = estimated_remaining_for(entry.profile, entry.category, when=entry.occurred_at, create_period=create_period)
    remaining_after_entry = balance["remaining"] - entry.amount
    return remaining_after_entry < 0, remaining_after_entry


def balance_state_for(balance, low_threshold):
    if isinstance(balance, dict):
        balance = balance["remaining"]
    if balance < Decimal("0.00"):
        return "negative_or_exceeded"
    if balance == Decimal("0.00"):
        return "zero"
    if balance <= low_threshold:
        return "low"
    return "healthy"


def create_yakap_audit_event(*, clinic, actor, action, obj, summary):
    return YakapAuditEvent.objects.create(
        clinic=clinic,
        actor=actor,
        action=action,
        object_type=obj.__class__.__name__,
        object_id=str(obj.pk),
        summary=summary,
    )
