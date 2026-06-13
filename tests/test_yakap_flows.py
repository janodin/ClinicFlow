import csv
from decimal import Decimal
from datetime import timedelta
from io import StringIO
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
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


def _move_appointment_to_first_slot(clinic, service, appointment):
    slot = _first_booking_slot(clinic, service)
    appointment.starts_at = slot["starts_at"]
    appointment.ends_at = slot["ends_at"]
    appointment.save(update_fields=["starts_at", "ends_at", "updated_at"])
    return slot


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


def _prepare_verified_yakap_visit(
    clinic,
    service,
    *,
    category_name="Primary Care",
    profile_status=PatientYakapProfile.STATUS_ACTIVE,
    rule_status=ServiceYakapRule.STATUS_COVERED,
    snapshot_status=AppointmentYakapSnapshot.STATUS_VERIFIED_FOR_VISIT,
    verified_at=None,
):
    settings, categories = ensure_default_yakap_setup(clinic)
    category = next(item for item in categories if item.name == category_name)
    category.annual_limit = Decimal("20000.00")
    category.save(update_fields=["annual_limit", "updated_at"])
    ServiceYakapRule.objects.update_or_create(
        clinic=clinic,
        service=service,
        defaults={
            "category": category,
            "coverage_status": rule_status,
            "estimated_covered_amount": Decimal("300.00"),
            "requires_verification": True,
            "public_badge_label": "YAKAP verification available",
        },
    )
    patient, appointment = _create_patient_appointment(clinic, service)
    appointment.status = Appointment.STATUS_CONFIRMED
    appointment.save(update_fields=["status", "updated_at"])
    snapshot = AppointmentYakapSnapshot.objects.create(
        clinic=clinic,
        appointment=appointment,
        requested=True,
        coverage_status=snapshot_status,
        category_name=category.name,
        service_rule_status=rule_status,
        estimated_covered_amount_at_booking=Decimal("300.00"),
    )
    verified_at = verified_at or timezone.now()
    profile = yakap_profile_for_patient(patient)
    profile.status = profile_status
    profile.registered_clinic_name = clinic.name
    profile.verification_method = "Clinic PhilHealth workflow"
    profile.verification_reference = "YAKAP-VERIFIED"
    profile.last_verified_at = verified_at
    profile.last_verified_by = clinic.group.owner
    profile.save()
    snapshot.verified_at = verified_at
    snapshot.verified_by = clinic.group.owner
    snapshot.save()
    return settings, category, patient, appointment, snapshot, profile


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
def test_yakap_dashboard_excludes_cancelled_requests_from_needs_verification(client, clinic_setup):
    clinic, service = clinic_setup
    _patient, appointment, snapshot = _create_yakap_requested_appointment(clinic, service)
    appointment.status = Appointment.STATUS_CANCELLED
    appointment.save(update_fields=["status", "updated_at"])
    client.force_login(clinic.group.owner)

    response = client.get(reverse("dashboard:yakap"))

    assert response.status_code == 200
    assert appointment.patient.full_name.encode() not in response.content


@pytest.mark.django_db
def test_yakap_dashboard_excludes_no_show_requests_from_needs_verification(client, clinic_setup):
    clinic, service = clinic_setup
    _patient, appointment, snapshot = _create_yakap_requested_appointment(clinic, service)
    appointment.status = Appointment.STATUS_NO_SHOW
    appointment.save(update_fields=["status", "updated_at"])
    client.force_login(clinic.group.owner)

    response = client.get(reverse("dashboard:yakap"))

    assert response.status_code == 200
    assert appointment.patient.full_name.encode() not in response.content


@pytest.mark.django_db
def test_yakap_dashboard_excludes_verified_or_not_eligible_requests_from_needs_verification(client, clinic_setup):
    clinic, service = clinic_setup
    _included_patient, _included_appointment, _included_snapshot = _create_yakap_requested_appointment(
        clinic,
        service,
        full_name="Still Needs Verification Patient",
        status=AppointmentYakapSnapshot.STATUS_UNVERIFIED,
    )
    _included_appointment.starts_at = timezone.now() + timedelta(days=4)
    _included_appointment.ends_at = _included_appointment.starts_at + timedelta(minutes=service.duration_minutes)
    _included_appointment.save(update_fields=["starts_at", "ends_at", "updated_at"])
    verified_patient, _verified_appointment, _verified_snapshot = _create_yakap_requested_appointment(
        clinic,
        service,
        full_name="Already Verified YAKAP Patient",
        status=AppointmentYakapSnapshot.STATUS_VERIFIED_FOR_VISIT,
    )
    _verified_appointment.starts_at = timezone.now() + timedelta(days=5)
    _verified_appointment.ends_at = _verified_appointment.starts_at + timedelta(minutes=service.duration_minutes)
    _verified_appointment.save(update_fields=["starts_at", "ends_at", "updated_at"])
    not_eligible_patient, _not_eligible_appointment, _not_eligible_snapshot = _create_yakap_requested_appointment(
        clinic,
        service,
        full_name="Not Eligible YAKAP Patient",
        status=AppointmentYakapSnapshot.STATUS_NOT_ELIGIBLE,
    )
    client.force_login(clinic.group.owner)

    response = client.get(reverse("dashboard:yakap"))

    assert response.status_code == 200
    assert b"Still Needs Verification Patient" in response.content
    assert verified_patient.full_name.encode() not in response.content
    assert not_eligible_patient.full_name.encode() not in response.content


@pytest.mark.django_db
def test_yakap_dashboard_counts_categoryless_service_rules_as_incomplete(client, clinic_setup):
    clinic, service = clinic_setup
    ensure_default_yakap_setup(clinic)
    ServiceYakapRule.objects.create(
        clinic=clinic,
        service=service,
        coverage_status=ServiceYakapRule.STATUS_COVERED,
        public_badge_label="Incomplete rule",
    )
    client.force_login(clinic.group.owner)

    response = client.get(reverse("dashboard:yakap"))

    assert response.status_code == 200
    assert b"Services needing YAKAP setup" in response.content
    assert service.name.encode() in response.content


@pytest.mark.django_db
def test_service_row_yakap_badge_uses_semantic_classes(client, clinic_setup):
    clinic, service = clinic_setup
    ServiceYakapRule.objects.create(
        clinic=clinic,
        service=service,
        coverage_status=ServiceYakapRule.STATUS_CASH_ONLY,
        public_badge_label="Cash only",
    )
    client.force_login(clinic.group.owner)

    response = client.get(reverse("dashboard:services"))

    assert response.status_code == 200
    assert b"cf-status-cancelled" in response.content
    assert b"cf-badge-danger" not in response.content


@pytest.mark.django_db
def test_viewer_patient_detail_does_not_render_editable_yakap_profile_form(client, clinic_setup):
    clinic, service = clinic_setup
    patient, _appointment = _create_patient_appointment(clinic, service)
    User = get_user_model()
    viewer = User.objects.create_user(username="yakap-viewer-detail@example.com", email="yakap-viewer-detail@example.com")
    ClinicMembership.objects.create(clinic=clinic, user=viewer, role="viewer")
    client.force_login(viewer)

    response = client.get(reverse("dashboard:patient_detail", args=[patient.id]))

    assert response.status_code == 200
    assert b"Update YAKAP Profile" not in response.content
    assert b"Estimated YAKAP balances" in response.content


