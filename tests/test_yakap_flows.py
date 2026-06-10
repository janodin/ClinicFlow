from decimal import Decimal
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment
from clinics.models import Clinic, ClinicGroup, ClinicMembership
from patients.models import Patient
from scheduling.utils import generate_slots
from yakap.models import (
    AppointmentYakapSnapshot,
    ClinicYakapSettings,
    PatientYakapProfile,
    ServiceYakapRule,
    YakapAuditEvent,
    YakapCoverageCategory,
    YakapCreditLinePeriod,
    YakapLedgerEntry,
)
from yakap.services import create_appointment_yakap_snapshot, ensure_default_yakap_setup, yakap_profile_for_patient


def _yakap_settings_post_data(**overrides):
    data = {
        "_form": "settings",
        "is_enabled": "on",
        "program_label": "YAKAP",
        "public_promo_headline": "YAKAP care estimate",
        "public_promo_body": "Ask the clinic to estimate covered primary care benefits.",
        "public_disclaimer": "Subject to PhilHealth and clinic verification.",
        "internal_disclaimer": "Staff must verify YAKAP eligibility before service.",
        "verification_instructions": "Check the clinic PhilHealth workflow before service.",
        "default_annual_credit": "20000.00",
        "medicine_annual_limit_default": "20000.00",
        "default_non_medicine_limit": "0.00",
        "low_balance_threshold_amount": "1000.00",
        "verification_stale_after_days": "30",
        "reset_month": "1",
        "reset_day": "1",
    }
    data.update(overrides)
    return data


def _enable_yakap_settings(client, clinic, **overrides):
    client.force_login(clinic.group.owner)
    data = _yakap_settings_post_data(**overrides)
    response = client.post(reverse("dashboard:yakap"), data)
    assert response.status_code == 302
    client.logout()


def _first_booking_slot(clinic, service):
    target_date = timezone.localdate() + timedelta(days=1)
    slots = generate_slots(clinic, service, target_date)
    assert slots
    return slots[0]


def _widget_booking_payload(service, slot, **overrides):
    data = {
        "service": str(service.id),
        "starts_at": slot["starts_at"].isoformat(),
        "full_name": "Juan Dela Cruz",
        "phone": "0917-000-1234",
        "email": "juan@example.com",
        "reason": "Primary care visit",
    }
    data.update(overrides)
    return data


def _create_patient_appointment(clinic, service, *, full_name="Maria Santos"):
    patient = Patient.objects.create(
        clinic=clinic,
        full_name=full_name,
        phone="0917-555-0101",
        email="maria@example.com",
    )
    starts_at = timezone.now() + timedelta(days=3)
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=service.duration_minutes),
        source=Appointment.SOURCE_STAFF,
        reason="YAKAP ledger visit",
    )
    return patient, appointment


def _create_yakap_requested_appointment(
    clinic,
    service,
    *,
    full_name="YAKAP Request Patient",
    status=AppointmentYakapSnapshot.STATUS_REQUESTED,
):
    patient, appointment = _create_patient_appointment(clinic, service, full_name=full_name)
    snapshot = create_appointment_yakap_snapshot(appointment, requested=True)
    snapshot.coverage_status = status
    snapshot.save()
    return patient, appointment, snapshot


def _yakap_ledger_post_data(category, **overrides):
    data = {
        "category": str(category.id),
        "entry_type": YakapLedgerEntry.TYPE_SERVICE_USAGE,
        "amount": "300.00",
        "verification_status": YakapLedgerEntry.VERIFICATION_VERIFIED,
        "occurred_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
        "note": "Verified in clinic workflow.",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_yakap_dashboard_requires_login(client):
    response = client.get(reverse("dashboard:yakap"))

    assert response.status_code == 302


@pytest.mark.django_db
def test_yakap_dashboard_creates_default_settings(client, clinic_setup):
    clinic, _service = clinic_setup
    client.force_login(clinic.group.owner)

    response = client.get(reverse("dashboard:yakap"))

    assert response.status_code == 200
    assert ClinicYakapSettings.objects.filter(clinic=clinic).exists()
    assert YakapCoverageCategory.objects.filter(clinic=clinic, name="Medicines").exists()
    assert b"Estimated YAKAP coverage" in response.content


@pytest.mark.django_db
def test_yakap_dashboard_shows_requested_unverified_appointments(client, clinic_setup):
    clinic, service = clinic_setup
    client.force_login(clinic.group.owner)
    client.get(reverse("dashboard:yakap"))
    patient = Patient.objects.create(clinic=clinic, full_name="Risk Patient", phone="09170005555")
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=timezone.now() + timezone.timedelta(days=2),
        ends_at=timezone.now() + timezone.timedelta(days=2, minutes=30),
    )
    create_appointment_yakap_snapshot(appointment, requested=True)

    response = client.get(reverse("dashboard:yakap"))

    assert response.status_code == 200
    assert b"Risk Patient" in response.content
    assert b"Unverified YAKAP requests" in response.content
    assert b"Review" in response.content
    assert reverse("dashboard:appointment_detail", args=[appointment.id]).encode() in response.content


@pytest.mark.django_db
def test_yakap_dashboard_queue_includes_needs_verification_requests(client, clinic_setup):
    clinic, service = clinic_setup
    _patient, appointment, snapshot = _create_yakap_requested_appointment(
        clinic,
        service,
        full_name="Needs Verification Patient",
        status=AppointmentYakapSnapshot.STATUS_NEEDS_VERIFICATION,
    )
    client.force_login(clinic.group.owner)

    response = client.get(reverse("dashboard:yakap"))

    assert response.status_code == 200
    assert b"Needs Verification Patient" in response.content
    assert b"Needs verification" in response.content
    assert reverse("dashboard:appointment_detail", args=[appointment.id]).encode() in response.content
    snapshot.refresh_from_db()
    assert snapshot.coverage_status == AppointmentYakapSnapshot.STATUS_NEEDS_VERIFICATION


