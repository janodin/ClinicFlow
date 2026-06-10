from decimal import Decimal
from datetime import date, datetime, timedelta, timezone as dt_timezone

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from yakap import forms as yakap_forms
from yakap import services as yakap_services
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
    YakapCreditLinePeriod,
    YakapLedgerEntry,
)
from yakap.services import (
    ensure_default_yakap_setup,
    estimated_remaining_for,
    estimated_used_for,
    yakap_profile_for_patient,
)


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
def test_default_yakap_setup_uses_medicine_limit_only(clinic_setup):
    clinic, _service = clinic_setup

    settings, categories = ensure_default_yakap_setup(clinic)

    assert settings.program_label == "YAKAP"
    assert settings.medicine_annual_limit_default == Decimal("20000.00")
    assert settings.default_non_medicine_limit == Decimal("0.00")
    assert settings.low_balance_threshold_amount == Decimal("1000.00")
    assert settings.verification_stale_after_days == 30
    categories_by_type = {category.category_type: category for category in categories}
    assert categories_by_type[YakapCoverageCategory.TYPE_MEDICINES].annual_limit == Decimal("20000.00")
    assert categories_by_type[YakapCoverageCategory.TYPE_PRIMARY_CARE].annual_limit == Decimal("0.00")
    assert categories_by_type[YakapCoverageCategory.TYPE_LABORATORY].annual_limit == Decimal("0.00")
    assert categories_by_type[YakapCoverageCategory.TYPE_CANCER_SCREENING].annual_limit == Decimal("0.00")


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
    limits_by_type = {category.category_type: category.annual_limit for category in categories}
    assert limits_by_type == {
        YakapCoverageCategory.TYPE_PRIMARY_CARE: Decimal("0.00"),
        YakapCoverageCategory.TYPE_LABORATORY: Decimal("0.00"),
        YakapCoverageCategory.TYPE_MEDICINES: Decimal("20000.00"),
        YakapCoverageCategory.TYPE_CANCER_SCREENING: Decimal("0.00"),
    }
    assert set(clinic.yakap_categories.values_list("name", flat=True)) == set(expected_categories)


@pytest.mark.django_db
def test_period_bounds_for_uses_clinic_reset_date(clinic_setup):
    clinic, _service = clinic_setup
    settings, _categories = ensure_default_yakap_setup(clinic)
    settings.reset_month = 7
    settings.reset_day = 1
    settings.save()

    period_start, period_end = yakap_services.period_bounds_for(clinic, when=date(2026, 8, 15))

    assert period_start == date(2026, 7, 1)
    assert period_end == date(2027, 6, 30)


@pytest.mark.django_db
def test_period_bounds_for_uses_last_valid_day_when_reset_is_feb_29_in_non_leap_year(clinic_setup):
    clinic, _service = clinic_setup
    settings, _categories = ensure_default_yakap_setup(clinic)
    settings.reset_month = 2
    settings.reset_day = 29
    settings.save()

    period_start, period_end = yakap_services.period_bounds_for(clinic, when=date(2025, 3, 1))

    assert period_start == date(2025, 2, 28)
    assert period_end == date(2026, 2, 27)


@pytest.mark.django_db
def test_period_bounds_for_uses_clinic_timezone_for_aware_datetime(clinic_setup):
    clinic, _service = clinic_setup
    clinic.timezone = "Asia/Manila"
    clinic.save()
    settings, _categories = ensure_default_yakap_setup(clinic)
    settings.reset_month = 7
    settings.reset_day = 1
    settings.save()
    when = datetime(2026, 6, 30, 16, 30, tzinfo=dt_timezone.utc)

    with timezone.override("UTC"):
        period_start, period_end = yakap_services.period_bounds_for(clinic, when=when)

    assert period_start == date(2026, 7, 1)
    assert period_end == date(2027, 6, 30)


