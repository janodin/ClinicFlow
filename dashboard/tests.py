import pytest
from datetime import time, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo
from django.urls import reverse

from clinics.models import Clinic, ClinicGroup, ClinicMembership
from patients.models import Patient
from services.models import Service
from appointments.models import Appointment
from django.contrib.auth import get_user_model
from django.utils import timezone
from scheduling.models import BlockedTime, ClinicBusinessHour, UnavailableDate


@pytest.fixture
def clinic_setup(db):
    User = get_user_model()
    user = User.objects.create_user(username="owner@example.com", email="owner@example.com", password="password123")
    group = ClinicGroup.objects.create(name="Demo Clinic", owner=user)
    clinic = Clinic.objects.create(group=group, name="Demo Clinic", slug="demo-clinic")
    ClinicMembership.objects.create(clinic=clinic, user=user, role=ClinicMembership.ROLE_OWNER)
    service = Service.objects.create(clinic=clinic, name="General Consultation", duration_minutes=30)
    return clinic, service, user


@pytest.fixture
def calendar_setup(clinic_setup):
    clinic, service, user = clinic_setup
    target_date = timezone.localdate() + timedelta(days=1)
    ClinicBusinessHour.objects.create(
        clinic=clinic,
        weekday=target_date.weekday(),
        is_open=True,
        open_time=time(9),
        close_time=time(17),
        break_start=time(12),
        break_end=time(13),
    )
    patient = Patient.objects.create(clinic=clinic, full_name="Test Patient", phone="09170001111")
    starts_at = timezone.make_aware(timezone.datetime.combine(target_date, time(10)))
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=30),
        status=Appointment.STATUS_CONFIRMED,
    )
    return clinic, service, user, patient, appointment, target_date


@pytest.mark.django_db
def test_search_patients(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)
    Patient.objects.create(clinic=clinic, full_name="John Doe", phone="09170001111")
    response = client.get(reverse("dashboard:search") + "?q=john")
    assert response.status_code == 200
    assert b"John Doe" in response.content


@pytest.mark.django_db
def test_search_appointments(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)
    patient = Patient.objects.create(clinic=clinic, full_name="Jane Doe", phone="09170002222")
    starts_at = timezone.now() + timezone.timedelta(days=1)
    Appointment.objects.create(clinic=clinic, patient=patient, service=service, starts_at=starts_at, ends_at=starts_at + timezone.timedelta(minutes=30))
    response = client.get(reverse("dashboard:search") + "?q=jane")
    assert response.status_code == 200
    assert b"Jane Doe" in response.content


@pytest.mark.django_db
def test_calendar_events_returns_events(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)
    response = client.get(reverse("dashboard:calendar_events"))
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == appointment.id