@pytest.mark.django_db
def test_yakap_dashboard_queue_includes_unverified_requests(client, clinic_setup):
    clinic, service = clinic_setup
    _patient, appointment, snapshot = _create_yakap_requested_appointment(
        clinic,
        service,
        full_name="Unverified Request Patient",
        status=AppointmentYakapSnapshot.STATUS_UNVERIFIED,
    )
    client.force_login(clinic.group.owner)

    response = client.get(reverse("dashboard:yakap"))

    assert response.status_code == 200
    assert b"Unverified Request Patient" in response.content
    assert b"Review" in response.content
    assert reverse("dashboard:appointment_detail", args=[appointment.id]).encode() in response.content
    snapshot.refresh_from_db()
    assert snapshot.coverage_status == AppointmentYakapSnapshot.STATUS_UNVERIFIED


@pytest.mark.django_db
def test_yakap_dashboard_rejects_staff_without_settings_permission(client, clinic_setup):
    clinic, _service = clinic_setup
    User = get_user_model()
    staff = User.objects.create_user(username="yakap-staff@example.com", email="yakap-staff@example.com")
    ClinicMembership.objects.create(clinic=clinic, user=staff, role=ClinicMembership.ROLE_STAFF)
    client.force_login(staff)

    response = client.get(reverse("dashboard:yakap"))

    assert response.status_code == 403


@pytest.mark.django_db
def test_yakap_dashboard_post_rejects_staff_without_settings_permission(client, clinic_setup):
    clinic, _service = clinic_setup
    User = get_user_model()
    staff = User.objects.create_user(username="yakap-staff-post@example.com", email="yakap-staff-post@example.com")
    ClinicMembership.objects.create(clinic=clinic, user=staff, role=ClinicMembership.ROLE_STAFF)
    client.force_login(staff)

    response = client.post(reverse("dashboard:yakap"), _yakap_settings_post_data())

    assert response.status_code == 403


@pytest.mark.django_db
def test_yakap_settings_update_is_clinic_scoped(client, clinic_setup):
    clinic, _service = clinic_setup
    client.force_login(clinic.group.owner)

    response = client.post(
        reverse("dashboard:yakap"),
        _yakap_settings_post_data(
            public_promo_headline="Estimated YAKAP coverage",
            public_promo_body="Patients can ask staff about estimated YAKAP coverage.",
            public_disclaimer="Coverage is public guidance only and requires clinic verification.",
            internal_disclaimer="Staff must verify eligibility before honoring estimates.",
            verification_instructions="Check the clinic PhilHealth workflow before service.",
            default_annual_credit="25000.00",
        ),
    )

    assert response.status_code == 302
    settings = ClinicYakapSettings.objects.get(clinic=clinic)
    assert settings.is_enabled is True
    assert settings.default_annual_credit == Decimal("25000.00")


@pytest.mark.django_db
def test_widget_shows_yakap_promo_when_enabled(client, clinic_setup):
    clinic, _service = clinic_setup
    _enable_yakap_settings(
        client,
        clinic,
        public_promo_headline="Custom YAKAP clinic estimate",
        public_promo_body="Patients can request an estimate before their visit.",
        public_disclaimer="Custom YAKAP disclaimer requires clinic verification.",
    )

    response = client.get(reverse("widget:home", args=[clinic.slug]))

    assert response.status_code == 200
    assert b"Custom YAKAP clinic estimate" in response.content
    assert b"Custom YAKAP disclaimer requires clinic verification." in response.content