@pytest.mark.django_db
def test_active_period_for_profile_category_uses_clinic_reset_date(clinic_setup):
    clinic, _service = clinic_setup
    settings, categories = ensure_default_yakap_setup(clinic)
    settings.reset_month = 7
    settings.reset_day = 1
    settings.save()
    category = next(category for category in categories if category.category_type == YakapCoverageCategory.TYPE_MEDICINES)
    patient = Patient.objects.create(clinic=clinic, full_name="Juan Dela Cruz", phone="0917-000-0001")
    profile = yakap_profile_for_patient(patient)

    active_period_for_profile_category = getattr(yakap_services, "active_period_for_profile_category", None)
    assert callable(active_period_for_profile_category)
    period = active_period_for_profile_category(profile, category, when=date(2026, 8, 15))

    assert period.clinic == clinic
    assert period.patient == patient
    assert period.profile == profile
    assert period.category == category
    assert period.period_start == date(2026, 7, 1)
    assert period.period_end == date(2027, 6, 30)
    assert period.limit_snapshot == Decimal("20000.00")
    assert period.status == YakapCreditLinePeriod.STATUS_OPEN


@pytest.mark.django_db
def test_estimated_used_for_respects_active_period_boundaries(clinic_setup):
    clinic, _service = clinic_setup
    settings, categories = ensure_default_yakap_setup(clinic)
    settings.reset_month = 7
    settings.reset_day = 1
    settings.save()
    category = next(category for category in categories if category.category_type == YakapCoverageCategory.TYPE_MEDICINES)
    patient = Patient.objects.create(clinic=clinic, full_name="Juan Dela Cruz", phone="0917-000-0001")
    profile = yakap_profile_for_patient(patient)

    for occurred_at, amount, note in [
        (datetime(2026, 6, 30, 23, 59), Decimal("5000.00"), "Before active period"),
        (datetime(2026, 7, 1, 0, 0), Decimal("100.00"), "At active period start"),
        (datetime(2027, 6, 30, 23, 59), Decimal("200.00"), "At active period end"),
        (datetime(2027, 7, 1, 0, 0), Decimal("300.00"), "After active period"),
    ]:
        YakapLedgerEntry.objects.create(
            clinic=clinic,
            patient=patient,
            profile=profile,
            category=category,
            occurred_at=timezone.make_aware(occurred_at),
            entry_type=YakapLedgerEntry.TYPE_MEDICINE_USAGE,
            amount=amount,
            note=note,
        )

    assert estimated_used_for(profile, category, when=date(2026, 8, 15)) == Decimal("300.00")


@pytest.mark.django_db
def test_estimated_remaining_for_uses_active_period_only(clinic_setup):
    clinic, _service = clinic_setup
    settings, categories = ensure_default_yakap_setup(clinic)
    settings.reset_month = 7
    settings.reset_day = 1
    settings.save()
    category = next(category for category in categories if category.category_type == YakapCoverageCategory.TYPE_MEDICINES)
    patient = Patient.objects.create(clinic=clinic, full_name="Juan Dela Cruz", phone="0917-000-0001")
    profile = yakap_profile_for_patient(patient)

    YakapLedgerEntry.objects.create(
        clinic=clinic,
        patient=patient,
        profile=profile,
        category=category,
        occurred_at=timezone.make_aware(datetime(2026, 6, 30, 10, 0)),
        entry_type=YakapLedgerEntry.TYPE_MEDICINE_USAGE,
        amount=Decimal("5000.00"),
        note="Prior period medicine usage",
    )
    YakapLedgerEntry.objects.create(
        clinic=clinic,
        patient=patient,
        profile=profile,
        category=category,
        occurred_at=timezone.make_aware(datetime(2026, 7, 2, 10, 0)),
        entry_type=YakapLedgerEntry.TYPE_MEDICINE_USAGE,
        amount=Decimal("750.00"),
        note="Current period medicine usage",
    )

    balance = estimated_remaining_for(profile, category, when=date(2026, 8, 15))

    assert balance["period"].period_start == date(2026, 7, 1)
    assert balance["period"].period_end == date(2027, 6, 30)
    assert balance["limit"] == Decimal("20000.00")
    assert balance["used"] == Decimal("750.00")
    assert balance["remaining"] == Decimal("19250.00")