@pytest.mark.django_db
def test_calendar_events_filters_by_service(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    other_service = Service.objects.create(clinic=clinic, name="Other Service", duration_minutes=30)
    other_start = appointment.starts_at + timedelta(hours=1)
    Appointment.objects.create(clinic=clinic, patient=patient, service=other_service, starts_at=other_start, ends_at=other_start + timedelta(minutes=30))
    client.force_login(user)
    response = client.get(reverse("dashboard:calendar_events") + f"?service={service.id}")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == appointment.id


@pytest.mark.django_db
def test_calendar_reschedule_valid(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)
    new_start = appointment.starts_at + timedelta(hours=1)
    response = client.post(reverse("dashboard:calendar_reschedule"), {"appointment_id": appointment.id, "starts_at": new_start.isoformat()})
    assert response.status_code == 200
    assert response.json()["success"] is True
    appointment.refresh_from_db()
    assert appointment.starts_at == new_start


@pytest.mark.django_db
def test_calendar_reschedule_outside_hours(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)
    new_start = timezone.make_aware(timezone.datetime.combine(target_date, time(18)))
    response = client.post(reverse("dashboard:calendar_reschedule"), {"appointment_id": appointment.id, "starts_at": new_start.isoformat()})
    assert response.json()["success"] is False
    assert "outside working hours" in response.json()["error"].lower()


@pytest.mark.django_db
def test_calendar_reschedule_overlaps_break(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)
    new_start = timezone.make_aware(timezone.datetime.combine(target_date, time(12, 15)))
    response = client.post(reverse("dashboard:calendar_reschedule"), {"appointment_id": appointment.id, "starts_at": new_start.isoformat()})
    assert response.json()["success"] is False
    assert "break" in response.json()["error"].lower()


@pytest.mark.django_db
def test_calendar_reschedule_double_booking(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    other_patient = Patient.objects.create(clinic=clinic, full_name="Other Patient", phone="09170002222")
    other_start = appointment.starts_at + timedelta(hours=4)
    Appointment.objects.create(clinic=clinic, patient=other_patient, service=service, starts_at=other_start, ends_at=other_start + timedelta(minutes=30))
    client.force_login(user)
    response = client.post(reverse("dashboard:calendar_reschedule"), {"appointment_id": appointment.id, "starts_at": other_start.isoformat()})
    assert response.json()["success"] is False
    assert "already has an appointment" in response.json()["error"].lower()


@pytest.mark.django_db
def test_calendar_reschedule_blocked_time(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    block_start = appointment.starts_at + timedelta(hours=1)
    BlockedTime.objects.create(clinic=clinic, starts_at=block_start, ends_at=block_start + timedelta(minutes=30))
    client.force_login(user)
    response = client.post(reverse("dashboard:calendar_reschedule"), {"appointment_id": appointment.id, "starts_at": block_start.isoformat()})
    assert response.json()["success"] is False
    assert "blocked" in response.json()["error"].lower()


@pytest.mark.django_db
def test_calendar_reschedule_cross_clinic_isolation(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    other_user = get_user_model().objects.create_user(username="other@example.com", email="other@example.com", password="password123")
    other_group = ClinicGroup.objects.create(name="Other Clinic", owner=other_user)
    other_clinic = Clinic.objects.create(group=other_group, name="Other Clinic", slug="other-clinic")
    ClinicMembership.objects.create(clinic=other_clinic, user=other_user, role=ClinicMembership.ROLE_OWNER)
    client.force_login(other_user)
    response = client.post(reverse("dashboard:calendar_reschedule"), {"appointment_id": appointment.id, "starts_at": (appointment.starts_at + timedelta(hours=1)).isoformat()})
    assert response.status_code == 404


@pytest.mark.django_db
def test_appointment_detail_returns_partial(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)
    response = client.get(reverse("dashboard:appointment_detail", args=[appointment.id]))
    assert response.status_code == 200
    assert b"Appointment Details" in response.content
    assert b"Test Patient" in response.content


@pytest.mark.django_db
def test_calendar_reschedule_unavailable_date(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    UnavailableDate.objects.create(clinic=clinic, date=target_date, reason="Holiday")
    client.force_login(user)
    response = client.post(reverse("dashboard:calendar_reschedule"), {"appointment_id": appointment.id, "starts_at": (appointment.starts_at + timedelta(hours=1)).isoformat()})
    assert response.json()["success"] is False
    assert "not available" in response.json()["error"].lower()


@pytest.mark.django_db
def test_calendar_reschedule_accepts_utc_iso_string(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)
    new_start = timezone.make_aware(timezone.datetime.combine(target_date, time(11)))
    utc_start = new_start.astimezone(dt_timezone.utc)
    response = client.post(reverse("dashboard:calendar_reschedule"), {"appointment_id": appointment.id, "starts_at": utc_start.isoformat().replace("+00:00", "Z")})
    assert response.json()["success"] is True
    appointment.refresh_from_db()
    local_start = appointment.starts_at.astimezone(ZoneInfo(clinic.timezone))
    assert local_start.hour == 11