@pytest.mark.django_db
def test_widget_booking_creates_yakap_snapshot_when_enabled_and_requested(client, clinic_setup):
    clinic, service = clinic_setup
    _enable_yakap_settings(client, clinic)
    client.force_login(clinic.group.owner)
    client.get(reverse("dashboard:yakap"))
    category = YakapCoverageCategory.objects.get(clinic=clinic, name="Primary Care")
    client.logout()
    rule = ServiceYakapRule.objects.create(
        clinic=clinic,
        service=service,
        category=category,
        coverage_status=ServiceYakapRule.STATUS_COVERED,
    )
    slot = _first_booking_slot(clinic, service)

    response = client.post(
        reverse("widget:book", args=[clinic.slug]),
        _widget_booking_payload(service, slot, yakap_requested="on"),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    appointment = Appointment.objects.get(clinic=clinic, service=service, patient__full_name="Juan Dela Cruz")
    snapshot = AppointmentYakapSnapshot.objects.get(appointment=appointment)
    assert snapshot.requested is True
    assert snapshot.coverage_status == AppointmentYakapSnapshot.STATUS_REQUESTED
    assert snapshot.service_rule_status == rule.coverage_status
    assert snapshot.category_name == category.name


@pytest.mark.django_db
def test_widget_booking_ignores_yakap_intent_when_disabled(client, clinic_setup):
    clinic, service = clinic_setup
    slot = _first_booking_slot(clinic, service)

    response = client.post(
        reverse("widget:book", args=[clinic.slug]),
        _widget_booking_payload(service, slot, yakap_requested="on"),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    appointment = Appointment.objects.get(clinic=clinic, service=service, patient__full_name="Juan Dela Cruz")
    assert not AppointmentYakapSnapshot.objects.filter(appointment=appointment).exists()


@pytest.mark.django_db
def test_yakap_settings_invalid_post_renders_errors_without_saving(client, clinic_setup):
    clinic, _service = clinic_setup
    settings = ClinicYakapSettings.objects.create(clinic=clinic)
    client.force_login(clinic.group.owner)

    response = client.post(
        reverse("dashboard:yakap"),
        _yakap_settings_post_data(
            public_promo_headline="Updated headline",
            public_promo_body="Updated body",
            public_disclaimer="Updated public disclaimer",
            internal_disclaimer="Updated internal disclaimer",
            verification_instructions="Updated verification steps",
            default_annual_credit="25000.00",
            reset_month="2",
            reset_day="31",
        ),
    )

    assert response.status_code == 200
    assert b"Reset day must be valid for the reset month" in response.content
    settings.refresh_from_db()
    assert settings.is_enabled is False
    assert settings.public_promo_headline == "Use your PhilHealth YAKAP benefits"
    assert settings.default_annual_credit == Decimal("20000.00")


@pytest.mark.django_db
def test_yakap_category_create_uses_active_clinic_not_posted_clinic(client, clinic_setup):
    clinic, _service = clinic_setup
    other_group = ClinicGroup.objects.create(name="Other Clinic Group", owner=clinic.group.owner)
    other_clinic = Clinic.objects.create(group=other_group, name="Other Clinic", slug="other-yakap-flow")
    client.force_login(clinic.group.owner)

    response = client.post(
        reverse("dashboard:yakap"),
        {
            "_form": "category",
            "clinic": str(other_clinic.id),
            "name": "Dental",
            "category_type": YakapCoverageCategory.TYPE_OTHER,
            "annual_limit": "5000.00",
            "is_active": "on",
            "notes": "Clinic-scoped category",
            "sort_order": "5",
        },
    )

    assert response.status_code == 302
    category = YakapCoverageCategory.objects.get(clinic=clinic, name="Dental")
    assert category.annual_limit == Decimal("5000.00")
    assert not YakapCoverageCategory.objects.filter(clinic=other_clinic, name="Dental").exists()


@pytest.mark.django_db
def test_yakap_duplicate_category_returns_form_error_without_creating_row(client, clinic_setup):
    clinic, _service = clinic_setup
    YakapCoverageCategory.objects.create(
        clinic=clinic,
        name="Dental",
        category_type=YakapCoverageCategory.TYPE_OTHER,
        annual_limit=Decimal("5000.00"),
        sort_order=5,
    )
    client.force_login(clinic.group.owner)
    client.raise_request_exception = False

    response = client.post(
        reverse("dashboard:yakap"),
        {
            "_form": "category",
            "name": "Dental",
            "category_type": YakapCoverageCategory.TYPE_OTHER,
            "annual_limit": "7500.00",
            "is_active": "on",
            "notes": "Duplicate should show a form error.",
            "sort_order": "6",
        },
    )

    assert response.status_code == 200
    assert b"already exists" in response.content
    assert YakapCoverageCategory.objects.filter(clinic=clinic, name="Dental").count() == 1


@pytest.mark.django_db
def test_yakap_invalid_category_post_renders_errors_without_saving(client, clinic_setup):
    clinic, _service = clinic_setup
    client.force_login(clinic.group.owner)

    response = client.post(
        reverse("dashboard:yakap"),
        {
            "_form": "category",
            "name": "Optical",
            "category_type": YakapCoverageCategory.TYPE_OTHER,
            "annual_limit": "-1.00",
            "is_active": "on",
            "notes": "Invalid negative limit.",
            "sort_order": "7",
        },
    )

    assert response.status_code == 200
    assert b"Ensure this value is greater than or equal" in response.content
    assert not YakapCoverageCategory.objects.filter(clinic=clinic, name="Optical").exists()


@pytest.mark.django_db
def test_staff_can_add_yakap_ledger_entry_from_appointment(client, clinic_setup):
    clinic, service = clinic_setup
    client.force_login(clinic.group.owner)
    client.get(reverse("dashboard:yakap"))
    category = YakapCoverageCategory.objects.get(clinic=clinic, name="Primary Care")
    category.annual_limit = Decimal("20000.00")
    category.save(update_fields=["annual_limit", "updated_at"])
    _patient, appointment = _create_patient_appointment(clinic, service)

    response = client.post(
        reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]),
        _yakap_ledger_post_data(category),
    )

    assert response.status_code == 302
    entry = appointment.yakap_ledger_entries.get()
    assert entry.amount == Decimal("300.00")
    assert entry.category == category
    assert entry.entry_type == YakapLedgerEntry.TYPE_SERVICE_USAGE
    assert entry.verification_status == YakapLedgerEntry.VERIFICATION_VERIFIED
    assert entry.created_by == clinic.group.owner


@pytest.mark.django_db
def test_yakap_ledger_entry_marks_verified_request_as_posted(client, clinic_setup):
    clinic, service = clinic_setup
    client.force_login(clinic.group.owner)
    client.get(reverse("dashboard:yakap"))
    category = YakapCoverageCategory.objects.get(clinic=clinic, name="Primary Care")
    category.annual_limit = Decimal("20000.00")
    category.save(update_fields=["annual_limit", "updated_at"])
    _patient, appointment, snapshot = _create_yakap_requested_appointment(
        clinic,
        service,
        status=AppointmentYakapSnapshot.STATUS_VERIFIED_FOR_VISIT,
    )

    response = client.post(
        reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]),
        _yakap_ledger_post_data(category),
    )

    assert response.status_code == 302
    snapshot.refresh_from_db()
    assert snapshot.coverage_status == AppointmentYakapSnapshot.STATUS_POSTED


@pytest.mark.django_db
def test_yakap_ledger_entry_marks_existing_snapshot_as_posted(client, clinic_setup):
    clinic, service = clinic_setup
    client.force_login(clinic.group.owner)
    client.get(reverse("dashboard:yakap"))
    category = YakapCoverageCategory.objects.get(clinic=clinic, name="Primary Care")
    category.annual_limit = Decimal("20000.00")
    category.save(update_fields=["annual_limit", "updated_at"])
    _patient, appointment, snapshot = _create_yakap_requested_appointment(
        clinic,
        service,
        status=AppointmentYakapSnapshot.STATUS_NOT_ELIGIBLE,
    )

    response = client.post(
        reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]),
        _yakap_ledger_post_data(category),
    )

    assert response.status_code == 302
    snapshot.refresh_from_db()
    assert snapshot.coverage_status == AppointmentYakapSnapshot.STATUS_POSTED