@pytest.mark.django_db
def test_appointment_detail_shows_verified_yakap_status_with_manual_verification_copy(client, clinic_setup):
    clinic, service = clinic_setup
    _patient, appointment, snapshot = _create_yakap_requested_appointment(
        clinic,
        service,
        status=AppointmentYakapSnapshot.STATUS_VERIFIED_FOR_VISIT,
    )
    snapshot.verified_by = clinic.group.owner
    snapshot.verified_at = timezone.now()
    snapshot.verification_note = "Method: PhilHealth portal"
    snapshot.save()
    client.force_login(clinic.group.owner)

    response = client.get(reverse("dashboard:appointment_detail", args=[appointment.id]))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Clinic verification recorded for this visit." in content
    assert "Estimated coverage only; this is not a PhilHealth eligibility or benefit determination." in content
    assert "YAKAP assistance approved" not in content
    assert "official PhilHealth approval" not in content
    assert "guaranteed free" not in content.lower()


@pytest.mark.django_db
def test_yakap_dashboard_shows_operational_risk_sections(client, clinic_setup):
    clinic, service = clinic_setup
    client.force_login(clinic.group.owner)
    settings, categories = ensure_default_yakap_setup(clinic)
    settings.low_balance_threshold_amount = Decimal("100.00")
    settings.save(update_fields=["low_balance_threshold_amount", "updated_at"])
    category = next(item for item in categories if item.name == "Medicines")
    category.annual_limit = Decimal("1000.00")
    category.save(update_fields=["annual_limit", "updated_at"])
    _request_patient, request_appointment, _snapshot = _create_yakap_requested_appointment(
        clinic,
        service,
        full_name="Upcoming YAKAP Patient",
    )
    low_patient = Patient.objects.create(clinic=clinic, full_name="Low Balance Patient", phone="0917-555-0201")
    low_profile = yakap_profile_for_patient(low_patient)
    YakapLedgerEntry.objects.create(
        clinic=clinic,
        patient=low_patient,
        profile=low_profile,
        service=service,
        category=category,
        entry_type=YakapLedgerEntry.TYPE_MEDICINE_USAGE,
        amount=Decimal("950.00"),
        verification_status=YakapLedgerEntry.VERIFICATION_VERIFIED,
        note="Low estimated balance.",
        created_by=clinic.group.owner,
    )
    over_patient = Patient.objects.create(clinic=clinic, full_name="Over Limit Patient", phone="0917-555-0202")
    over_profile = yakap_profile_for_patient(over_patient)
    YakapLedgerEntry.objects.create(
        clinic=clinic,
        patient=over_patient,
        profile=over_profile,
        category=category,
        entry_type=YakapLedgerEntry.TYPE_MEDICINE_USAGE,
        amount=Decimal("1200.00"),
        verification_status=YakapLedgerEntry.VERIFICATION_VERIFIED,
        note="Over estimated limit.",
        created_by=clinic.group.owner,
    )
    assert not YakapCreditLinePeriod.objects.filter(clinic=clinic).exists()

    response = client.get(reverse("dashboard:yakap"))

    assert response.status_code == 200
    assert b"Needs verification" in response.content
    assert b"Upcoming YAKAP Patient" in response.content
    assert b"Low estimated balance" in response.content
    assert b"Low Balance Patient" in response.content
    assert b"Over estimated limit" in response.content
    assert b"Over Limit Patient" in response.content
    assert b"Services needing YAKAP setup" in response.content
    assert service.name.encode() in response.content
    assert b"Recent YAKAP ledger entries" in response.content
    assert b"Low estimated balance." in response.content
    assert reverse("dashboard:appointment_detail", args=[request_appointment.id]).encode() in response.content
    assert not YakapCreditLinePeriod.objects.filter(clinic=clinic).exists()


@pytest.mark.django_db
def test_yakap_dashboard_kpis_use_total_counts_not_table_caps(client, clinic_setup):
    clinic, _service = clinic_setup
    client.force_login(clinic.group.owner)
    ensure_default_yakap_setup(clinic)
    for index in range(11):
        clinic.services.create(name=f"Unclassified Service {index}", duration_minutes=30)

    response = client.get(reverse("dashboard:yakap"))

    assert response.status_code == 200
    assert b'<p class="mt-2 text-3xl font-light tabular-nums text-[var(--cf-ink)]">12</p>' in response.content


@pytest.mark.django_db
def test_yakap_export_is_clinic_scoped_and_audited(client, clinic_setup):
    clinic, service = clinic_setup
    settings, categories = ensure_default_yakap_setup(clinic)
    category = next(item for item in categories if item.name == "Primary Care")
    patient, appointment = _create_patient_appointment(clinic, service, full_name="Export Included Patient")
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
        external_reference="YAKAP-EXPORT-1",
        note="Included in export.",
        created_by=clinic.group.owner,
    )
    YakapLedgerEntry.objects.create(
        clinic=clinic,
        patient=patient,
        profile=profile,
        category=category,
        entry_type=YakapLedgerEntry.TYPE_SERVICE_USAGE,
        amount=Decimal("400.00"),
        verification_status=YakapLedgerEntry.VERIFICATION_VERIFIED,
        occurred_at=timezone.now() - timedelta(days=40),
        note="Outside export window.",
        created_by=clinic.group.owner,
    )
    other_group = ClinicGroup.objects.create(name="Other YAKAP Export Group", owner=clinic.group.owner)
    other_clinic = Clinic.objects.create(group=other_group, name="Other YAKAP Export Clinic", slug="other-yakap-export")
    other_category = YakapCoverageCategory.objects.create(
        clinic=other_clinic,
        name="Other Primary Care",
        category_type=YakapCoverageCategory.TYPE_PRIMARY_CARE,
        annual_limit=Decimal("20000.00"),
    )
    other_patient = Patient.objects.create(clinic=other_clinic, full_name="Other Clinic Patient", phone="0917-555-0999")
    other_profile = yakap_profile_for_patient(other_patient)
    YakapLedgerEntry.objects.create(
        clinic=other_clinic,
        patient=other_patient,
        profile=other_profile,
        category=other_category,
        entry_type=YakapLedgerEntry.TYPE_SERVICE_USAGE,
        amount=Decimal("900.00"),
        verification_status=YakapLedgerEntry.VERIFICATION_VERIFIED,
        note="Other clinic export row.",
        created_by=clinic.group.owner,
    )
    client.force_login(clinic.group.owner)

    response = client.get(
        "/yakap/export/",
        {
            "started_at": timezone.localdate().isoformat(),
            "ended_at": timezone.localdate().isoformat(),
        },
    )

    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    rows = list(csv.DictReader(StringIO(response.content.decode())))
    assert [row["patient"] for row in rows] == ["Export Included Patient"]
    assert rows[0]["appointment_reference"] == appointment.reference_code
    assert rows[0]["service"] == service.name
    assert rows[0]["category"] == category.name
    assert rows[0]["amount"] == "300.00"
    assert rows[0]["external_reference"] == "YAKAP-EXPORT-1"
    assert rows[0]["note"] == "Included in export."
    assert "Outside export window." not in response.content.decode()
    assert "Other Clinic Patient" not in response.content.decode()
    event = YakapAuditEvent.objects.get(action=YakapAuditEvent.ACTION_EXPORT_CREATED)
    assert event.clinic == clinic
    assert event.actor == clinic.group.owner
    assert event.object_id == str(settings.pk)


@pytest.mark.django_db
def test_yakap_export_escapes_formula_like_csv_cells(client, clinic_setup):
    clinic, service = clinic_setup
    ensure_default_yakap_setup(clinic)
    category = YakapCoverageCategory.objects.get(clinic=clinic, name="Primary Care")
    patient = Patient.objects.create(clinic=clinic, full_name="=Formula Patient", phone="0917-555-0301")
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=timezone.now() + timedelta(days=4),
        ends_at=timezone.now() + timedelta(days=4, minutes=service.duration_minutes),
        source=Appointment.SOURCE_STAFF,
        reason="YAKAP export formula test",
    )
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
        external_reference="+REF",
        note="@formula note",
        created_by=clinic.group.owner,
    )
    client.force_login(clinic.group.owner)

    response = client.get(
        reverse("dashboard:yakap_export"),
        {"started_at": timezone.localdate().isoformat(), "ended_at": timezone.localdate().isoformat()},
    )

    assert response.status_code == 200
    rows = list(csv.DictReader(StringIO(response.content.decode())))
    assert rows[0]["patient"] == "'=Formula Patient"
    assert rows[0]["external_reference"] == "'+REF"
    assert rows[0]["note"] == "'@formula note"


