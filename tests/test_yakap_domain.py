from decimal import Decimal
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from appointments.models import Appointment
from clinics.models import Clinic, ClinicGroup
from patients.models import Patient
from services.models import Service
from yakap.models import (
    AppointmentYakapSnapshot,
    ClinicYakapSettings,
    PatientYakapProfile,
    ServiceYakapRule,
    YakapCoverageCategory,
    YakapLedgerEntry,
)
from yakap.services import ensure_default_yakap_setup, estimated_remaining_for, estimated_used_for, yakap_profile_for_patient


def create_other_clinic(clinic, slug="other-yakap-clinic"):
    other_group = ClinicGroup.objects.create(name=f"Other {slug}", owner=clinic.group.owner)
    return Clinic.objects.create(group=other_group, name=f"Other {slug}", slug=slug)


def create_appointment(clinic, patient, service, days_from_now=2):
    starts_at = timezone.now() + timedelta(days=days_from_now)
    return Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=service.effective_duration()),
    )


@pytest.mark.django_db
def test_ensure_default_yakap_setup_creates_clinic_scoped_defaults(clinic_setup):
    clinic, _service = clinic_setup

    settings, categories = ensure_default_yakap_setup(clinic)

    assert settings.clinic == clinic
    assert settings.default_annual_credit == Decimal("20000.00")
    expected_categories = {
        "Primary Care": YakapCoverageCategory.TYPE_PRIMARY_CARE,
        "Laboratory": YakapCoverageCategory.TYPE_LABORATORY,
        "Medicines": YakapCoverageCategory.TYPE_MEDICINES,
        "Cancer Screening": YakapCoverageCategory.TYPE_CANCER_SCREENING,
    }
    assert {category.name: category.category_type for category in categories} == expected_categories
    assert all(category.clinic == clinic for category in categories)
    assert all(category.annual_limit == Decimal("20000.00") for category in categories)
    assert set(clinic.yakap_categories.values_list("name", flat=True)) == set(expected_categories)


@pytest.mark.django_db
def test_service_yakap_rule_rejects_category_from_another_clinic(clinic_setup):
    clinic, service = clinic_setup
    other_clinic = create_other_clinic(clinic)
    _settings, other_categories = ensure_default_yakap_setup(other_clinic)

    rule = ServiceYakapRule(
        clinic=clinic,
        service=service,
        category=other_categories[0],
        coverage_status=ServiceYakapRule.STATUS_COVERED,
    )

    with pytest.raises(ValidationError) as exc_info:
        rule.full_clean()

    assert "category" in str(exc_info.value).lower()


@pytest.mark.django_db
def test_service_yakap_rule_create_rejects_category_from_another_clinic(clinic_setup):
    clinic, service = clinic_setup
    other_clinic = create_other_clinic(clinic)
    _settings, other_categories = ensure_default_yakap_setup(other_clinic)

    with pytest.raises(ValidationError, match="category"):
        ServiceYakapRule.objects.create(
            clinic=clinic,
            service=service,
            category=other_categories[0],
            coverage_status=ServiceYakapRule.STATUS_COVERED,
        )


@pytest.mark.django_db
def test_patient_yakap_profile_create_rejects_patient_from_another_clinic(clinic_setup):
    clinic, _service = clinic_setup
    other_clinic = create_other_clinic(clinic)
    other_patient = Patient.objects.create(clinic=other_clinic, full_name="Other Patient", phone="0917-111-1111")

    with pytest.raises(ValidationError, match="patient"):
        PatientYakapProfile.objects.create(clinic=clinic, patient=other_patient)


@pytest.mark.django_db
def test_appointment_yakap_snapshot_create_rejects_appointment_from_another_clinic(clinic_setup):
    clinic, _service = clinic_setup
    other_clinic = create_other_clinic(clinic)
    other_service = Service.objects.create(clinic=other_clinic, name="Other Consultation", duration_minutes=30)
    other_patient = Patient.objects.create(clinic=other_clinic, full_name="Other Patient", phone="0917-111-1111")
    other_appointment = create_appointment(other_clinic, other_patient, other_service)

    with pytest.raises(ValidationError, match="appointment"):
        AppointmentYakapSnapshot.objects.create(clinic=clinic, appointment=other_appointment)


@pytest.mark.django_db
def test_yakap_ledger_create_rejects_category_from_another_clinic(clinic_setup):
    clinic, _service = clinic_setup
    other_clinic = create_other_clinic(clinic)
    _settings, other_categories = ensure_default_yakap_setup(other_clinic)
    patient = Patient.objects.create(clinic=clinic, full_name="Juan Dela Cruz", phone="0917-000-0001")
    profile = yakap_profile_for_patient(patient)

    with pytest.raises(ValidationError, match="category"):
        YakapLedgerEntry.objects.create(
            clinic=clinic,
            patient=patient,
            profile=profile,
            category=other_categories[0],
            entry_type=YakapLedgerEntry.TYPE_SERVICE_USAGE,
            amount=Decimal("750.00"),
            note="Cross-clinic category should not persist",
        )


@pytest.mark.django_db
def test_yakap_ledger_rejects_patient_profile_mismatch(clinic_setup):
    clinic, _service = clinic_setup
    _settings, categories = ensure_default_yakap_setup(clinic)
    patient = Patient.objects.create(clinic=clinic, full_name="Juan Dela Cruz", phone="0917-000-0001")
    other_patient = Patient.objects.create(clinic=clinic, full_name="Maria Santos", phone="0917-000-0002")
    other_profile = yakap_profile_for_patient(other_patient)

    with pytest.raises(ValidationError, match="profile"):
        YakapLedgerEntry.objects.create(
            clinic=clinic,
            patient=patient,
            profile=other_profile,
            category=categories[0],
            entry_type=YakapLedgerEntry.TYPE_SERVICE_USAGE,
            amount=Decimal("750.00"),
            note="Profile must match patient",
        )