@pytest.mark.django_db
def test_successful_appointment_ledger_entry_creates_credit_line_period_snapshot(client, clinic_setup):
    clinic, service = clinic_setup
    client.force_login(clinic.group.owner)
    _settings, categories = ensure_default_yakap_setup(clinic)
    category = next(item for item in categories if item.name == "Medicines")
    patient, appointment = _create_patient_appointment(clinic, service)

    response = client.post(
        reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]),
        _yakap_ledger_post_data(category, entry_type=YakapLedgerEntry.TYPE_MEDICINE_USAGE),
    )

    assert response.status_code == 302
    period = YakapCreditLinePeriod.objects.get(patient=patient, category=category)
    assert period.profile == patient.yakap_profile
    assert period.limit_snapshot == Decimal("20000.00")
    category.annual_limit = Decimal("15000.00")
    category.save(update_fields=["annual_limit", "updated_at"])
    period.refresh_from_db()
    assert period.limit_snapshot == Decimal("20000.00")


@pytest.mark.django_db
def test_appointment_detail_ledger_form_includes_occurred_at(client, clinic_setup):
    clinic, service = clinic_setup
    _patient, appointment = _create_patient_appointment(clinic, service)
    client.force_login(clinic.group.owner)

    response = client.get(reverse("dashboard:appointment_detail", args=[appointment.id]))

    assert response.status_code == 200
    assert b'name="occurred_at"' in response.content


@pytest.mark.django_db
def test_appointment_detail_ledger_form_includes_reference_and_reversal_fields(client, clinic_setup):
    clinic, service = clinic_setup
    _patient, appointment = _create_patient_appointment(clinic, service)
    client.force_login(clinic.group.owner)

    response = client.get(reverse("dashboard:appointment_detail", args=[appointment.id]))

    assert response.status_code == 200
    assert b'name="external_reference"' in response.content
    assert b'name="reversal_of"' in response.content


@pytest.mark.django_db
def test_staff_can_post_yakap_reversal_linked_to_original_entry_from_appointment(client, clinic_setup):
    clinic, service = clinic_setup
    client.force_login(clinic.group.owner)
    _settings, categories = ensure_default_yakap_setup(clinic)
    category = next(item for item in categories if item.name == "Medicines")
    patient, appointment = _create_patient_appointment(clinic, service)
    profile = yakap_profile_for_patient(patient)
    original_entry = YakapLedgerEntry.objects.create(
        clinic=clinic,
        patient=patient,
        profile=profile,
        appointment=appointment,
        service=service,
        category=category,
        entry_type=YakapLedgerEntry.TYPE_MEDICINE_USAGE,
        amount=Decimal("300.00"),
        verification_status=YakapLedgerEntry.VERIFICATION_VERIFIED,
        note="Original verified usage.",
        created_by=clinic.group.owner,
    )

    response = client.post(
        reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]),
        _yakap_ledger_post_data(
            category,
            entry_type=YakapLedgerEntry.TYPE_REVERSAL,
            amount="100.00",
            external_reference="REV-123",
            reversal_of=str(original_entry.pk),
            note="Partial reversal after clinic review.",
        ),
    )

    assert response.status_code == 302
    reversal = YakapLedgerEntry.objects.get(appointment=appointment, entry_type=YakapLedgerEntry.TYPE_REVERSAL)
    assert reversal.reversal_of == original_entry
    assert reversal.external_reference == "REV-123"
    assert reversal.amount == Decimal("100.00")


@pytest.mark.django_db
def test_staff_role_cannot_post_yakap_reversal(client, clinic_setup):
    clinic, service = clinic_setup
    _settings, categories = ensure_default_yakap_setup(clinic)
    category = next(item for item in categories if item.name == "Medicines")
    patient, appointment = _create_patient_appointment(clinic, service)
    profile = yakap_profile_for_patient(patient)
    original_entry = YakapLedgerEntry.objects.create(
        clinic=clinic,
        patient=patient,
        profile=profile,
        appointment=appointment,
        service=service,
        category=category,
        entry_type=YakapLedgerEntry.TYPE_MEDICINE_USAGE,
        amount=Decimal("300.00"),
        verification_status=YakapLedgerEntry.VERIFICATION_VERIFIED,
        note="Original verified usage.",
        created_by=clinic.group.owner,
    )
    User = get_user_model()
    staff = User.objects.create_user(username="yakap-reversal-staff@example.com", email="yakap-reversal-staff@example.com")
    ClinicMembership.objects.create(clinic=clinic, user=staff, role=ClinicMembership.ROLE_STAFF)
    client.force_login(staff)

    response = client.post(
        reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]),
        _yakap_ledger_post_data(
            category,
            entry_type=YakapLedgerEntry.TYPE_REVERSAL,
            amount="100.00",
            reversal_of=str(original_entry.pk),
            note="Staff should not reverse entries.",
        ),
    )

    assert response.status_code == 403
    assert not YakapLedgerEntry.objects.filter(appointment=appointment, entry_type=YakapLedgerEntry.TYPE_REVERSAL).exists()


@pytest.mark.django_db
def test_linked_yakap_reversal_must_match_original_entry_period(client, clinic_setup):
    clinic, service = clinic_setup
    client.force_login(clinic.group.owner)
    _settings, categories = ensure_default_yakap_setup(clinic)
    category = next(item for item in categories if item.name == "Medicines")
    patient, appointment = _create_patient_appointment(clinic, service)
    profile = yakap_profile_for_patient(patient)
    prior_period_usage_at = timezone.now() - timedelta(days=370)
    original_entry = YakapLedgerEntry.objects.create(
        clinic=clinic,
        patient=patient,
        profile=profile,
        appointment=appointment,
        service=service,
        category=category,
        entry_type=YakapLedgerEntry.TYPE_MEDICINE_USAGE,
        amount=Decimal("300.00"),
        verification_status=YakapLedgerEntry.VERIFICATION_VERIFIED,
        occurred_at=prior_period_usage_at,
        note="Prior-period usage.",
        created_by=clinic.group.owner,
    )
    YakapLedgerEntry.objects.create(
        clinic=clinic,
        patient=patient,
        profile=profile,
        appointment=appointment,
        service=service,
        category=category,
        entry_type=YakapLedgerEntry.TYPE_MEDICINE_USAGE,
        amount=Decimal("500.00"),
        verification_status=YakapLedgerEntry.VERIFICATION_VERIFIED,
        note="Current-period usage.",
        created_by=clinic.group.owner,
    )

    response = client.post(
        reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]),
        _yakap_ledger_post_data(
            category,
            entry_type=YakapLedgerEntry.TYPE_REVERSAL,
            amount="100.00",
            reversal_of=str(original_entry.pk),
            note="Cross-period linked reversal should be rejected.",
        ),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert b"same benefit period" in response.content
    assert not YakapLedgerEntry.objects.filter(
        appointment=appointment,
        entry_type=YakapLedgerEntry.TYPE_REVERSAL,
        note="Cross-period linked reversal should be rejected.",
    ).exists()