@pytest.mark.django_db
def test_yakap_dashboard_staff_can_view_operational_sections_without_settings_controls(client, clinic_setup):
    clinic, service = clinic_setup
    _patient, appointment, _snapshot = _create_yakap_requested_appointment(clinic, service, full_name="Staff Visible YAKAP")
    User = get_user_model()
    staff = User.objects.create_user(username="yakap-staff@example.com", email="yakap-staff@example.com")
    ClinicMembership.objects.create(clinic=clinic, user=staff, role=ClinicMembership.ROLE_STAFF)
    client.force_login(staff)

    response = client.get(reverse("dashboard:yakap"))

    assert response.status_code == 200
    assert b"Staff Visible YAKAP" in response.content
    assert reverse("dashboard:appointment_detail", args=[appointment.id]).encode() in response.content
    assert b"Unverified YAKAP requests" in response.content
    assert b"Manual ledger export" not in response.content
    assert b'name="_form" value="settings"' not in response.content
    assert b'name="_form" value="category"' not in response.content
    assert not ClinicYakapSettings.objects.filter(clinic=clinic).exists()


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
def test_yakap_dashboard_category_post_rejects_staff_without_mutating(client, clinic_setup):
    clinic, _service = clinic_setup
    User = get_user_model()
    staff = User.objects.create_user(username="yakap-category-staff@example.com", email="yakap-category-staff@example.com")
    ClinicMembership.objects.create(clinic=clinic, user=staff, role=ClinicMembership.ROLE_STAFF)
    client.force_login(staff)

    response = client.post(
        reverse("dashboard:yakap"),
        {
            "_form": "category",
            "name": "Unauthorized Category",
            "category_type": YakapCoverageCategory.TYPE_OTHER,
            "annual_limit": "1000.00",
            "is_active": "on",
            "notes": "Should not save.",
            "sort_order": "9",
        },
    )

    assert response.status_code == 403
    assert not YakapCoverageCategory.objects.filter(clinic=clinic, name="Unauthorized Category").exists()
    assert not YakapAuditEvent.objects.exists()


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
def test_widget_hides_yakap_promo_when_enabled_without_promotable_services(client, clinic_setup):
    clinic, _service = clinic_setup
    _enable_yakap_settings(client, clinic)

    response = client.get(reverse("widget:home", args=[clinic.slug]))

    assert response.status_code == 200
    assert b"Ask the clinic to check YAKAP" not in response.content
    assert b'name="yakap_requested"' not in response.content


@pytest.mark.django_db
def test_widget_shows_yakap_promo_when_enabled_with_promotable_service(client, clinic_setup):
    clinic, _service = clinic_setup
    _enable_yakap_settings(
        client,
        clinic,
        public_promo_headline="Custom YAKAP clinic estimate",
        public_promo_body="Patients can request an estimate before their visit.",
        public_disclaimer="Custom YAKAP disclaimer requires clinic verification.",
    )
    _settings, categories = ensure_default_yakap_setup(clinic)
    category = next(item for item in categories if item.name == "Primary Care")
    ServiceYakapRule.objects.create(
        clinic=clinic,
        service=_service,
        category=category,
        coverage_status=ServiceYakapRule.STATUS_REQUIRES_VERIFICATION,
        public_badge_label="YAKAP check available",
    )

    response = client.get(reverse("widget:home", args=[clinic.slug]))

    assert response.status_code == 200
    assert b"Ask the clinic to check YAKAP for your visit" in response.content
    assert b"Custom YAKAP disclaimer requires clinic verification." in response.content


@pytest.mark.django_db
def test_widget_yakap_checkbox_binds_state_and_disables_when_service_not_promotable(client, clinic_setup):
    clinic, service = clinic_setup
    _enable_yakap_settings(client, clinic)
    _settings, categories = ensure_default_yakap_setup(clinic)
    category = next(item for item in categories if item.name == "Primary Care")
    ServiceYakapRule.objects.create(
        clinic=clinic,
        service=service,
        category=category,
        coverage_status=ServiceYakapRule.STATUS_REQUIRES_VERIFICATION,
    )

    response = client.get(reverse("widget:home", args=[clinic.slug]))

    assert response.status_code == 200
    content = response.content.decode()
    assert "yakapRequested: false" in content
    assert 'x-model="yakapRequested"' in content
    assert ':disabled="!selectedServiceAllowsYakap()"' in content
    assert content.count("this.yakapRequested = false;") >= 3


@pytest.mark.django_db
def test_widget_shows_public_yakap_service_badge_without_amount(client, clinic_setup):
    clinic, service = clinic_setup
    _enable_yakap_settings(client, clinic)
    client.force_login(clinic.group.owner)
    client.get(reverse("dashboard:yakap"))
    category = YakapCoverageCategory.objects.get(clinic=clinic, name="Medicines")
    ServiceYakapRule.objects.create(
        clinic=clinic,
        service=service,
        category=category,
        coverage_status=ServiceYakapRule.STATUS_POSSIBLY_COVERED,
        estimated_covered_amount=Decimal("350.00"),
        public_badge_label="YAKAP verification available",
    )
    client.logout()

    response = client.get(reverse("widget:home", args=[clinic.slug]))

    assert response.status_code == 200
    assert b"YAKAP verification available" in response.content
    assert b"350.00" not in response.content
    assert b"20000" not in response.content


@pytest.mark.django_db
def test_widget_hides_public_yakap_service_badge_without_category(client, clinic_setup):
    clinic, service = clinic_setup
    _enable_yakap_settings(client, clinic)
    ServiceYakapRule.objects.create(
        clinic=clinic,
        service=service,
        coverage_status=ServiceYakapRule.STATUS_POSSIBLY_COVERED,
        public_badge_label="YAKAP verification available",
    )

    response = client.get(reverse("widget:home", args=[clinic.slug]))

    assert response.status_code == 200
    assert b"YAKAP verification available" not in response.content