@pytest.mark.django_db
def test_booking_snapshot_populates_rule_category_and_estimates_when_requested(clinic_setup):
    clinic, service = clinic_setup
    _settings, categories = ensure_default_yakap_setup(clinic)
    category = next(category for category in categories if category.category_type == YakapCoverageCategory.TYPE_MEDICINES)
    ServiceYakapRule.objects.create(
        clinic=clinic,
        service=service,
        category=category,
        coverage_status=ServiceYakapRule.STATUS_COVERED,
        estimated_covered_amount=Decimal("1200.00"),
    )
    patient = Patient.objects.create(clinic=clinic, full_name="Juan Dela Cruz", phone="0917-000-0001")
    appointment = create_appointment(clinic, patient, service)

    assert not PatientYakapProfile.objects.filter(clinic=clinic, patient=patient).exists()
    snapshot = yakap_services.create_appointment_yakap_snapshot(appointment, requested=True)

    assert PatientYakapProfile.objects.filter(clinic=clinic, patient=patient).exists()
    assert snapshot.category_name == "Medicines"
    assert snapshot.service_rule_status == ServiceYakapRule.STATUS_COVERED
    assert snapshot.estimated_remaining_at_booking == Decimal("20000.00")
    assert snapshot.estimated_covered_amount_at_booking == Decimal("1200.00")


@pytest.mark.django_db
def test_booking_snapshot_estimates_remaining_for_appointment_period(clinic_setup, monkeypatch):
    clinic, service = clinic_setup
    settings, categories = ensure_default_yakap_setup(clinic)
    settings.reset_month = 7
    settings.reset_day = 1
    settings.save()
    category = next(category for category in categories if category.category_type == YakapCoverageCategory.TYPE_MEDICINES)
    ServiceYakapRule.objects.create(
        clinic=clinic,
        service=service,
        category=category,
        coverage_status=ServiceYakapRule.STATUS_COVERED,
        estimated_covered_amount=Decimal("1200.00"),
    )
    patient = Patient.objects.create(clinic=clinic, full_name="Juan Dela Cruz", phone="0917-000-0001")
    profile = yakap_profile_for_patient(patient)
    YakapLedgerEntry.objects.create(
        clinic=clinic,
        patient=patient,
        profile=profile,
        category=category,
        occurred_at=timezone.make_aware(datetime(2026, 6, 20, 10, 0)),
        entry_type=YakapLedgerEntry.TYPE_MEDICINE_USAGE,
        amount=Decimal("5000.00"),
        note="Before reset usage",
    )
    starts_at = timezone.make_aware(datetime(2026, 7, 2, 10, 0))
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=service.effective_duration()),
    )
    original_localdate = yakap_services.timezone.localdate

    def fake_localdate(*args, **kwargs):
        if not args and not kwargs:
            return date(2026, 6, 15)
        return original_localdate(*args, **kwargs)

    monkeypatch.setattr(yakap_services.timezone, "localdate", fake_localdate)

    snapshot = yakap_services.create_appointment_yakap_snapshot(appointment, requested=True)

    assert snapshot.estimated_remaining_at_booking == Decimal("20000.00")


@pytest.mark.django_db
def test_booking_snapshot_does_not_create_profile_when_not_requested(clinic_setup):
    clinic, service = clinic_setup
    _settings, categories = ensure_default_yakap_setup(clinic)
    category = next(category for category in categories if category.category_type == YakapCoverageCategory.TYPE_MEDICINES)
    ServiceYakapRule.objects.create(
        clinic=clinic,
        service=service,
        category=category,
        coverage_status=ServiceYakapRule.STATUS_COVERED,
        estimated_covered_amount=Decimal("1200.00"),
    )
    patient = Patient.objects.create(clinic=clinic, full_name="Juan Dela Cruz", phone="0917-000-0001")
    appointment = create_appointment(clinic, patient, service)

    snapshot = yakap_services.create_appointment_yakap_snapshot(appointment, requested=False)

    assert not PatientYakapProfile.objects.filter(clinic=clinic, patient=patient).exists()
    assert snapshot.category_name == "Medicines"
    assert snapshot.estimated_remaining_at_booking is None
    assert snapshot.estimated_covered_amount_at_booking is None