@pytest.mark.django_db
def test_linked_yakap_reversal_cannot_cumulatively_exceed_original_entry(client, clinic_setup):
    clinic, service = clinic_setup
    client.force_login(clinic.group.owner)
    _settings, categories = ensure_default_yakap_setup(clinic)
    category = next(item for item in categories if item.name == "Medicines")
    patient, appointment = _create_patient_appointment(clinic, service)
    profile = yakap_profile_for_patient(patient)
    original_entry = YakapLedgerEntry.objects.create(
        clinic=clinic,
        patient=patient,
        profile=profile,
        appointment=appointment,
        service=service,
        category=category,
        entry_type=YakapLedgerEntry.TYPE_MEDICINE_USAGE,
        amount=Decimal("300.00"),
        verification_status=YakapLedgerEntry.VERIFICATION_VERIFIED,
        note="Original verified usage.",
        created_by=clinic.group.owner,
    )
    YakapLedgerEntry.objects.create(
        clinic=clinic,
        patient=patient,
        profile=profile,
        appointment=appointment,
        service=service,
        category=category,
        entry_type=YakapLedgerEntry.TYPE_MEDICINE_USAGE,
        amount=Decimal("500.00"),
        verification_status=YakapLedgerEntry.VERIFICATION_VERIFIED,
        note="Separate usage keeps current used positive.",
        created_by=clinic.group.owner,
    )
    YakapLedgerEntry.objects.create(
        clinic=clinic,
        patient=patient,
        profile=profile,
        appointment=appointment,
        service=service,
        category=category,
        entry_type=YakapLedgerEntry.TYPE_REVERSAL,
        amount=Decimal("250.00"),
        verification_status=YakapLedgerEntry.VERIFICATION_VERIFIED,
        reversal_of=original_entry,
        note="Existing linked reversal.",
        created_by=clinic.group.owner,
    )

    response = client.post(
        reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]),
        _yakap_ledger_post_data(
            category,
            entry_type=YakapLedgerEntry.TYPE_REVERSAL,
            amount="100.00",
            reversal_of=str(original_entry.pk),
            note="Cumulative linked reversal should be rejected.",
        ),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert b"remaining amount on the original entry" in response.content
    assert not YakapLedgerEntry.objects.filter(
        appointment=appointment,
        entry_type=YakapLedgerEntry.TYPE_REVERSAL,
        note="Cumulative linked reversal should be rejected.",
    ).exists()


@pytest.mark.django_db
def test_yakap_ledger_oversized_reversal_rerenders_error_without_saving(client, clinic_setup):
    clinic, service = clinic_setup
    client.force_login(clinic.group.owner)
    client.get(reverse("dashboard:yakap"))
    category = YakapCoverageCategory.objects.get(clinic=clinic, name="Primary Care")
    patient, appointment = _create_patient_appointment(clinic, service)
    profile = yakap_profile_for_patient(patient)
    YakapLedgerEntry.objects.create(
        clinic=clinic,
        patient=patient,
        profile=profile,
        appointment=appointment,
        service=service,
        category=category,
        entry_type=YakapLedgerEntry.TYPE_SERVICE_USAGE,
        amount=Decimal("300.00"),
        verification_status=YakapLedgerEntry.VERIFICATION_VERIFIED,
        note="Existing verified usage.",
        created_by=clinic.group.owner,
    )
    client.raise_request_exception = False

    response = client.post(
        reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]),
        _yakap_ledger_post_data(
            category,
            entry_type=YakapLedgerEntry.TYPE_REVERSAL,
            amount="999.00",
            note="Oversized reversal should be rejected.",
        ),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert b"Reversal cannot exceed current estimated used" in response.content
    assert not YakapLedgerEntry.objects.filter(
        appointment=appointment,
        category=category,
        entry_type=YakapLedgerEntry.TYPE_REVERSAL,
    ).exists()


@pytest.mark.django_db
def test_yakap_ledger_cross_period_reversal_rerenders_error_without_saving(client, clinic_setup):
    clinic, service = clinic_setup
    client.force_login(clinic.group.owner)
    _settings, categories = ensure_default_yakap_setup(clinic)
    category = next(item for item in categories if item.name == "Medicines")
    patient, appointment = _create_patient_appointment(clinic, service)
    profile = yakap_profile_for_patient(patient)
    prior_period_usage_at = timezone.now() - timedelta(days=370)
    YakapLedgerEntry.objects.create(
        clinic=clinic,
        patient=patient,
        profile=profile,
        appointment=appointment,
        service=service,
        category=category,
        entry_type=YakapLedgerEntry.TYPE_MEDICINE_USAGE,
        amount=Decimal("300.00"),
        verification_status=YakapLedgerEntry.VERIFICATION_VERIFIED,
        occurred_at=prior_period_usage_at,
        note="Prior-period usage.",
        created_by=clinic.group.owner,
    )

    response = client.post(
        reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]),
        _yakap_ledger_post_data(
            category,
            entry_type=YakapLedgerEntry.TYPE_REVERSAL,
            amount="100.00",
            note="Current-period reversal should be rejected.",
        ),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert b"Reversal cannot exceed current estimated used" in response.content
    assert not YakapLedgerEntry.objects.filter(
        appointment=appointment,
        category=category,
        entry_type=YakapLedgerEntry.TYPE_REVERSAL,
    ).exists()