@pytest.mark.django_db
@override_settings(WIDGET_PUBLIC_BOOKING_RATE_LIMIT=0)
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
@override_settings(WIDGET_PUBLIC_BOOKING_RATE_LIMIT=0)
def test_widget_booking_ignores_yakap_intent_for_service_without_promotable_rule(client, clinic_setup):
    clinic, service = clinic_setup
    _enable_yakap_settings(client, clinic)
    slot = _first_booking_slot(clinic, service)

    response = client.post(
        reverse("widget:book", args=[clinic.slug]),
        _widget_booking_payload(service, slot, yakap_requested="on"),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    appointment = Appointment.objects.get(clinic=clinic, service=service, patient__full_name="Juan Dela Cruz")
    assert not AppointmentYakapSnapshot.objects.filter(appointment=appointment).exists()
    assert b"YAKAP check requested" not in response.content


@pytest.mark.parametrize(
    "rule_status",
    [ServiceYakapRule.STATUS_CASH_ONLY, ServiceYakapRule.STATUS_NOT_COVERED],
)
@pytest.mark.django_db
@override_settings(WIDGET_PUBLIC_BOOKING_RATE_LIMIT=0)
def test_widget_booking_ignores_yakap_intent_for_non_public_rule(client, clinic_setup, rule_status):
    clinic, service = clinic_setup
    _enable_yakap_settings(client, clinic)
    _settings, categories = ensure_default_yakap_setup(clinic)
    category = next(item for item in categories if item.name == "Primary Care")
    ServiceYakapRule.objects.create(clinic=clinic, service=service, category=category, coverage_status=rule_status)
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
@override_settings(WIDGET_PUBLIC_BOOKING_RATE_LIMIT=0)
def test_widget_yakap_confirmation_uses_check_requested_language(client, clinic_setup):
    clinic, service = clinic_setup
    _enable_yakap_settings(client, clinic)
    _settings, categories = ensure_default_yakap_setup(clinic)
    category = next(item for item in categories if item.name == "Primary Care")
    ServiceYakapRule.objects.create(
        clinic=clinic,
        service=service,
        category=category,
        coverage_status=ServiceYakapRule.STATUS_REQUIRES_VERIFICATION,
    )
    slot = _first_booking_slot(clinic, service)

    response = client.post(
        reverse("widget:book", args=[clinic.slug]),
        _widget_booking_payload(service, slot, yakap_requested="on"),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "YAKAP check requested" in content
    assert "not official PhilHealth approval or balance" in content
    assert "guaranteed" not in content.lower()


@pytest.mark.django_db
@override_settings(WIDGET_PUBLIC_BOOKING_RATE_LIMIT=0)
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
@override_settings(WIDGET_PUBLIC_BOOKING_RATE_LIMIT=0)
def test_widget_booking_ignores_yakap_intent_when_disabled_with_promotable_rule(client, clinic_setup):
    clinic, service = clinic_setup
    _settings, categories = ensure_default_yakap_setup(clinic)
    category = next(item for item in categories if item.name == "Primary Care")
    ServiceYakapRule.objects.create(
        clinic=clinic,
        service=service,
        category=category,
        coverage_status=ServiceYakapRule.STATUS_REQUIRES_VERIFICATION,
    )
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
def test_yakap_dashboard_renders_policy_settings_fields(client, clinic_setup):
    clinic, _service = clinic_setup
    client.force_login(clinic.group.owner)

    response = client.get(reverse("dashboard:yakap"))

    assert response.status_code == 200
    content = response.content.decode()
    for field_name in [
        "program_label",
        "medicine_annual_limit_default",
        "default_non_medicine_limit",
        "low_balance_threshold_amount",
        "verification_stale_after_days",
    ]:
        assert f'name="{field_name}"' in content
    assert '<p class="cf-kpi-label">Default annual credit</p>' not in content
    assert "Medicines/GAMOT default" in content


@pytest.mark.django_db
def test_yakap_settings_save_is_audited(client, clinic_setup):
    clinic, _service = clinic_setup
    client.force_login(clinic.group.owner)

    response = client.post(
        reverse("dashboard:yakap"),
        _yakap_settings_post_data(public_promo_headline="Audited YAKAP headline"),
    )

    assert response.status_code == 302
    settings = ClinicYakapSettings.objects.get(clinic=clinic)
    event = YakapAuditEvent.objects.get(
        clinic=clinic,
        action=YakapAuditEvent.ACTION_SETTINGS_CHANGED,
        object_type="ClinicYakapSettings",
        object_id=str(settings.pk),
    )
    assert "settings" in event.summary.lower()


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
def test_yakap_dashboard_updates_existing_category_limit_and_audits(client, clinic_setup):
    clinic, _service = clinic_setup
    ensure_default_yakap_setup(clinic)
    category = YakapCoverageCategory.objects.get(clinic=clinic, name="Primary Care")
    client.force_login(clinic.group.owner)

    response = client.post(
        reverse("dashboard:yakap"),
        {
            "_form": "category",
            "category_id": str(category.id),
            "name": category.name,
            "category_type": category.category_type,
            "annual_limit": "1500.00",
            "is_active": "on",
            "notes": "Updated local policy.",
            "sort_order": str(category.sort_order),
        },
    )

    assert response.status_code == 302
    category.refresh_from_db()
    assert category.annual_limit == Decimal("1500.00")
    assert category.notes == "Updated local policy."
    assert YakapCoverageCategory.objects.filter(clinic=clinic, name="Primary Care").count() == 1
    event = YakapAuditEvent.objects.get(
        clinic=clinic,
        action=YakapAuditEvent.ACTION_SETTINGS_CHANGED,
        object_type="YakapCoverageCategory",
        object_id=str(category.pk),
    )
    assert "updated" in event.summary.lower()


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
def test_yakap_ledger_blocks_unverified_request_without_saving(client, clinic_setup):
    clinic, service = clinic_setup
    client.force_login(clinic.group.owner)
    _settings, category, _patient, appointment, snapshot, _profile = _prepare_verified_yakap_visit(
        clinic,
        service,
        snapshot_status=AppointmentYakapSnapshot.STATUS_UNVERIFIED,
    )
    client.raise_request_exception = False

    response = client.post(
        reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]),
        _yakap_ledger_post_data(category),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert b"Verify YAKAP eligibility for this visit before posting usage" in response.content
    assert not YakapLedgerEntry.objects.filter(appointment=appointment).exists()
    snapshot.refresh_from_db()
    assert snapshot.coverage_status == AppointmentYakapSnapshot.STATUS_UNVERIFIED


@pytest.mark.parametrize("appointment_status", [Appointment.STATUS_PENDING, Appointment.STATUS_CANCELLED, Appointment.STATUS_NO_SHOW])
@pytest.mark.django_db
def test_yakap_ledger_blocks_unpostable_appointment_lifecycle_statuses(client, clinic_setup, appointment_status):
    clinic, service = clinic_setup
    client.force_login(clinic.group.owner)
    _settings, category, _patient, appointment, _snapshot, _profile = _prepare_verified_yakap_visit(clinic, service)
    appointment.status = appointment_status
    appointment.save(update_fields=["status", "updated_at"])

    response = client.post(
        reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]),
        _yakap_ledger_post_data(category),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert b"Only confirmed or completed appointments can receive YAKAP usage" in response.content
    assert not YakapLedgerEntry.objects.filter(appointment=appointment).exists()


@pytest.mark.django_db
def test_yakap_ledger_blocks_inactive_profile_without_saving(client, clinic_setup):
    clinic, service = clinic_setup
    client.force_login(clinic.group.owner)
    _settings, category, _patient, appointment, _snapshot, profile = _prepare_verified_yakap_visit(
        clinic,
        service,
        profile_status=PatientYakapProfile.STATUS_INACTIVE,
    )

    response = client.post(
        reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]),
        _yakap_ledger_post_data(category),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert b"Patient YAKAP profile must be active" in response.content
    assert not YakapLedgerEntry.objects.filter(appointment=appointment).exists()
    profile.refresh_from_db()
    assert profile.status == PatientYakapProfile.STATUS_INACTIVE


@pytest.mark.django_db
def test_yakap_ledger_blocks_active_profile_without_verification_timestamp(client, clinic_setup):
    clinic, service = clinic_setup
    client.force_login(clinic.group.owner)
    _settings, category, _patient, appointment, _snapshot, profile = _prepare_verified_yakap_visit(
        clinic,
        service,
    )
    profile.last_verified_at = None
    profile.save(update_fields=["last_verified_at", "updated_at"])

    response = client.post(
        reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]),
        _yakap_ledger_post_data(category),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert b"Record patient YAKAP verification before posting usage" in response.content
    assert not YakapLedgerEntry.objects.filter(appointment=appointment).exists()