@pytest.mark.django_db
def test_booking_snapshot_does_not_create_profile_without_yakap_rule(clinic_setup):
    clinic, service = clinic_setup
    patient = Patient.objects.create(clinic=clinic, full_name="Juan Dela Cruz", phone="0917-000-0001")
    appointment = create_appointment(clinic, patient, service)

    snapshot = yakap_services.create_appointment_yakap_snapshot(appointment, requested=True)

    assert not PatientYakapProfile.objects.filter(clinic=clinic, patient=patient).exists()
    assert snapshot.category_name == ""
    assert snapshot.estimated_remaining_at_booking is None
    assert snapshot.estimated_covered_amount_at_booking is None


@pytest.mark.django_db
def test_credit_line_period_snapshots_category_limit_and_defaults_open(clinic_setup):
    from yakap.models import YakapCreditLinePeriod

    clinic, _service = clinic_setup
    category = YakapCoverageCategory.objects.create(
        clinic=clinic,
        name="Medicines",
        category_type=YakapCoverageCategory.TYPE_MEDICINES,
        annual_limit=Decimal("20000.00"),
    )
    patient = Patient.objects.create(clinic=clinic, full_name="Juan Dela Cruz", phone="0917-000-0001")
    profile = yakap_profile_for_patient(patient)

    period = YakapCreditLinePeriod.objects.create(
        clinic=clinic,
        patient=patient,
        profile=profile,
        category=category,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
    )

    assert period.status == YakapCreditLinePeriod.STATUS_OPEN
    assert period.limit_snapshot == Decimal("20000.00")


@pytest.mark.django_db
def test_profile_records_verification_fields(clinic_setup, django_user_model):
    clinic, _service = clinic_setup
    user = django_user_model.objects.create_user(username="yakap-verifier", password="password")
    patient = Patient.objects.create(clinic=clinic, full_name="Juan Dela Cruz", phone="0917-000-0001")

    profile = PatientYakapProfile.objects.create(
        clinic=clinic,
        patient=patient,
        status=PatientYakapProfile.STATUS_PENDING_VERIFICATION,
        registered_clinic_name="Registered Clinic",
        last_verified_by=user,
        verification_method="PhilHealth portal",
        verification_reference="YAKAP-REF-001",
        consent_note="Patient consented to YAKAP verification.",
    )

    assert profile.status == PatientYakapProfile.STATUS_PENDING_VERIFICATION
    assert profile.registered_clinic_name == "Registered Clinic"
    assert profile.last_verified_by == user
    assert profile.verification_method == "PhilHealth portal"
    assert profile.verification_reference == "YAKAP-REF-001"
    assert profile.consent_note == "Patient consented to YAKAP verification."
    assert (PatientYakapProfile.STATUS_TRANSFERRED, "Transferred") in PatientYakapProfile.STATUS_CHOICES


@pytest.mark.django_db
def test_patient_yakap_profile_form_saves_allowed_verification_fields(clinic_setup):
    clinic, _service = clinic_setup
    patient = Patient.objects.create(clinic=clinic, full_name="Juan Dela Cruz", phone="0917-000-0001")
    profile = yakap_profile_for_patient(patient)
    form_class = getattr(yakap_forms, "PatientYakapProfileForm", None)
    assert form_class is not None

    form = form_class(
        data={
            "status": PatientYakapProfile.STATUS_REGISTERED_TO_THIS_CLINIC,
            "registered_clinic_name": "Demo Clinic YAKAP Desk",
            "verification_method": "PhilHealth portal",
            "verification_reference": "YAKAP-REF-001",
            "consent_note": "Patient consented to verification.",
            "staff_notes": "Bring ID on next visit.",
        },
        instance=profile,
    )

    assert form.is_valid(), form.errors
    saved = form.save()
    saved.refresh_from_db()
    assert saved.status == PatientYakapProfile.STATUS_REGISTERED_TO_THIS_CLINIC
    assert saved.registered_clinic_name == "Demo Clinic YAKAP Desk"
    assert saved.verification_method == "PhilHealth portal"
    assert saved.verification_reference == "YAKAP-REF-001"
    assert saved.consent_note == "Patient consented to verification."
    assert saved.staff_notes == "Bring ID on next visit."