@pytest.mark.django_db
def test_ledger_over_limit_requires_confirmation_when_hard_block_disabled(client, clinic_setup):
    clinic, service = clinic_setup
    client.force_login(clinic.group.owner)
    settings, categories = ensure_default_yakap_setup(clinic)
    settings.hard_block_exceeded = False
    settings.save(update_fields=["hard_block_exceeded", "updated_at"])
    category = next(item for item in categories if item.name == "Medicines")
    patient, appointment = _create_patient_appointment(clinic, service)

    response = client.post(
        reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]),
        _yakap_ledger_post_data(category, entry_type=YakapLedgerEntry.TYPE_MEDICINE_USAGE, amount="25000.00"),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert b"exceeds estimated remaining" in response.content
    assert not YakapLedgerEntry.objects.filter(appointment=appointment).exists()
    assert not PatientYakapProfile.objects.filter(patient=patient).exists()
    assert not YakapCreditLinePeriod.objects.filter(patient=patient, category=category).exists()

    confirmed = _yakap_ledger_post_data(category, entry_type=YakapLedgerEntry.TYPE_MEDICINE_USAGE, amount="25000.00")
    confirmed["confirm_over_limit"] = "on"
    response = client.post(reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]), confirmed, HTTP_HX_REQUEST="true")

    assert response.status_code == 200
    assert YakapLedgerEntry.objects.filter(appointment=appointment, amount=Decimal("25000.00")).exists()
    assert clinic.yakap_audit_events.filter(action="ledger_posted").exists()


@pytest.mark.django_db
def test_ledger_over_limit_is_blocked_when_hard_block_enabled(client, clinic_setup):
    clinic, service = clinic_setup
    client.force_login(clinic.group.owner)
    settings, categories = ensure_default_yakap_setup(clinic)
    settings.hard_block_exceeded = True
    settings.save(update_fields=["hard_block_exceeded", "updated_at"])
    category = next(item for item in categories if item.name == "Medicines")
    patient, appointment = _create_patient_appointment(clinic, service)
    post_data = _yakap_ledger_post_data(category, entry_type=YakapLedgerEntry.TYPE_MEDICINE_USAGE, amount="25000.00")
    post_data["confirm_over_limit"] = "on"

    response = client.post(reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]), post_data, HTTP_HX_REQUEST="true")

    assert response.status_code == 200
    assert b"blocked by clinic YAKAP settings" in response.content
    assert not YakapLedgerEntry.objects.filter(appointment=appointment).exists()
    assert not PatientYakapProfile.objects.filter(patient=patient).exists()
    assert not YakapCreditLinePeriod.objects.filter(patient=patient, category=category).exists()


@pytest.mark.django_db
def test_ledger_over_limit_uses_entry_period_not_current_period(client, clinic_setup):
    clinic, service = clinic_setup
    client.force_login(clinic.group.owner)
    settings, categories = ensure_default_yakap_setup(clinic)
    settings.hard_block_exceeded = False
    settings.save(update_fields=["hard_block_exceeded", "updated_at"])
    category = next(item for item in categories if item.name == "Medicines")
    patient, appointment = _create_patient_appointment(clinic, service)
    profile = yakap_profile_for_patient(patient)
    future_usage_at = timezone.now() + timedelta(days=370)
    YakapLedgerEntry.objects.create(
        clinic=clinic,
        patient=patient,
        profile=profile,
        appointment=appointment,
        service=service,
        category=category,
        entry_type=YakapLedgerEntry.TYPE_MEDICINE_USAGE,
        amount=Decimal("10000.00"),
        verification_status=YakapLedgerEntry.VERIFICATION_VERIFIED,
        occurred_at=future_usage_at,
        note="Future-period usage already posted.",
        created_by=clinic.group.owner,
    )

    response = client.post(
        reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]),
        _yakap_ledger_post_data(
            category,
            entry_type=YakapLedgerEntry.TYPE_MEDICINE_USAGE,
            amount="15000.00",
            occurred_at=future_usage_at.strftime("%Y-%m-%dT%H:%M"),
        ),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert b"exceeds estimated remaining" in response.content
    assert not YakapLedgerEntry.objects.filter(appointment=appointment, amount=Decimal("15000.00")).exists()


@pytest.mark.django_db
def test_staff_without_daily_ops_permission_cannot_add_yakap_ledger_entry(client, clinic_setup):
    clinic, service = clinic_setup
    User = get_user_model()
    viewer = User.objects.create_user(username="yakap-viewer@example.com", email="yakap-viewer@example.com")
    ClinicMembership.objects.create(clinic=clinic, user=viewer, role="viewer")
    category = YakapCoverageCategory.objects.create(
        clinic=clinic,
        name="Primary Care",
        category_type=YakapCoverageCategory.TYPE_PRIMARY_CARE,
        annual_limit=Decimal("20000.00"),
    )
    _patient, appointment = _create_patient_appointment(clinic, service)
    client.force_login(viewer)

    response = client.post(
        reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]),
        _yakap_ledger_post_data(category),
    )

    assert response.status_code == 403
    assert not YakapLedgerEntry.objects.filter(appointment=appointment).exists()


@pytest.mark.django_db
def test_staff_can_update_patient_yakap_profile(client, clinic_setup):
    clinic, service = clinic_setup
    patient, _appointment = _create_patient_appointment(clinic, service)
    User = get_user_model()
    staff = User.objects.create_user(username="yakap-profile-staff@example.com", email="yakap-profile-staff@example.com")
    ClinicMembership.objects.create(clinic=clinic, user=staff, role=ClinicMembership.ROLE_STAFF)
    client.force_login(staff)

    response = client.post(
        reverse("dashboard:update_patient_yakap_profile", args=[patient.id]),
        {
            "status": PatientYakapProfile.STATUS_ACTIVE,
            "registered_clinic_name": "Demo Clinic PhilHealth Desk",
            "verification_method": "PhilHealth portal",
            "verification_reference": "YAKAP-PROFILE-123",
            "consent_note": "Patient consented to YAKAP verification.",
            "staff_notes": "Confirmed with clinic staff workflow.",
        },
    )

    assert response.status_code == 302
    profile = patient.yakap_profile
    assert profile.status == PatientYakapProfile.STATUS_ACTIVE
    assert profile.registered_clinic_name == "Demo Clinic PhilHealth Desk"
    assert profile.verification_method == "PhilHealth portal"
    assert profile.verification_reference == "YAKAP-PROFILE-123"
    assert profile.consent_note == "Patient consented to YAKAP verification."
    assert profile.staff_notes == "Confirmed with clinic staff workflow."
    assert profile.last_verified_at is not None
    assert profile.last_verified_by == staff
    event = YakapAuditEvent.objects.get(action=YakapAuditEvent.ACTION_PROFILE_STATUS_CHANGED)
    assert event.clinic == clinic
    assert event.actor == staff
    assert event.object_id == str(profile.pk)