@pytest.mark.django_db
def test_yakap_ledger_blocks_service_rule_cash_only_without_saving(client, clinic_setup):
    clinic, service = clinic_setup
    client.force_login(clinic.group.owner)
    _settings, category, _patient, appointment, _snapshot, _profile = _prepare_verified_yakap_visit(
        clinic,
        service,
        rule_status=ServiceYakapRule.STATUS_CASH_ONLY,
    )

    response = client.post(
        reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]),
        _yakap_ledger_post_data(category),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert b"This service is not configured as YAKAP-covered for ledger posting" in response.content
    assert not YakapLedgerEntry.objects.filter(appointment=appointment).exists()


@pytest.mark.django_db
def test_stale_yakap_profile_requires_confirmation_before_ledger_post(client, clinic_setup):
    clinic, service = clinic_setup
    client.force_login(clinic.group.owner)
    stale_verified_at = timezone.now() - timedelta(days=45)
    _settings, category, _patient, appointment, _snapshot, _profile = _prepare_verified_yakap_visit(
        clinic,
        service,
        verified_at=stale_verified_at,
    )

    response = client.post(
        reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]),
        _yakap_ledger_post_data(category),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert b"YAKAP verification is stale" in response.content
    assert b"confirm_stale_verification" in response.content
    assert not YakapLedgerEntry.objects.filter(appointment=appointment).exists()

    post_data = _yakap_ledger_post_data(category)
    post_data["confirm_stale_verification"] = "on"
    response = client.post(
        reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]),
        post_data,
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert YakapLedgerEntry.objects.filter(appointment=appointment).exists()
    _profile.refresh_from_db()
    assert _profile.last_verified_at > stale_verified_at
    assert _profile.last_verified_by == clinic.group.owner


@pytest.mark.django_db
def test_staff_can_add_yakap_ledger_entry_from_appointment(client, clinic_setup):
    clinic, service = clinic_setup
    client.force_login(clinic.group.owner)
    _settings, category, _patient, appointment, _snapshot, _profile = _prepare_verified_yakap_visit(clinic, service)

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
    _settings, category, _patient, appointment, snapshot, _profile = _prepare_verified_yakap_visit(clinic, service)

    response = client.post(
        reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]),
        _yakap_ledger_post_data(category),
    )

    assert response.status_code == 302
    snapshot.refresh_from_db()
    assert snapshot.coverage_status == AppointmentYakapSnapshot.STATUS_POSTED


@pytest.mark.django_db
def test_yakap_ledger_allows_additional_usage_after_snapshot_posted(client, clinic_setup):
    clinic, service = clinic_setup
    client.force_login(clinic.group.owner)
    _settings, category, _patient, appointment, snapshot, _profile = _prepare_verified_yakap_visit(clinic, service)
    first_response = client.post(
        reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]),
        _yakap_ledger_post_data(category),
    )
    assert first_response.status_code == 302
    snapshot.refresh_from_db()
    assert snapshot.coverage_status == AppointmentYakapSnapshot.STATUS_POSTED

    second_response = client.post(
        reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]),
        _yakap_ledger_post_data(category, amount="150.00", note="Additional verified usage."),
    )

    assert second_response.status_code == 302
    assert YakapLedgerEntry.objects.filter(appointment=appointment).count() == 2


@pytest.mark.django_db
def test_yakap_ledger_entry_does_not_mark_not_eligible_request_as_posted(client, clinic_setup):
    clinic, service = clinic_setup
    client.force_login(clinic.group.owner)
    _settings, category, _patient, appointment, snapshot, _profile = _prepare_verified_yakap_visit(
        clinic,
        service,
        snapshot_status=AppointmentYakapSnapshot.STATUS_NOT_ELIGIBLE,
    )

    response = client.post(
        reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]),
        _yakap_ledger_post_data(category),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert b"Verify YAKAP eligibility for this visit before posting usage" in response.content
    assert not YakapLedgerEntry.objects.filter(appointment=appointment).exists()
    snapshot.refresh_from_db()
    assert snapshot.coverage_status == AppointmentYakapSnapshot.STATUS_NOT_ELIGIBLE


@pytest.mark.django_db
def test_successful_appointment_ledger_entry_creates_credit_line_period_snapshot(client, clinic_setup):
    clinic, service = clinic_setup
    client.force_login(clinic.group.owner)
    _settings, category, patient, appointment, _snapshot, _profile = _prepare_verified_yakap_visit(
        clinic,
        service,
        category_name="Medicines",
    )

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
    _settings, _category, _patient, appointment, _snapshot, _profile = _prepare_verified_yakap_visit(clinic, service)
    client.force_login(clinic.group.owner)

    response = client.get(reverse("dashboard:appointment_detail", args=[appointment.id]))

    assert response.status_code == 200
    assert b'name="occurred_at"' in response.content


@pytest.mark.django_db
def test_appointment_detail_ledger_form_includes_reference_and_reversal_fields(client, clinic_setup):
    clinic, service = clinic_setup
    _settings, _category, _patient, appointment, _snapshot, _profile = _prepare_verified_yakap_visit(clinic, service)
    client.force_login(clinic.group.owner)

    response = client.get(reverse("dashboard:appointment_detail", args=[appointment.id]))

    assert response.status_code == 200
    assert b'name="external_reference"' in response.content
    assert b'name="reversal_of"' in response.content


@pytest.mark.django_db
def test_appointment_detail_cash_only_without_saving_hides_yakap_ledger_form(client, clinic_setup):
    clinic, service = clinic_setup
    _settings, _category, _patient, appointment, _snapshot, _profile = _prepare_verified_yakap_visit(
        clinic,
        service,
        rule_status=ServiceYakapRule.STATUS_CASH_ONLY,
    )
    client.force_login(clinic.group.owner)

    response = client.get(reverse("dashboard:appointment_detail", args=[appointment.id]))

    assert response.status_code == 200
    assert b"Add YAKAP Usage" not in response.content
    assert b"Configure this service as YAKAP-covered before posting usage." in response.content


@pytest.mark.django_db
def test_appointment_detail_context_defaults_to_no_daily_ops_controls(clinic_setup):
    clinic, service = clinic_setup
    _patient, appointment = _create_patient_appointment(clinic, service)

    from dashboard.views import _appointment_detail_context

    context = _appointment_detail_context(clinic, appointment)

    assert context["can_manage_daily_ops"] is False


@pytest.mark.django_db
def test_owner_reversal_controls_remain_reachable_with_yakap_usage_blockers(client, clinic_setup):
    clinic, service = clinic_setup
    _settings, category, _patient, appointment, _snapshot, profile = _prepare_verified_yakap_visit(clinic, service)
    original_entry = YakapLedgerEntry.objects.create(
        clinic=clinic,
        patient=appointment.patient,
        profile=profile,
        appointment=appointment,
        service=service,
        category=category,
        entry_type=YakapLedgerEntry.TYPE_SERVICE_USAGE,
        amount=Decimal("300.00"),
        verification_status=YakapLedgerEntry.VERIFICATION_VERIFIED,
        note="Original usage available for reversal.",
        created_by=clinic.group.owner,
    )
    appointment.status = Appointment.STATUS_PENDING
    appointment.save(update_fields=["status", "updated_at"])
    client.force_login(clinic.group.owner)

    response = client.get(reverse("dashboard:appointment_detail", args=[appointment.id]))

    assert response.status_code == 200
    assert b"Confirm or complete the appointment before posting YAKAP usage." in response.content
    assert b"Post YAKAP Reversal" in response.content
    assert b"Add YAKAP Usage" not in response.content
    assert b'name="reversal_of"' in response.content
    assert f'value="{original_entry.pk}"'.encode() in response.content


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
def test_staff_role_cannot_post_yakap_adjustment(client, clinic_setup):
    clinic, service = clinic_setup
    _settings, category, _patient, appointment, _snapshot, _profile = _prepare_verified_yakap_visit(
        clinic,
        service,
        category_name="Medicines",
    )
    User = get_user_model()
    staff = User.objects.create_user(username="yakap-adjustment-staff@example.com", email="yakap-adjustment-staff@example.com")
    ClinicMembership.objects.create(clinic=clinic, user=staff, role=ClinicMembership.ROLE_STAFF)
    client.force_login(staff)

    response = client.post(
        reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]),
        _yakap_ledger_post_data(
            category,
            entry_type=YakapLedgerEntry.TYPE_ADJUSTMENT,
            amount="100.00",
            note="Staff should not post adjustments.",
        ),
    )

    assert response.status_code == 403
    assert not YakapLedgerEntry.objects.filter(
        appointment=appointment,
        entry_type=YakapLedgerEntry.TYPE_ADJUSTMENT,
    ).exists()