def test_patient_yakap_profile_form_exposes_expected_fields():
    assert list(yakap_forms.PatientYakapProfileForm().fields) == [
        "status",
        "registered_clinic_name",
        "verification_method",
        "verification_reference",
        "consent_note",
        "staff_notes",
    ]


@pytest.mark.django_db
def test_appointment_yakap_status_form_saves_coverage_status_and_note(clinic_setup):
    clinic, service = clinic_setup
    patient = Patient.objects.create(clinic=clinic, full_name="Juan Dela Cruz", phone="0917-000-0001")
    appointment = create_appointment(clinic, patient, service)
    snapshot = AppointmentYakapSnapshot.objects.create(
        clinic=clinic,
        appointment=appointment,
        requested=True,
        coverage_status=AppointmentYakapSnapshot.STATUS_REQUESTED,
    )
    form_class = getattr(yakap_forms, "AppointmentYakapStatusForm", None)
    assert form_class is not None

    form = form_class(
        data={
            "coverage_status": AppointmentYakapSnapshot.STATUS_VERIFIED_FOR_VISIT,
            "verification_note": "Verified in clinic YAKAP workflow.",
        },
        instance=snapshot,
    )

    assert form.is_valid(), form.errors
    saved = form.save()
    saved.refresh_from_db()
    assert saved.coverage_status == AppointmentYakapSnapshot.STATUS_VERIFIED_FOR_VISIT
    assert saved.verification_note == "Verified in clinic YAKAP workflow."


def test_appointment_yakap_status_form_exposes_expected_fields():
    assert list(yakap_forms.AppointmentYakapStatusForm().fields) == [
        "coverage_status",
        "verification_note",
    ]


@pytest.mark.django_db
def test_audit_event_records_actor_action_summary(clinic_setup, django_user_model):
    from yakap.models import YakapAuditEvent

    clinic, _service = clinic_setup
    actor = django_user_model.objects.create_user(username="yakap-auditor", password="password")
    patient = Patient.objects.create(clinic=clinic, full_name="Juan Dela Cruz", phone="0917-000-0001")
    profile = yakap_profile_for_patient(patient)

    create_yakap_audit_event = getattr(yakap_services, "create_yakap_audit_event", None)
    assert callable(create_yakap_audit_event)
    event = create_yakap_audit_event(
        clinic=clinic,
        actor=actor,
        action=YakapAuditEvent.ACTION_PROFILE_STATUS_CHANGED,
        obj=profile,
        summary="Marked profile as pending verification.",
    )

    assert event.clinic == clinic
    assert event.actor == actor
    assert event.action == YakapAuditEvent.ACTION_PROFILE_STATUS_CHANGED
    assert event.object_type == "PatientYakapProfile"
    assert event.object_id == str(profile.pk)
    assert event.summary == "Marked profile as pending verification."


@pytest.mark.parametrize(
    ("balance", "low_threshold", "expected"),
    [
        (Decimal("-0.01"), Decimal("1000.00"), "negative_or_exceeded"),
        (Decimal("0.00"), Decimal("1000.00"), "zero"),
        (Decimal("999.99"), Decimal("1000.00"), "low"),
        (Decimal("1000.00"), Decimal("1000.00"), "low"),
        ({"remaining": Decimal("1000.00")}, Decimal("1000.00"), "low"),
    ],
)
def test_balance_state_for_classifies_estimated_balance(balance, low_threshold, expected):
    balance_state_for = getattr(yakap_services, "balance_state_for", None)
    assert callable(balance_state_for)
    assert balance_state_for(balance, low_threshold) == expected


