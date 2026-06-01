from datetime import time, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from appointments.models import Appointment
from clinics.models import Clinic, ClinicGroup, ClinicMembership
from patients.models import Patient
from scheduling.models import ClinicBusinessHour, UnavailableDate, Weekday
from scheduling.utils import generate_slots, get_working_window, slot_is_available
from services.models import Service


@pytest.fixture
def clinic_setup(db):
    User = get_user_model()
    user = User.objects.create_user(username="owner@example.com", email="owner@example.com", password="password123")
    group = ClinicGroup.objects.create(name="Demo Clinic", owner=user)
    clinic = Clinic.objects.create(group=group, name="Demo Clinic", slug="demo-clinic")
    ClinicMembership.objects.create(clinic=clinic, user=user, role=ClinicMembership.ROLE_OWNER)
    service = Service.objects.create(clinic=clinic, name="General Consultation", duration_minutes=30)
    weekday = (timezone.localdate() + timedelta(days=1)).weekday()
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=weekday, open_time=time(9), close_time=time(12))
    return clinic, service


@pytest.mark.django_db
def test_clinic_business_hour_unique_constraint(clinic_setup):
    clinic, _ = clinic_setup
    existing = clinic.business_hours.first()
    hour = ClinicBusinessHour(clinic=clinic, weekday=existing.weekday, open_time=time(9), close_time=time(18))
    with pytest.raises(Exception):
        hour.validate_unique()


@pytest.mark.django_db
def test_get_working_window_uses_clinic_hours(clinic_setup):
    clinic, _ = clinic_setup
    target_date = timezone.localdate() + timedelta(days=1)
    window = get_working_window(clinic, target_date)
    assert window[0] == time(9)
    assert window[1] == time(12)


@pytest.mark.django_db
def test_unavailable_date_blocks_all_slots(clinic_setup):
    clinic, service = clinic_setup
    target_date = timezone.localdate() + timedelta(days=1)
    assert generate_slots(clinic, service, target_date)
    UnavailableDate.objects.create(clinic=clinic, date=target_date, reason="Holiday")
    assert generate_slots(clinic, service, target_date) == []


@pytest.mark.django_db
def test_generate_slots_respects_break_time(clinic_setup):
    clinic, service = clinic_setup
    target_date = timezone.localdate() + timedelta(days=1)
    ClinicBusinessHour.objects.update_or_create(
        clinic=clinic,
        weekday=target_date.weekday(),
        defaults={"is_open": True, "open_time": time(9), "close_time": time(12), "break_start": time(10), "break_end": time(10, 30)},
    )
    labels = [s["label"] for s in generate_slots(clinic, service, target_date)]
    assert "10:00 AM" not in labels


@pytest.mark.django_db
def test_generate_slots_respects_clinic_appointments(clinic_setup):
    clinic, service = clinic_setup
    target_date = timezone.localdate() + timedelta(days=1)
    slots = generate_slots(clinic, service, target_date)
    patient = Patient.objects.create(clinic=clinic, full_name="Patient", phone="123")
    Appointment.objects.create(clinic=clinic, patient=patient, service=service, starts_at=slots[0]["starts_at"], ends_at=slots[0]["ends_at"])
    remaining = generate_slots(clinic, service, target_date)
    assert slots[0]["starts_at"] not in [s["starts_at"] for s in remaining]


@pytest.mark.django_db
def test_slot_is_available_true_when_free(clinic_setup):
    clinic, service = clinic_setup
    target_date = timezone.localdate() + timedelta(days=1)
    slot = generate_slots(clinic, service, target_date)[0]
    assert slot_is_available(clinic, slot["starts_at"], slot["ends_at"]) is True