@pytest.mark.django_db
def test_staff_can_update_appointment_yakap_status(client, clinic_setup):
    clinic, service = clinic_setup
    _patient, appointment = _create_patient_appointment(clinic, service)
    User = get_user_model()
    staff = User.objects.create_user(username="yakap-status-staff@example.com", email="yakap-status-staff@example.com")
    ClinicMembership.objects.create(clinic=clinic, user=staff, role=ClinicMembership.ROLE_STAFF)
    client.force_login(staff)

    response = client.post(
        reverse("dashboard:update_appointment_yakap_status", args=[appointment.id]),
        {
            "coverage_status": AppointmentYakapSnapshot.STATUS_VERIFIED_FOR_VISIT,
            "verification_note": "Verified for this appointment through YAKAP desk.",
        },
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    snapshot = appointment.yakap_snapshot
    assert snapshot.clinic == clinic
    assert snapshot.requested is True
    assert snapshot.coverage_status == AppointmentYakapSnapshot.STATUS_VERIFIED_FOR_VISIT
    assert snapshot.verification_note == "Verified for this appointment through YAKAP desk."
    assert snapshot.verified_at is not None
    assert snapshot.verified_by == staff
    event = YakapAuditEvent.objects.get(action=YakapAuditEvent.ACTION_APPOINTMENT_STATUS_CHANGED)
    assert event.clinic == clinic
    assert event.actor == staff
    assert event.object_id == str(snapshot.pk)
    assert b"Verified for this appointment through YAKAP desk." in response.content


@pytest.mark.django_db
def test_invalid_appointment_yakap_status_does_not_create_snapshot(client, clinic_setup):
    clinic, service = clinic_setup
    _patient, appointment = _create_patient_appointment(clinic, service)
    User = get_user_model()
    staff = User.objects.create_user(username="yakap-invalid-status@example.com", email="yakap-invalid-status@example.com")
    ClinicMembership.objects.create(clinic=clinic, user=staff, role=ClinicMembership.ROLE_STAFF)
    client.force_login(staff)

    response = client.post(
        reverse("dashboard:update_appointment_yakap_status", args=[appointment.id]),
        {
            "coverage_status": "invalid-status",
            "verification_note": "Should not create a YAKAP snapshot.",
        },
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert b"No YAKAP request was recorded" in response.content
    assert b"YAKAP was requested at booking" not in response.content
    assert not AppointmentYakapSnapshot.objects.filter(appointment=appointment).exists()
    assert not YakapAuditEvent.objects.exists()


@pytest.mark.django_db
def test_invalid_patient_yakap_profile_update_does_not_create_profile(client, clinic_setup):
    clinic, service = clinic_setup
    patient, _appointment = _create_patient_appointment(clinic, service)
    User = get_user_model()
    staff = User.objects.create_user(username="yakap-invalid-profile@example.com", email="yakap-invalid-profile@example.com")
    ClinicMembership.objects.create(clinic=clinic, user=staff, role=ClinicMembership.ROLE_STAFF)
    client.force_login(staff)

    response = client.post(
        reverse("dashboard:update_patient_yakap_profile", args=[patient.id]),
        {
            "status": "invalid-status",
            "registered_clinic_name": "Should not save",
            "verification_method": "Should not save",
            "verification_reference": "DENIED",
            "consent_note": "Should not save",
            "staff_notes": "Should not save",
        },
    )

    assert response.status_code == 302
    assert not PatientYakapProfile.objects.filter(patient=patient).exists()
    assert not YakapAuditEvent.objects.exists()


@pytest.mark.django_db
def test_patient_detail_can_start_yakap_profile_without_creating_one(client, clinic_setup):
    clinic, service = clinic_setup
    patient, _appointment = _create_patient_appointment(clinic, service)
    client.force_login(clinic.group.owner)

    response = client.get(reverse("dashboard:patient_detail", args=[patient.id]))

    assert response.status_code == 200
    assert b"Update YAKAP Profile" in response.content
    assert not PatientYakapProfile.objects.filter(patient=patient).exists()


@pytest.mark.django_db
def test_viewer_cannot_update_yakap_status_or_profile(client, clinic_setup):
    clinic, service = clinic_setup
    patient, appointment, snapshot = _create_yakap_requested_appointment(clinic, service)
    User = get_user_model()
    viewer = User.objects.create_user(username="yakap-update-viewer@example.com", email="yakap-update-viewer@example.com")
    ClinicMembership.objects.create(clinic=clinic, user=viewer, role="viewer")
    client.force_login(viewer)

    profile_response = client.post(
        reverse("dashboard:update_patient_yakap_profile", args=[patient.id]),
        {
            "status": PatientYakapProfile.STATUS_ACTIVE,
            "registered_clinic_name": "Should not save",
            "verification_method": "Should not save",
            "verification_reference": "DENIED",
            "consent_note": "Should not save",
            "staff_notes": "Should not save",
        },
    )
    appointment_response = client.post(
        reverse("dashboard:update_appointment_yakap_status", args=[appointment.id]),
        {
            "coverage_status": AppointmentYakapSnapshot.STATUS_VERIFIED_FOR_VISIT,
            "verification_note": "Viewer should not save.",
        },
    )

    assert profile_response.status_code == 403
    assert appointment_response.status_code == 403
    assert not PatientYakapProfile.objects.filter(patient=patient).exists()
    snapshot.refresh_from_db()
    assert snapshot.coverage_status == AppointmentYakapSnapshot.STATUS_REQUESTED
    assert snapshot.verification_note == ""
    assert not YakapAuditEvent.objects.exists()


@pytest.mark.django_db
def test_yakap_ledger_rejects_category_from_another_clinic(client, clinic_setup):
    clinic, service = clinic_setup
    other_group = ClinicGroup.objects.create(name="Other YAKAP Ledger Group", owner=clinic.group.owner)
    other_clinic = Clinic.objects.create(group=other_group, name="Other YAKAP Ledger Clinic", slug="other-yakap-ledger")
    other_category = YakapCoverageCategory.objects.create(
        clinic=other_clinic,
        name="Other Primary Care",
        category_type=YakapCoverageCategory.TYPE_PRIMARY_CARE,
        annual_limit=Decimal("20000.00"),
    )
    _patient, appointment = _create_patient_appointment(clinic, service)
    client.force_login(clinic.group.owner)

    response = client.post(
        reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]),
        _yakap_ledger_post_data(other_category),
    )

    assert response.status_code == 302
    assert not YakapLedgerEntry.objects.filter(appointment=appointment).exists()