@pytest.mark.django_db
def test_audit_event_create_rejects_invalid_action(clinic_setup, django_user_model):
    from yakap.models import YakapAuditEvent

    clinic, _service = clinic_setup
    actor = django_user_model.objects.create_user(username="yakap-invalid-action", password="password")

    with pytest.raises(ValidationError, match="action"):
        YakapAuditEvent.objects.create(
            clinic=clinic,
            actor=actor,
            action="invalid",
            object_type="PatientYakapProfile",
            object_id="profile-123",
            summary="Invalid audit action should not persist.",
        )


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
def test_yakap_coverage_category_form_allows_editing_existing_name(clinic_setup):
    clinic, _service = clinic_setup
    _settings, categories = ensure_default_yakap_setup(clinic)
    category = categories[0]

    form = yakap_forms.YakapCoverageCategoryForm(
        data={
            "name": category.name,
            "category_type": category.category_type,
            "annual_limit": str(category.annual_limit),
            "is_active": "on",
            "notes": category.notes,
            "sort_order": str(category.sort_order),
        },
        clinic=clinic,
        instance=category,
    )

    assert form.is_valid(), form.errors


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
def test_appointment_yakap_snapshot_rejects_negative_estimated_covered_amount(clinic_setup):
    clinic, service = clinic_setup
    patient = Patient.objects.create(clinic=clinic, full_name="Juan Dela Cruz", phone="0917-000-0001")
    appointment = create_appointment(clinic, patient, service)

    with pytest.raises(ValidationError, match="estimated_covered_amount_at_booking"):
        AppointmentYakapSnapshot.objects.create(
            clinic=clinic,
            appointment=appointment,
            estimated_covered_amount_at_booking=Decimal("-0.01"),
        )


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
def test_yakap_ledger_entry_form_scopes_reversal_choices(clinic_setup):
    clinic, _service = clinic_setup
    _settings, categories = ensure_default_yakap_setup(clinic)
    category = categories[0]
    other_category = categories[1]
    patient = Patient.objects.create(clinic=clinic, full_name="Juan Dela Cruz", phone="0917-000-0001")
    profile = yakap_profile_for_patient(patient)
    other_patient = Patient.objects.create(clinic=clinic, full_name="Maria Santos", phone="0917-000-0002")
    other_profile = yakap_profile_for_patient(other_patient)
    other_clinic = create_other_clinic(clinic)
    _other_settings, other_clinic_categories = ensure_default_yakap_setup(other_clinic)
    other_clinic_patient = Patient.objects.create(
        clinic=other_clinic,
        full_name="Other Clinic Patient",
        phone="0917-000-0003",
    )
    other_clinic_profile = yakap_profile_for_patient(other_clinic_patient)
    matching_entry = YakapLedgerEntry.objects.create(
        clinic=clinic,
        patient=patient,
        profile=profile,
        category=category,
        entry_type=YakapLedgerEntry.TYPE_SERVICE_USAGE,
        amount=Decimal("750.00"),
        note="Matching usage",
    )
    reversal_entry = YakapLedgerEntry.objects.create(
        clinic=clinic,
        patient=patient,
        profile=profile,
        category=category,
        entry_type=YakapLedgerEntry.TYPE_REVERSAL,
        amount=Decimal("100.00"),
        note="Existing reversal",
    )
    other_patient_entry = YakapLedgerEntry.objects.create(
        clinic=clinic,
        patient=other_patient,
        profile=other_profile,
        category=category,
        entry_type=YakapLedgerEntry.TYPE_SERVICE_USAGE,
        amount=Decimal("400.00"),
        note="Other patient usage",
    )
    other_category_entry = YakapLedgerEntry.objects.create(
        clinic=clinic,
        patient=patient,
        profile=profile,
        category=other_category,
        entry_type=YakapLedgerEntry.TYPE_SERVICE_USAGE,
        amount=Decimal("300.00"),
        note="Other category usage",
    )
    other_clinic_entry = YakapLedgerEntry.objects.create(
        clinic=other_clinic,
        patient=other_clinic_patient,
        profile=other_clinic_profile,
        category=other_clinic_categories[0],
        entry_type=YakapLedgerEntry.TYPE_SERVICE_USAGE,
        amount=Decimal("200.00"),
        note="Other clinic usage",
    )

    default_form = yakap_forms.YakapLedgerEntryForm(clinic)
    assert not default_form.fields["reversal_of"].required
    assert not default_form.fields["reversal_of"].queryset.exists()
    try:
        scoped_form = yakap_forms.YakapLedgerEntryForm(clinic, patient=patient, category=category)
    except TypeError as exc:
        pytest.fail(str(exc))

    reversal_choice_ids = set(scoped_form.fields["reversal_of"].queryset.values_list("pk", flat=True))
    assert reversal_choice_ids == {matching_entry.pk}
    assert reversal_entry.pk not in reversal_choice_ids
    assert other_patient_entry.pk not in reversal_choice_ids
    assert other_category_entry.pk not in reversal_choice_ids
    assert other_clinic_entry.pk not in reversal_choice_ids


