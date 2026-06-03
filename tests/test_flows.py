import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch

from appointments.models import Appointment
from clinics.models import Clinic, ClinicGroup, ClinicMembership
from patients.models import Patient
from scheduling.models import ClinicBusinessHour
from services.models import Service


@pytest.mark.django_db
def test_signup_creates_usable_clinic(client):
    response = client.post(
        reverse("accounts:signup"),
        {
            "full_name": "Demo User",
            "email": "demo@example.com",
            "clinic_name": "Demo Clinic",
            "password": "password123",
        },
    )
    assert response.status_code == 302
    clinic = Clinic.objects.get(slug="demo-clinic")
    assert clinic.services.filter(name="General Consultation").exists()
    assert clinic.business_hours.count() == 5


@pytest.mark.django_db
def test_today_dashboard_context_is_clinic_scoped_and_actionable(client):
    User = get_user_model()
    owner = User.objects.create_user(username="owner@example.com", email="owner@example.com", password="password123")
    other_owner = User.objects.create_user(username="other@example.com", email="other@example.com", password="password123")
    group = ClinicGroup.objects.create(name="Demo Group", owner=owner)
    other_group = ClinicGroup.objects.create(name="Other Group", owner=other_owner)
    clinic = Clinic.objects.create(group=group, name="Demo Clinic", slug="demo-clinic")
    other_clinic = Clinic.objects.create(group=other_group, name="Other Clinic", slug="other-clinic")
    ClinicMembership.objects.create(clinic=clinic, user=owner, role=ClinicMembership.ROLE_OWNER)
    ClinicMembership.objects.create(clinic=other_clinic, user=other_owner, role=ClinicMembership.ROLE_OWNER)
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30)
    other_service = Service.objects.create(clinic=other_clinic, name="Other Consultation", duration_minutes=30)
    clinic_tz = ZoneInfo(clinic.timezone)
    fixed_now = datetime(2026, 6, 2, 1, 0, tzinfo=ZoneInfo("UTC"))
    local_today = timezone.localdate(fixed_now, clinic_tz)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=local_today.weekday(), is_open=True, open_time=time(0), close_time=time(23, 59))
    ClinicBusinessHour.objects.create(clinic=other_clinic, weekday=local_today.weekday(), is_open=True, open_time=time(0), close_time=time(23, 59))
    patient = Patient.objects.create(clinic=clinic, full_name="Demo Patient", phone="09170001111")
    other_patient = Patient.objects.create(clinic=other_clinic, full_name="Other Patient", phone="09170002222")
    starts_at = fixed_now + timedelta(hours=1)
    Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=30),
        status=Appointment.STATUS_PENDING,
    )
    Appointment.objects.create(
        clinic=other_clinic,
        patient=other_patient,
        service=other_service,
        starts_at=starts_at + timedelta(hours=1),
        ends_at=starts_at + timedelta(hours=1, minutes=30),
        status=Appointment.STATUS_PENDING,
    )
    client.force_login(owner)

    with patch("django.utils.timezone.now", return_value=fixed_now):
        response = client.get(reverse("dashboard:home"))

    assert response.status_code == 200
    assert response.context["metrics"]["pending"] == 1
    assert response.context["open_slots_count"] >= 1
    assert response.context["next_slot_label"]
    assert list(response.context["needs_attention"]) == [Appointment.objects.get(clinic=clinic)]


@pytest.mark.django_db
def test_today_dashboard_uses_clinic_timezone_day_bounds(client):
    User = get_user_model()
    owner = User.objects.create_user(username="timezone@example.com", email="timezone@example.com", password="password123")
    group = ClinicGroup.objects.create(name="Timezone Group", owner=owner)
    clinic_tz = ZoneInfo("Pacific/Kiritimati")
    clinic = Clinic.objects.create(group=group, name="Timezone Clinic", slug="timezone-clinic", timezone="Pacific/Kiritimati")
    ClinicMembership.objects.create(clinic=clinic, user=owner, role=ClinicMembership.ROLE_OWNER)
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30)
    local_today = timezone.localdate(timezone.now(), clinic_tz)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=local_today.weekday(), is_open=True, open_time=time(0), close_time=time(23, 59))
    patient = Patient.objects.create(clinic=clinic, full_name="Boundary Patient", phone="09170003333")
    local_start = datetime.combine(local_today, time(12), clinic_tz)
    starts_at = local_start.astimezone(ZoneInfo("UTC"))
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=30),
        status=Appointment.STATUS_PENDING,
    )
    client.force_login(owner)

    response = client.get(reverse("dashboard:home"))

    assert response.status_code == 200
    assert response.context["today"] == local_today
    assert list(response.context["appointments"]) == [appointment]
    assert response.context["metrics"]["today"] == 1
    assert b"12:00 PM" in response.content