@pytest.mark.django_db
def test_staff_role_cannot_attach_reversal_link_to_non_reversal_entry(client, clinic_setup):
    clinic, service = clinic_setup
    _settings, category, _patient, appointment, _snapshot, profile = _prepare_verified_yakap_visit(
        clinic,
        service,
        category_name="Medicines",
    )
    original_entry = YakapLedgerEntry.objects.create(
        clinic=clinic,
        patient=appointment.patient,
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
    staff = User.objects.create_user(username="yakap-link-staff@example.com", email="yakap-link-staff@example.com")
    ClinicMembership.objects.create(clinic=clinic, user=staff, role=ClinicMembership.ROLE_STAFF)
    client.force_login(staff)

    response = client.post(
        reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]),
        _yakap_ledger_post_data(
            category,
            entry_type=YakapLedgerEntry.TYPE_MEDICINE_USAGE,
            amount="100.00",
            reversal_of=str(original_entry.pk),
            note="Staff should not attach reversal metadata.",
        ),
    )

    assert response.status_code == 403
    assert not YakapLedgerEntry.objects.filter(
        appointment=appointment,
        note="Staff should not attach reversal metadata.",
    ).exists()


@pytest.mark.django_db
def test_linked_yakap_reversal_must_match_original_entry_period(client, clinic_setup):
    clinic, service = clinic_setup
    client.force_login(clinic.group.owner)
    _settings, category, patient, appointment, _snapshot, profile = _prepare_verified_yakap_visit(
        clinic,
        service,
        category_name="Medicines",
    )
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
    _settings, category, patient, appointment, _snapshot, profile = _prepare_verified_yakap_visit(
        clinic,
        service,
        category_name="Medicines",
    )
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
    _settings, category, patient, appointment, _snapshot, profile = _prepare_verified_yakap_visit(clinic, service)
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
    _settings, category, patient, appointment, _snapshot, profile = _prepare_verified_yakap_visit(
        clinic,
        service,
        category_name="Medicines",
    )
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
    settings, category, patient, appointment, _snapshot, profile = _prepare_verified_yakap_visit(
        clinic,
        service,
        category_name="Medicines",
    )
    settings.hard_block_exceeded = False
    settings.save(update_fields=["hard_block_exceeded", "updated_at"])

    response = client.post(
        reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]),
        _yakap_ledger_post_data(category, entry_type=YakapLedgerEntry.TYPE_MEDICINE_USAGE, amount="25000.00"),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert b"exceeds estimated remaining" in response.content
    assert not YakapLedgerEntry.objects.filter(appointment=appointment).exists()
    assert PatientYakapProfile.objects.filter(pk=profile.pk).exists()
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
    settings, category, patient, appointment, _snapshot, profile = _prepare_verified_yakap_visit(
        clinic,
        service,
        category_name="Medicines",
    )
    settings.hard_block_exceeded = True
    settings.save(update_fields=["hard_block_exceeded", "updated_at"])
    post_data = _yakap_ledger_post_data(category, entry_type=YakapLedgerEntry.TYPE_MEDICINE_USAGE, amount="25000.00")
    post_data["confirm_over_limit"] = "on"

    response = client.post(reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]), post_data, HTTP_HX_REQUEST="true")

    assert response.status_code == 200
    assert b"blocked by clinic YAKAP settings" in response.content
    assert not YakapLedgerEntry.objects.filter(appointment=appointment).exists()
    assert PatientYakapProfile.objects.filter(pk=profile.pk).exists()
    assert not YakapCreditLinePeriod.objects.filter(patient=patient, category=category).exists()


@pytest.mark.django_db
def test_rejected_over_limit_does_not_create_yakap_settings_when_missing(client, clinic_setup):
    clinic, service = clinic_setup
    client.force_login(clinic.group.owner)
    category = YakapCoverageCategory.objects.create(
        clinic=clinic,
        name="Manual Medicines",
        category_type=YakapCoverageCategory.TYPE_MEDICINES,
        annual_limit=Decimal("100.00"),
        sort_order=1,
    )
    patient, appointment = _create_patient_appointment(clinic, service)
    appointment.status = Appointment.STATUS_CONFIRMED
    appointment.save(update_fields=["status", "updated_at"])
    ServiceYakapRule.objects.create(
        clinic=clinic,
        service=service,
        category=category,
        coverage_status=ServiceYakapRule.STATUS_COVERED,
    )
    profile = PatientYakapProfile.objects.create(
        clinic=clinic,
        patient=patient,
        status=PatientYakapProfile.STATUS_ACTIVE,
        last_verified_at=timezone.now(),
        last_verified_by=clinic.group.owner,
    )
    AppointmentYakapSnapshot.objects.create(
        clinic=clinic,
        appointment=appointment,
        requested=True,
        coverage_status=AppointmentYakapSnapshot.STATUS_VERIFIED_FOR_VISIT,
        verified_at=timezone.now(),
        verified_by=clinic.group.owner,
    )

    response = client.post(
        reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]),
        _yakap_ledger_post_data(category, entry_type=YakapLedgerEntry.TYPE_MEDICINE_USAGE, amount="300.00"),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert b"exceeds estimated remaining" in response.content
    assert not ClinicYakapSettings.objects.filter(clinic=clinic).exists()
    assert PatientYakapProfile.objects.filter(pk=profile.pk).exists()
    assert not YakapCreditLinePeriod.objects.filter(patient=patient, category=category).exists()
    assert not YakapLedgerEntry.objects.filter(appointment=appointment).exists()
    assert not YakapAuditEvent.objects.exists()