@pytest.mark.django_db
def test_yakap_ledger_entry_form_exposes_expected_fields(clinic_setup):
    clinic, _service = clinic_setup

    assert list(yakap_forms.YakapLedgerEntryForm(clinic).fields) == [
        "category",
        "entry_type",
        "amount",
        "verification_status",
        "occurred_at",
        "external_reference",
        "reversal_of",
        "note",
    ]


@pytest.mark.django_db
def test_yakap_ledger_entry_form_renders_datetime_local_occurred_at_value(clinic_setup):
    clinic, _service = clinic_setup
    _settings, categories = ensure_default_yakap_setup(clinic)
    patient = Patient.objects.create(clinic=clinic, full_name="Juan Dela Cruz", phone="0917-000-0001")
    profile = yakap_profile_for_patient(patient)
    entry = YakapLedgerEntry.objects.create(
        clinic=clinic,
        patient=patient,
        profile=profile,
        category=categories[0],
        occurred_at=timezone.make_aware(datetime(2026, 8, 1, 10, 30)),
        entry_type=YakapLedgerEntry.TYPE_SERVICE_USAGE,
        amount=Decimal("750.00"),
        note="Rendered datetime-local value",
    )

    form = yakap_forms.YakapLedgerEntryForm(clinic, instance=entry)

    assert 'value="2026-08-01T10:30"' in str(form["occurred_at"])


@pytest.mark.django_db
def test_clinic_yakap_settings_create_rejects_impossible_reset_date(clinic_setup):
    clinic, _service = clinic_setup

    with pytest.raises(ValidationError, match="reset_day"):
        ClinicYakapSettings.objects.create(clinic=clinic, reset_month=2, reset_day=31)


@pytest.mark.django_db
def test_yakap_ledger_usage_updates_estimated_remaining(clinic_setup):
    clinic, _service = clinic_setup
    _settings, categories = ensure_default_yakap_setup(clinic)
    category = next(category for category in categories if category.category_type == YakapCoverageCategory.TYPE_MEDICINES)
    patient = Patient.objects.create(clinic=clinic, full_name="Juan Dela Cruz", phone="0917-000-0000")
    profile = yakap_profile_for_patient(patient)

    YakapLedgerEntry.objects.create(
        clinic=clinic,
        patient=patient,
        profile=profile,
        category=category,
        occurred_at=timezone.make_aware(datetime(2026, 8, 1, 10, 0)),
        entry_type=YakapLedgerEntry.TYPE_SERVICE_USAGE,
        amount=Decimal("750.00"),
        note="General consultation usage",
    )

    balance = estimated_remaining_for(profile, category, when=date(2026, 8, 15))

    assert balance["period"].period_start == date(2026, 1, 1)
    assert balance["period"].period_end == date(2026, 12, 31)
    assert balance["limit"] == Decimal("20000.00")
    assert balance["used"] == Decimal("750.00")
    assert balance["remaining"] == Decimal("19250.00")


def test_yakap_export_form_validates_date_range():
    form_class = getattr(yakap_forms, "YakapExportForm", None)
    assert form_class is not None
    invalid_form = form_class(data={"started_at": "2026-08-02", "ended_at": "2026-08-01"})

    assert not invalid_form.is_valid()
    assert "ended_at" in invalid_form.errors

    valid_form = form_class(data={"started_at": "2026-08-01", "ended_at": "2026-08-02"})
    assert valid_form.is_valid(), valid_form.errors
    assert valid_form.cleaned_data["started_at"] == date(2026, 8, 1)
    assert valid_form.cleaned_data["ended_at"] == date(2026, 8, 2)
