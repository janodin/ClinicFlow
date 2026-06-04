import json

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment
from clinics.models import Clinic, ClinicGroup, ClinicMembership
from patients.models import Patient
from patients.utils import format_phone_display, normalize_phone
from services.models import Service


@pytest.fixture
def clinic_setup(db):
    User = get_user_model()
    user = User.objects.create_user(username="owner@example.com", email="owner@example.com", password="password123")
    group = ClinicGroup.objects.create(name="Demo Clinic", owner=user)
    clinic = Clinic.objects.create(group=group, name="Demo Clinic", slug="demo-clinic")
    ClinicMembership.objects.create(clinic=clinic, user=user, role=ClinicMembership.ROLE_OWNER)
    service = Service.objects.create(clinic=clinic, name="General Consultation", duration_minutes=30)
    return clinic, service, user


@pytest.mark.django_db
def test_patient_edit_updates_fields(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)
    patient = Patient.objects.create(clinic=clinic, full_name="John Doe", phone="09170001111")
    response = client.post(
        reverse("dashboard:patient_edit", args=[patient.id]),
        {"full_name": "Jane Doe", "phone": "09170002222", "email": "jane@example.com", "notes": "Updated notes"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    patient.refresh_from_db()
    assert patient.full_name == "Jane Doe"
    assert patient.normalized_phone == "09170002222"
    assert patient.email == "jane@example.com"
    assert patient.notes == "Updated notes"


@pytest.mark.django_db
def test_patient_edit_prevents_duplicate_phone(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)
    Patient.objects.create(clinic=clinic, full_name="Existing", phone="09170001111")
    patient = Patient.objects.create(clinic=clinic, full_name="Another", phone="09170002222")
    response = client.post(
        reverse("dashboard:patient_edit", args=[patient.id]),
        {"full_name": "Another", "phone": "09170001111", "email": ""},
    )
    assert response.status_code == 200
    patient.refresh_from_db()
    assert patient.phone == "09170002222"


@pytest.mark.django_db
def test_phone_normalization_on_save(clinic_setup):
    clinic, _, _ = clinic_setup
    patient = Patient.objects.create(clinic=clinic, full_name="Test", phone="(555) 123-4567")
    assert patient.normalized_phone == "5551234567"


@pytest.mark.django_db
def test_phone_formatting_display():
    assert format_phone_display("5551234567") == "+1 (555) 123-4567"
    assert format_phone_display("15551234567") == "+1 (555) 123-4567"
    assert format_phone_display("09171234567") == "+63 917 123 4567"
    assert format_phone_display("639171234567") == "+63 917 123 4567"
    assert normalize_phone("(555) 123-4567") == "5551234567"


@pytest.mark.django_db
def test_merge_moves_appointments_and_deletes_duplicate(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)
    primary = Patient.objects.create(clinic=clinic, full_name="Primary", phone="09170001111")
    duplicate = Patient.objects.create(clinic=clinic, full_name="Duplicate", phone="09170001112")
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=duplicate,
        service=service,
        starts_at=timezone.now() + timezone.timedelta(days=1),
        ends_at=timezone.now() + timezone.timedelta(days=1, minutes=30),
    )
    response = client.post(
        reverse("dashboard:patient_merge"),
        {"primary_id": primary.id, "duplicate_id": duplicate.id},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert Appointment.objects.filter(pk=appointment.pk, patient=primary).exists()
    assert not Patient.objects.filter(pk=duplicate.pk).exists()


@pytest.mark.django_db
def test_merge_scoped_to_clinic(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)
    other_group = ClinicGroup.objects.create(name="Other Clinic", owner=user)
    other_clinic = Clinic.objects.create(group=other_group, name="Other Clinic", slug="other-clinic")
    primary = Patient.objects.create(clinic=clinic, full_name="Primary", phone="09170001111")
    other_patient = Patient.objects.create(clinic=other_clinic, full_name="Other", phone="09170001112")

    response = client.post(
        reverse("dashboard:patient_merge"),
        {"primary_id": primary.id, "duplicate_id": other_patient.id},
    )
    assert response.status_code == 404
    assert Patient.objects.filter(pk=other_patient.pk).exists()


@pytest.mark.django_db
def test_patient_delete_without_appointments_deletes_patient(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)
    patient = Patient.objects.create(clinic=clinic, full_name="Delete Me", phone="09170008888")

    response = client.post(reverse("dashboard:delete_patient", args=[patient.id]))

    assert response.status_code == 302
    assert not Patient.objects.filter(pk=patient.pk).exists()


@pytest.mark.django_db
def test_patient_delete_with_appointments_is_blocked(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)
    patient = Patient.objects.create(clinic=clinic, full_name="History Patient", phone="09170007777")
    starts_at = timezone.now() + timezone.timedelta(days=1)
    Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=starts_at,
        ends_at=starts_at + timezone.timedelta(minutes=30),
    )

    response = client.post(reverse("dashboard:delete_patient", args=[patient.id]))

    assert response.status_code == 302
    assert Patient.objects.filter(pk=patient.pk).exists()


@pytest.mark.django_db
def test_patient_delete_requires_post(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)
    patient = Patient.objects.create(clinic=clinic, full_name="Delete By Post", phone="09170006666")

    response = client.get(reverse("dashboard:delete_patient", args=[patient.id]))

    assert response.status_code == 405
    assert Patient.objects.filter(pk=patient.pk).exists()


@pytest.mark.django_db
def test_patient_delete_requires_login(clinic_setup, client):
    clinic, service, user = clinic_setup
    patient = Patient.objects.create(clinic=clinic, full_name="Login Required", phone="09170001110")

    response = client.post(reverse("dashboard:delete_patient", args=[patient.id]))

    assert response.status_code == 302
    assert Patient.objects.filter(pk=patient.pk).exists()


@pytest.mark.django_db
def test_patient_delete_cross_clinic_returns_404(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)
    other_group = ClinicGroup.objects.create(name="Other Clinic", owner=user)
    other_clinic = Clinic.objects.create(group=other_group, name="Other Clinic", slug="other-patient-delete")
    other_patient = Patient.objects.create(clinic=other_clinic, full_name="Other Patient", phone="09170005555")

    response = client.post(reverse("dashboard:delete_patient", args=[other_patient.id]))

    assert response.status_code == 404
    assert Patient.objects.filter(pk=other_patient.pk).exists()


@pytest.mark.django_db
def test_patient_delete_htmx_refreshes_patient_list(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)
    patient = Patient.objects.create(clinic=clinic, full_name="HTMX Delete", phone="09170004444")

    response = client.post(
        reverse("dashboard:delete_patient", args=[patient.id]),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert not Patient.objects.filter(pk=patient.pk).exists()
    assert b"Patients" in response.content
    assert "Patient deleted." in response.headers["HX-Trigger"]


@pytest.mark.django_db
def test_patient_delete_htmx_preserves_current_page_from_current_url(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)
    for index in range(12):
        Patient.objects.create(clinic=clinic, full_name=f"Paged Patient {index:02d}", phone=f"09170010{index:03d}")
    ordered_patients = list(clinic.patients.order_by("-created_at", "-id"))
    page_1_patient = ordered_patients[0]
    delete_patient = ordered_patients[10]
    remaining_page_2_patient = ordered_patients[11]

    response = client.post(
        reverse("dashboard:delete_patient", args=[delete_patient.id]),
        HTTP_HX_REQUEST="true",
        HTTP_HX_CURRENT_URL=reverse("dashboard:patients") + "?page=2",
    )

    content = response.content.decode()
    assert response.status_code == 200
    assert page_1_patient.full_name not in content
    assert remaining_page_2_patient.full_name in content


@pytest.mark.django_db
def test_patient_delete_htmx_blocked_keeps_patient_list(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)
    patient = Patient.objects.create(clinic=clinic, full_name="Blocked Delete", phone="09170003333")
    starts_at = timezone.now() + timezone.timedelta(days=1)
    Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=starts_at,
        ends_at=starts_at + timezone.timedelta(minutes=30),
    )

    response = client.post(
        reverse("dashboard:delete_patient", args=[patient.id]),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert Patient.objects.filter(pk=patient.pk).exists()
    assert response.headers["HX-Reswap"] == "none"
    trigger = json.loads(response.headers["HX-Trigger"])
    assert trigger["patientDeleteBlocked"] is True
    assert trigger["toast-message"]["type"] == "error"
    assert "appointment history" in trigger["toast-message"]["message"]


@pytest.mark.django_db
def test_duplicate_detection_finds_same_phone(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)
    Patient.objects.create(clinic=clinic, full_name="Alpha", phone="09170001111")
    Patient.objects.create(clinic=clinic, full_name="Beta", phone="09170001111")
    response = client.get(reverse("dashboard:find_duplicates"))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Alpha" in content
    assert "Beta" in content


@pytest.mark.django_db
def test_duplicate_detection_finds_same_name(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)
    Patient.objects.create(clinic=clinic, full_name="Same Name", phone="09170001111")
    Patient.objects.create(clinic=clinic, full_name="Same Name", phone="09170002222")
    response = client.get(reverse("dashboard:find_duplicates"))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Same Name" in content


@pytest.mark.django_db
def test_patient_detail_shows_appointment_history(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)
    patient = Patient.objects.create(clinic=clinic, full_name="History Patient", phone="09170003333")
    Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=timezone.now() + timezone.timedelta(days=1),
        ends_at=timezone.now() + timezone.timedelta(days=1, minutes=30),
    )
    response = client.get(reverse("dashboard:patient_detail", args=[patient.id]))
    assert response.status_code == 200
    content = response.content.decode()
    assert "History Patient" in content
    assert "General Consultation" in content