@pytest.mark.django_db
def test_patient_detail_shows_estimated_yakap_balances_after_ledger_entry(client, clinic_setup):
    clinic, service = clinic_setup
    client.force_login(clinic.group.owner)
    client.get(reverse("dashboard:yakap"))
    category = YakapCoverageCategory.objects.get(clinic=clinic, name="Primary Care")
    category.annual_limit = Decimal("20000.00")
    category.save(update_fields=["annual_limit", "updated_at"])
    patient, appointment = _create_patient_appointment(clinic, service)
    profile = yakap_profile_for_patient(patient)
    YakapLedgerEntry.objects.create(
        clinic=clinic,
        patient=patient,
        profile=profile,
        appointment=appointment,
        service=service,
        category=category,
        entry_type=YakapLedgerEntry.TYPE_SERVICE_USAGE,
        amount=Decimal("300.00"),
        verification_status=YakapLedgerEntry.VERIFICATION_VERIFIED,
        note="Estimated usage shown on patient detail.",
        created_by=clinic.group.owner,
    )

    response = client.get(reverse("dashboard:patient_detail", args=[patient.id]))

    assert response.status_code == 200
    assert b"Estimated YAKAP balances" in response.content
    assert b"Primary Care" in response.content
    assert b"300.00 used" in response.content
    assert b"19700.00 remaining" in response.content


@pytest.mark.django_db
def test_service_edit_saves_yakap_rule(client, clinic_setup):
    clinic, service = clinic_setup
    client.force_login(clinic.group.owner)
    client.get(reverse("dashboard:yakap"))
    category = YakapCoverageCategory.objects.get(clinic=clinic, name="Primary Care")

    response = client.post(reverse("dashboard:edit_service", args=[service.id]), {
        "name": service.name,
        "description": service.description,
        "duration_minutes": "30",
        "price": "0.00",
        "color": "#06b6d4",
        "is_active": "on",
        "display_price": "on",
        "yakap_category": str(category.id),
        "yakap_coverage_status": "covered",
        "yakap_estimated_covered_amount": "500.00",
        "yakap_requires_verification": "on",
        "yakap_public_badge_label": "YAKAP eligible",
    })

    assert response.status_code == 302
    service.refresh_from_db()
    assert service.yakap_rule.category == category
    assert service.yakap_rule.coverage_status == "covered"


@pytest.mark.django_db
def test_service_create_saves_yakap_rule(client, clinic_setup):
    clinic, _service = clinic_setup
    client.force_login(clinic.group.owner)
    client.get(reverse("dashboard:yakap"))
    category = YakapCoverageCategory.objects.get(clinic=clinic, name="Primary Care")

    response = client.post(reverse("dashboard:create_service"), {
        "name": "YAKAP checkup",
        "description": "Primary care visit",
        "duration_minutes": "30",
        "price": "0.00",
        "color": "#06b6d4",
        "is_active": "on",
        "display_price": "on",
        "yakap_category": str(category.id),
        "yakap_coverage_status": "possibly_covered",
        "yakap_estimated_covered_amount": "750.00",
        "yakap_requires_verification": "on",
        "yakap_public_badge_label": "YAKAP estimate",
    })

    assert response.status_code == 302
    service = clinic.services.get(name="YAKAP checkup")
    assert service.yakap_rule.category == category
    assert service.yakap_rule.coverage_status == "possibly_covered"
    assert service.yakap_rule.estimated_covered_amount == Decimal("750.00")


@pytest.mark.django_db
def test_service_edit_rejects_yakap_category_from_other_clinic(client, clinic_setup):
    clinic, service = clinic_setup
    other_group = ClinicGroup.objects.create(name="Other YAKAP Clinic Group", owner=clinic.group.owner)
    other_clinic = Clinic.objects.create(group=other_group, name="Other YAKAP Clinic", slug="other-yakap-rule")
    other_category = YakapCoverageCategory.objects.create(
        clinic=other_clinic,
        name="Other Primary Care",
        category_type=YakapCoverageCategory.TYPE_PRIMARY_CARE,
        annual_limit=Decimal("20000.00"),
    )
    client.force_login(clinic.group.owner)
    original_name = service.name

    response = client.post(reverse("dashboard:edit_service", args=[service.id]), {
        "name": "Cross-clinic YAKAP service",
        "description": service.description,
        "duration_minutes": "30",
        "price": "0.00",
        "color": "#06b6d4",
        "is_active": "on",
        "display_price": "on",
        "yakap_category": str(other_category.id),
        "yakap_coverage_status": "covered",
        "yakap_estimated_covered_amount": "500.00",
        "yakap_requires_verification": "on",
        "yakap_public_badge_label": "YAKAP eligible",
    }, HTTP_HX_REQUEST="true")

    assert response.status_code == 200
    assert b"Select a valid choice" in response.content
    service.refresh_from_db()
    assert service.name == original_name
    assert not ServiceYakapRule.objects.filter(service=service).exists()