@pytest.mark.django_db
def test_yakap_ledger_rejects_appointment_patient_mismatch(clinic_setup):
    clinic, service = clinic_setup
    _settings, categories = ensure_default_yakap_setup(clinic)
    patient = Patient.objects.create(clinic=clinic, full_name="Juan Dela Cruz", phone="0917-000-0001")
    profile = yakap_profile_for_patient(patient)
    other_patient = Patient.objects.create(clinic=clinic, full_name="Maria Santos", phone="0917-000-0002")
    other_appointment = create_appointment(clinic, other_patient, service)

    with pytest.raises(ValidationError, match="appointment"):
        YakapLedgerEntry.objects.create(
            clinic=clinic,
            patient=patient,
            profile=profile,
            appointment=other_appointment,
            category=categories[0],
            service=service,
            entry_type=YakapLedgerEntry.TYPE_SERVICE_USAGE,
            amount=Decimal("750.00"),
            note="Appointment patient must match ledger patient",
        )


@pytest.mark.django_db
def test_yakap_ledger_rejects_appointment_service_mismatch(clinic_setup):
    clinic, service = clinic_setup
    _settings, categories = ensure_default_yakap_setup(clinic)
    patient = Patient.objects.create(clinic=clinic, full_name="Juan Dela Cruz", phone="0917-000-0001")
    profile = yakap_profile_for_patient(patient)
    appointment = create_appointment(clinic, patient, service)
    other_service = Service.objects.create(clinic=clinic, name="Laboratory Test", duration_minutes=30)

    with pytest.raises(ValidationError, match="service"):
        YakapLedgerEntry.objects.create(
            clinic=clinic,
            patient=patient,
            profile=profile,
            appointment=appointment,
            category=categories[0],
            service=other_service,
            entry_type=YakapLedgerEntry.TYPE_SERVICE_USAGE,
            amount=Decimal("750.00"),
            note="Appointment service must match ledger service",
        )


@pytest.mark.django_db
def test_yakap_ledger_rejects_reversal_that_exceeds_current_used(clinic_setup):
    clinic, _service = clinic_setup
    _settings, categories = ensure_default_yakap_setup(clinic)
    category = categories[0]
    patient = Patient.objects.create(clinic=clinic, full_name="Juan Dela Cruz", phone="0917-000-0001")
    profile = yakap_profile_for_patient(patient)
    YakapLedgerEntry.objects.create(
        clinic=clinic,
        patient=patient,
        profile=profile,
        category=category,
        entry_type=YakapLedgerEntry.TYPE_SERVICE_USAGE,
        amount=Decimal("750.00"),
        note="Initial usage",
    )

    with pytest.raises(ValidationError, match="amount"):
        YakapLedgerEntry.objects.create(
            clinic=clinic,
            patient=patient,
            profile=profile,
            category=category,
            entry_type=YakapLedgerEntry.TYPE_REVERSAL,
            amount=Decimal("800.00"),
            note="Oversized reversal",
        )


@pytest.mark.django_db
def test_yakap_ledger_valid_reversal_reduces_used_without_going_negative(clinic_setup):
    clinic, _service = clinic_setup
    _settings, categories = ensure_default_yakap_setup(clinic)
    category = categories[0]
    patient = Patient.objects.create(clinic=clinic, full_name="Juan Dela Cruz", phone="0917-000-0001")
    profile = yakap_profile_for_patient(patient)
    YakapLedgerEntry.objects.create(
        clinic=clinic,
        patient=patient,
        profile=profile,
        category=category,
        entry_type=YakapLedgerEntry.TYPE_SERVICE_USAGE,
        amount=Decimal("750.00"),
        note="Initial usage",
    )

    YakapLedgerEntry.objects.create(
        clinic=clinic,
        patient=patient,
        profile=profile,
        category=category,
        entry_type=YakapLedgerEntry.TYPE_REVERSAL,
        amount=Decimal("250.00"),
        note="Valid reversal",
    )

    assert estimated_used_for(profile, category) == Decimal("500.00")


@pytest.mark.django_db
def test_clinic_yakap_settings_create_rejects_impossible_reset_date(clinic_setup):
    clinic, _service = clinic_setup

    with pytest.raises(ValidationError, match="reset_day"):
        ClinicYakapSettings.objects.create(clinic=clinic, reset_month=2, reset_day=31)


@pytest.mark.django_db
def test_yakap_ledger_usage_updates_estimated_remaining(clinic_setup):
    clinic, _service = clinic_setup
    _settings, categories = ensure_default_yakap_setup(clinic)
    category = categories[0]
    patient = Patient.objects.create(clinic=clinic, full_name="Juan Dela Cruz", phone="0917-000-0000")
    profile = yakap_profile_for_patient(patient)

    YakapLedgerEntry.objects.create(
        clinic=clinic,
        patient=patient,
        profile=profile,
        category=category,
        entry_type=YakapLedgerEntry.TYPE_SERVICE_USAGE,
        amount=Decimal("750.00"),
        note="General consultation usage",
    )

    balance = estimated_remaining_for(profile, category)

    assert balance == {
        "limit": Decimal("20000.00"),
        "used": Decimal("750.00"),
        "remaining": Decimal("19250.00"),
    }
