from decimal import Decimal

from .models import (
    AppointmentYakapSnapshot,
    ClinicYakapSettings,
    PatientYakapProfile,
    ServiceYakapRule,
    YakapCoverageCategory,
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
        category, _created = YakapCoverageCategory.objects.get_or_create(
            clinic=clinic,
            name=name,
            defaults={
                "category_type": category_type,
                "annual_limit": yakap_settings.default_annual_credit,
                "sort_order": sort_order,
            },
        )
        categories.append(category)
    return yakap_settings, categories


def yakap_profile_for_patient(patient):
    profile, _created = PatientYakapProfile.objects.get_or_create(clinic=patient.clinic, patient=patient)
    return profile


def create_appointment_yakap_snapshot(appointment, requested=False):
    rule = getattr(appointment.service, "yakap_rule", None)
    category_name = rule.category.name if rule and rule.category else ""
    rule_status = rule.coverage_status if rule else ServiceYakapRule.STATUS_REQUIRES_VERIFICATION
    status = AppointmentYakapSnapshot.STATUS_REQUESTED if requested else AppointmentYakapSnapshot.STATUS_NOT_REQUESTED
    return AppointmentYakapSnapshot.objects.create(
        clinic=appointment.clinic,
        appointment=appointment,
        requested=requested,
        coverage_status=status,
        category_name=category_name,
        service_rule_status=rule_status,
    )


def estimated_used_for(profile, category):
    total = Decimal("0.00")
    for entry in profile.ledger_entries.filter(category=category):
        total += entry.signed_amount
    return total


def estimated_remaining_for(profile, category):
    limit = profile.annual_limit_override if profile.annual_limit_override is not None else category.annual_limit
    used = estimated_used_for(profile, category)
    return {"limit": limit, "used": used, "remaining": limit - used}