@pytest.mark.django_db
def test_ledger_over_limit_uses_entry_period_not_current_period(client, clinic_setup):
    clinic, service = clinic_setup
    client.force_login(clinic.group.owner)
    settings, category, patient, appointment, _snapshot, profile = _prepare_verified_yakap_visit(
        clinic,
        service,
        category_name="Medicines",
    )
    settings.hard_block_exceeded = False
    settings.save(update_fields=["hard_block_exceeded", "updated_at"])
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
def test_htmx_successful_ledger_post_keeps_patient_reversal_choices(client, clinic_setup):
    clinic, service = clinic_setup
    client.force_login(clinic.group.owner)
    _settings, category, patient, appointment, _snapshot, profile = _prepare_verified_yakap_visit(
        clinic,
        service,
        category_name="Medicines",
    )
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
        _yakap_ledger_post_data(category, entry_type=YakapLedgerEntry.TYPE_MEDICINE_USAGE, amount="100.00"),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert f'<option value="{original_entry.pk}">{original_entry}</option>'.encode() in response.content


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
def test_staff_cannot_manually_set_yakap_posted_status(client, clinic_setup):
    clinic, service = clinic_setup
    _patient, appointment = _create_patient_appointment(clinic, service)
    client.force_login(clinic.group.owner)

    response = client.post(
        reverse("dashboard:update_appointment_yakap_status", args=[appointment.id]),
        {
            "coverage_status": AppointmentYakapSnapshot.STATUS_POSTED,
            "verification_note": "Manual posted should be rejected.",
        },
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert b"Select a valid choice" in response.content
    assert not AppointmentYakapSnapshot.objects.filter(appointment=appointment).exists()


@pytest.mark.django_db
def test_non_verification_yakap_status_does_not_stamp_verified_metadata(client, clinic_setup):
    clinic, service = clinic_setup
    _patient, appointment, _snapshot = _create_yakap_requested_appointment(clinic, service)
    client.force_login(clinic.group.owner)

    response = client.post(
        reverse("dashboard:update_appointment_yakap_status", args=[appointment.id]),
        {
            "coverage_status": AppointmentYakapSnapshot.STATUS_NOT_ELIGIBLE,
            "verification_note": "Patient is not eligible for this visit.",
        },
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    appointment.refresh_from_db()
    snapshot = appointment.yakap_snapshot
    assert snapshot.coverage_status == AppointmentYakapSnapshot.STATUS_NOT_ELIGIBLE
    assert snapshot.verified_at is None
    assert snapshot.verified_by is None


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
def test_patient_detail_existing_yakap_profile_does_not_create_credit_line_periods(client, clinic_setup):
    clinic, service = clinic_setup
    ensure_default_yakap_setup(clinic)
    patient, _appointment = _create_patient_appointment(clinic, service)
    profile = yakap_profile_for_patient(patient)
    profile.status = PatientYakapProfile.STATUS_ACTIVE
    profile.last_verified_at = timezone.now()
    profile.last_verified_by = clinic.group.owner
    profile.save()
    client.force_login(clinic.group.owner)

    response = client.get(reverse("dashboard:patient_detail", args=[patient.id]))

    assert response.status_code == 200
    assert b"Estimated YAKAP balances" in response.content
    assert not YakapCreditLinePeriod.objects.filter(profile=profile).exists()


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
        "color": "#06b6d4",
        "is_active": "on",
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
    event = YakapAuditEvent.objects.get(
        clinic=clinic,
        action=YakapAuditEvent.ACTION_SETTINGS_CHANGED,
        object_type="ServiceYakapRule",
        object_id=str(service.yakap_rule.pk),
    )
    assert "service rule" in event.summary.lower()


@pytest.mark.django_db
def test_staff_service_edit_with_yakap_rule_fields_is_forbidden_and_preserves_existing_rule(client, clinic_setup):
    clinic, service = clinic_setup
    ensure_default_yakap_setup(clinic)
    category = YakapCoverageCategory.objects.get(clinic=clinic, name="Primary Care")
    rule = ServiceYakapRule.objects.create(
        clinic=clinic,
        service=service,
        category=category,
        coverage_status=ServiceYakapRule.STATUS_REQUIRES_VERIFICATION,
        estimated_covered_amount=Decimal("100.00"),
    )
    User = get_user_model()
    staff = User.objects.create_user(username="yakap-service-staff@example.com", email="yakap-service-staff@example.com")
    ClinicMembership.objects.create(clinic=clinic, user=staff, role=ClinicMembership.ROLE_STAFF)
    client.force_login(staff)

    response = client.post(reverse("dashboard:edit_service", args=[service.id]), {
        "name": "Staff edited regular name",
        "description": service.description,
        "duration_minutes": "30",
        "color": "#06b6d4",
        "is_active": "on",
        "yakap_category": str(category.id),
        "yakap_coverage_status": ServiceYakapRule.STATUS_COVERED,
        "yakap_estimated_covered_amount": "999.00",
        "yakap_requires_verification": "on",
        "yakap_public_badge_label": "Unsafe staff edit",
    })

    assert response.status_code == 403
    service.refresh_from_db()
    rule.refresh_from_db()
    assert service.name != "Staff edited regular name"
    assert rule.coverage_status == ServiceYakapRule.STATUS_REQUIRES_VERIFICATION
    assert rule.estimated_covered_amount == Decimal("100.00")
    assert not YakapAuditEvent.objects.exists()


@pytest.mark.django_db
def test_staff_service_edit_form_omits_yakap_rule_fields(client, clinic_setup):
    clinic, service = clinic_setup
    User = get_user_model()
    staff = User.objects.create_user(username="yakap-service-form-staff@example.com", email="yakap-service-form-staff@example.com")
    ClinicMembership.objects.create(clinic=clinic, user=staff, role=ClinicMembership.ROLE_STAFF)
    client.force_login(staff)

    response = client.get(reverse("dashboard:edit_service", args=[service.id]), HTTP_HX_REQUEST="true")

    assert response.status_code == 200
    assert b"YAKAP coverage rule" not in response.content
    assert b"yakap_coverage_status" not in response.content


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
        "color": "#06b6d4",
        "is_active": "on",
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
    assert YakapAuditEvent.objects.filter(
        clinic=clinic,
        action=YakapAuditEvent.ACTION_SETTINGS_CHANGED,
        object_type="ServiceYakapRule",
        object_id=str(service.yakap_rule.pk),
    ).exists()


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
        "color": "#06b6d4",
        "is_active": "on",
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


@pytest.mark.django_db
def test_cancelling_yakap_requested_appointment_marks_snapshot_cancelled(client, clinic_setup):
    clinic, service = clinic_setup
    _patient, appointment, snapshot = _create_yakap_requested_appointment(clinic, service)
    client.force_login(clinic.group.owner)

    response = client.post(
        reverse("dashboard:appointment_cancel", args=[appointment.id]),
        {"cancellation_reason": "Patient cancelled."},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    snapshot.refresh_from_db()
    assert snapshot.coverage_status == AppointmentYakapSnapshot.STATUS_CANCELLED
    assert snapshot.requested is False


@pytest.mark.django_db
def test_cancelling_appointment_with_yakap_ledger_is_blocked(client, clinic_setup):
    clinic, service = clinic_setup
    client.force_login(clinic.group.owner)
    _settings, category, _patient, appointment, _snapshot, _profile = _prepare_verified_yakap_visit(clinic, service)
    client.post(reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]), _yakap_ledger_post_data(category))

    response = client.post(
        reverse("dashboard:appointment_cancel", args=[appointment.id]),
        {"cancellation_reason": "Should block."},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    appointment.refresh_from_db()
    assert appointment.status == Appointment.STATUS_CONFIRMED
    assert b"Reverse YAKAP usage before cancelling" in response.content


@pytest.mark.django_db
def test_patient_merge_blocks_duplicate_with_yakap_history(client, clinic_setup):
    clinic, service = clinic_setup
    primary = Patient.objects.create(clinic=clinic, full_name="Primary Merge", phone="09170001121")
    duplicate, appointment = _create_patient_appointment(clinic, service, full_name="Duplicate Merge")
    yakap_profile_for_patient(duplicate)
    client.force_login(clinic.group.owner)

    response = client.post(
        reverse("dashboard:patient_merge"),
        {"primary_id": primary.id, "duplicate_id": duplicate.id},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert Patient.objects.filter(pk=duplicate.pk).exists()
    appointment.refresh_from_db()
    assert appointment.patient == duplicate
    assert b"Cannot merge patients with YAKAP history" in response.content


@pytest.mark.django_db
def test_appointment_edit_blocks_service_change_with_yakap_history(client, clinic_setup):
    clinic, service = clinic_setup
    patient, appointment, _snapshot = _create_yakap_requested_appointment(clinic, service)
    _move_appointment_to_first_slot(clinic, service, appointment)
    replacement_service = clinic.services.create(name="Replacement Consultation", duration_minutes=service.duration_minutes)
    starts_at = appointment.starts_at.astimezone(ZoneInfo(clinic.timezone))
    client.force_login(clinic.group.owner)

    response = client.post(
        reverse("dashboard:appointment_edit", args=[appointment.id]),
        {
            "patient_name": patient.full_name,
            "patient_phone": patient.phone,
            "patient_email": patient.email,
            "service": replacement_service.id,
            "date": starts_at.date().isoformat(),
            "time": starts_at.strftime("%H:%M"),
            "status": appointment.status,
            "payment_state": appointment.payment_state,
            "source": appointment.source,
            "reason": appointment.reason,
        },
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    appointment.refresh_from_db()
    assert appointment.service == service
    assert b"Cancel the YAKAP request or create a new appointment before changing patient or service." in response.content


@pytest.mark.django_db
def test_update_appointment_blocks_cancel_with_yakap_ledger(client, clinic_setup):
    clinic, service = clinic_setup
    client.force_login(clinic.group.owner)
    _settings, category, _patient, appointment, _snapshot, _profile = _prepare_verified_yakap_visit(clinic, service)
    client.post(reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]), _yakap_ledger_post_data(category))

    response = client.post(
        reverse("dashboard:update_appointment", args=[appointment.id]),
        {
            "status": Appointment.STATUS_CANCELLED,
            "payment_state": appointment.payment_state,
        },
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    appointment.refresh_from_db()
    assert appointment.status == Appointment.STATUS_CONFIRMED
    assert b"Reverse YAKAP usage before cancelling" in response.content


@pytest.mark.django_db
def test_appointment_edit_blocks_cancel_with_yakap_ledger(client, clinic_setup):
    clinic, service = clinic_setup
    client.force_login(clinic.group.owner)
    _settings, category, patient, appointment, _snapshot, _profile = _prepare_verified_yakap_visit(clinic, service)
    _move_appointment_to_first_slot(clinic, service, appointment)
    client.post(reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]), _yakap_ledger_post_data(category))
    starts_at = appointment.starts_at.astimezone(ZoneInfo(clinic.timezone))

    response = client.post(
        reverse("dashboard:appointment_edit", args=[appointment.id]),
        {
            "patient_name": patient.full_name,
            "patient_phone": patient.phone,
            "patient_email": patient.email,
            "service": service.id,
            "date": starts_at.date().isoformat(),
            "time": starts_at.strftime("%H:%M"),
            "status": Appointment.STATUS_CANCELLED,
            "payment_state": appointment.payment_state,
            "source": appointment.source,
            "reason": appointment.reason,
        },
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    appointment.refresh_from_db()
    assert appointment.status == Appointment.STATUS_CONFIRMED
    assert b"Reverse YAKAP usage before cancelling" in response.content


@pytest.mark.django_db
def test_appointment_edit_cancel_marks_unposted_yakap_snapshot_cancelled(client, clinic_setup):
    clinic, service = clinic_setup
    patient, appointment, snapshot = _create_yakap_requested_appointment(clinic, service)
    _move_appointment_to_first_slot(clinic, service, appointment)
    starts_at = appointment.starts_at.astimezone(ZoneInfo(clinic.timezone))
    client.force_login(clinic.group.owner)

    response = client.post(
        reverse("dashboard:appointment_edit", args=[appointment.id]),
        {
            "patient_name": patient.full_name,
            "patient_phone": patient.phone,
            "patient_email": patient.email,
            "service": service.id,
            "date": starts_at.date().isoformat(),
            "time": starts_at.strftime("%H:%M"),
            "status": Appointment.STATUS_CANCELLED,
            "payment_state": appointment.payment_state,
            "source": appointment.source,
            "reason": appointment.reason,
        },
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    appointment.refresh_from_db()
    snapshot.refresh_from_db()
    assert appointment.status == Appointment.STATUS_CANCELLED
    assert snapshot.coverage_status == AppointmentYakapSnapshot.STATUS_CANCELLED
    assert snapshot.requested is False


@pytest.mark.django_db
def test_cancelling_posted_snapshot_without_ledger_leaves_appointment_unchanged(client, clinic_setup):
    clinic, service = clinic_setup
    _settings, _category, _patient, appointment, _snapshot, _profile = _prepare_verified_yakap_visit(
        clinic,
        service,
        snapshot_status=AppointmentYakapSnapshot.STATUS_POSTED,
    )
    client.force_login(clinic.group.owner)

    response = client.post(
        reverse("dashboard:appointment_cancel", args=[appointment.id]),
        {"cancellation_reason": "Should remain confirmed."},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    appointment.refresh_from_db()
    assert appointment.status == Appointment.STATUS_CONFIRMED
    assert b"Reverse YAKAP usage before cancelling" in response.content


@pytest.mark.django_db
def test_messenger_posted_snapshot_without_ledger_leaves_appointment_unchanged(clinic_setup):
    from messenger.ai_tools import _cancel_verified_appointment_for_clinic

    clinic, service = clinic_setup
    _settings, _category, patient, appointment, _snapshot, _profile = _prepare_verified_yakap_visit(
        clinic,
        service,
        snapshot_status=AppointmentYakapSnapshot.STATUS_POSTED,
    )

    result = _cancel_verified_appointment_for_clinic(
        clinic,
        appointment.reference_code,
        patient.phone,
        True,
        "Should remain confirmed.",
    )

    assert result["cancelled"] is False
    assert "Reverse YAKAP usage before cancelling" in result["error"]
    appointment.refresh_from_db()
    assert appointment.status == Appointment.STATUS_CONFIRMED


@pytest.mark.django_db
def test_bot_engine_posted_snapshot_without_ledger_leaves_appointment_unchanged(clinic_setup):
    from messenger.bot_engine import handle_message
    from messenger.models import MessengerConnection, MessengerSession

    clinic, service = clinic_setup
    _settings, _category, _patient, appointment, _snapshot, _profile = _prepare_verified_yakap_visit(
        clinic,
        service,
        snapshot_status=AppointmentYakapSnapshot.STATUS_POSTED,
    )
    connection = MessengerConnection.objects.create(
        clinic=clinic,
        page_id="yakap-bot-page",
        page_access_token="test-token",
    )
    session = MessengerSession.objects.create(
        connection=connection,
        psid="yakap-bot-psid",
        state=MessengerSession.STATE_GREETING,
    )
    appointment.source = Appointment.SOURCE_MESSENGER
    appointment.messenger_psid = session.psid
    appointment.save(update_fields=["source", "messenger_psid", "updated_at"])

    actions = handle_message(session, "cancel", "")

    appointment.refresh_from_db()
    assert appointment.status == Appointment.STATUS_CONFIRMED
    assert any("Reverse YAKAP usage before cancelling" in action.get("text", "") for action in actions)


@pytest.mark.django_db
def test_appointment_edit_blocked_patient_change_does_not_create_patient(client, clinic_setup):
    clinic, service = clinic_setup
    patient, appointment, _snapshot = _create_yakap_requested_appointment(clinic, service)
    _move_appointment_to_first_slot(clinic, service, appointment)
    starts_at = appointment.starts_at.astimezone(ZoneInfo(clinic.timezone))
    client.force_login(clinic.group.owner)

    response = client.post(
        reverse("dashboard:appointment_edit", args=[appointment.id]),
        {
            "patient_name": "New YAKAP Patient",
            "patient_phone": "09170009999",
            "patient_email": "new-yakap-patient@example.com",
            "service": service.id,
            "date": starts_at.date().isoformat(),
            "time": starts_at.strftime("%H:%M"),
            "status": appointment.status,
            "payment_state": appointment.payment_state,
            "source": appointment.source,
            "reason": appointment.reason,
        },
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    appointment.refresh_from_db()
    assert appointment.patient == patient
    assert not Patient.objects.filter(clinic=clinic, phone="09170009999").exists()
    assert b"Cancel the YAKAP request or create a new appointment before changing patient or service." in response.content
