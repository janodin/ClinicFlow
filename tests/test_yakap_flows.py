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
    ServiceYakapRule,
    YakapCoverageCategory,
    YakapLedgerEntry,
)
from yakap.services import create_appointment_yakap_snapshot, yakap_profile_for_patient


def _enable_yakap_settings(client, clinic, **overrides):
    client.force_login(clinic.group.owner)
    data = {
        "_form": "settings",
        "is_enabled": "on",
        "public_promo_headline": "YAKAP care estimate",
        "public_promo_body": "Ask the clinic to estimate covered primary care benefits.",
        "public_disclaimer": "Subject to PhilHealth and clinic verification.",
        "internal_disclaimer": "Staff must verify YAKAP eligibility before service.",
        "verification_instructions": "Check the clinic PhilHealth workflow before service.",
        "default_annual_credit": "20000.00",
        "reset_month": "1",
        "reset_day": "1",
    }
    data.update(overrides)
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


def _yakap_ledger_post_data(category, **overrides):
    data = {
        "category": str(category.id),
        "entry_type": YakapLedgerEntry.TYPE_SERVICE_USAGE,
        "amount": "300.00",
        "verification_status": YakapLedgerEntry.VERIFICATION_VERIFIED,
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

    response = client.post(reverse("dashboard:yakap"), {"_form": "settings", "is_enabled": "on"})

    assert response.status_code == 403


@pytest.mark.django_db
def test_yakap_settings_update_is_clinic_scoped(client, clinic_setup):
    clinic, _service = clinic_setup
    client.force_login(clinic.group.owner)

    response = client.post(
        reverse("dashboard:yakap"),
        {
            "_form": "settings",
            "is_enabled": "on",
            "public_promo_headline": "Estimated YAKAP coverage",
            "public_promo_body": "Patients can ask staff about estimated YAKAP coverage.",
            "public_disclaimer": "Coverage is public guidance only and requires clinic verification.",
            "internal_disclaimer": "Staff must verify eligibility before honoring estimates.",
            "verification_instructions": "Check the clinic PhilHealth workflow before service.",
            "default_annual_credit": "25000.00",
            "reset_month": "1",
            "reset_day": "1",
        },
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
        {
            "_form": "settings",
            "is_enabled": "on",
            "public_promo_headline": "Updated headline",
            "public_promo_body": "Updated body",
            "public_disclaimer": "Updated public disclaimer",
            "internal_disclaimer": "Updated internal disclaimer",
            "verification_instructions": "Updated verification steps",
            "default_annual_credit": "25000.00",
            "reset_month": "2",
            "reset_day": "31",
        },
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
