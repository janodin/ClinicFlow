from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from appointments.forms import AppointmentStatusForm, StaffAppointmentForm
from appointments.models import Appointment
from clinics.models import Clinic, ClinicGroup
from patients.models import Patient
from scheduling.models import UnavailableDate
from scheduling.utils import generate_slots, validate_slot


@pytest.mark.django_db
def test_patient_matching_is_scoped_to_clinic(clinic_setup):
    clinic, _ = clinic_setup
    patient, created = Patient.find_or_create_for_booking(clinic, "Juan Dela Cruz", "0917-000-1111", "a@example.com")
    same, same_created = Patient.find_or_create_for_booking(clinic, "Juan", "09170001111", "b@example.com")
    other_group = ClinicGroup.objects.create(name="Other", owner=clinic.group.owner)
    other_clinic = Clinic.objects.create(group=other_group, name="Other", slug="other")
    other, other_created = Patient.find_or_create_for_booking(other_clinic, "Juan", "09170001111")
    assert created is True
    assert same_created is False
    assert same.id == patient.id
    assert other_created is True
    assert other.id != patient.id


@pytest.mark.django_db
def test_slot_generation_blocks_clinic_overlap(clinic_setup):
    clinic, service = clinic_setup
    target_date = timezone.localdate() + timedelta(days=1)
    slots = generate_slots(clinic, service, target_date)
    patient = Patient.objects.create(clinic=clinic, full_name="Patient", phone="123")
    Appointment.objects.create(clinic=clinic, patient=patient, service=service, starts_at=slots[0]["starts_at"], ends_at=slots[0]["ends_at"])
    remaining = generate_slots(clinic, service, target_date)
    assert slots[0]["starts_at"] not in [slot["starts_at"] for slot in remaining]


@pytest.mark.django_db
def test_different_service_same_time_allowed_in_same_clinic(clinic_setup):
    clinic, cleaning = clinic_setup
    filling = cleaning.__class__.objects.create(clinic=clinic, name="Tooth Filling", duration_minutes=30)
    patient_one = Patient.objects.create(clinic=clinic, full_name="Patient One", phone="111")
    patient_two = Patient.objects.create(clinic=clinic, full_name="Patient Two", phone="222")
    starts_at = timezone.now() + timedelta(days=2)
    ends_at = starts_at + timedelta(minutes=30)

    Appointment.objects.create(clinic=clinic, patient=patient_one, service=cleaning, starts_at=starts_at, ends_at=ends_at)
    Appointment.objects.create(clinic=clinic, patient=patient_two, service=filling, starts_at=starts_at, ends_at=ends_at)

    assert Appointment.objects.filter(clinic=clinic, starts_at=starts_at).count() == 2


@pytest.mark.django_db
def test_same_patient_overlapping_different_service_is_rejected(clinic_setup):
    clinic, cleaning = clinic_setup
    filling = cleaning.__class__.objects.create(clinic=clinic, name="Tooth Filling", duration_minutes=30)
    patient = Patient.objects.create(clinic=clinic, full_name="Patient", phone="09170001111")
    starts_at = timezone.now() + timedelta(days=2)
    ends_at = starts_at + timedelta(minutes=30)

    Appointment.objects.create(clinic=clinic, patient=patient, service=cleaning, starts_at=starts_at, ends_at=ends_at)

    with pytest.raises(ValidationError, match="already has an active appointment"):
        Appointment.objects.create(
            clinic=clinic,
            patient=patient,
            service=filling,
            starts_at=starts_at + timedelta(minutes=15),
            ends_at=ends_at + timedelta(minutes=15),
        )


@pytest.mark.django_db
def test_same_service_capacity_one_blocks_second_overlap(clinic_setup):
    clinic, service = clinic_setup
    patient_one = Patient.objects.create(clinic=clinic, full_name="Patient One", phone="111")
    patient_two = Patient.objects.create(clinic=clinic, full_name="Patient Two", phone="222")
    starts_at = timezone.now() + timedelta(days=2)
    ends_at = starts_at + timedelta(minutes=30)

    Appointment.objects.create(clinic=clinic, patient=patient_one, service=service, starts_at=starts_at, ends_at=ends_at)

    with pytest.raises(ValidationError):
        Appointment.objects.create(clinic=clinic, patient=patient_two, service=service, starts_at=starts_at, ends_at=ends_at)


@pytest.mark.django_db
def test_same_service_capacity_two_allows_two_and_blocks_third(clinic_setup):
    clinic, service = clinic_setup
    service.simultaneous_capacity = 2
    service.save(update_fields=["simultaneous_capacity", "updated_at"])
    starts_at = timezone.now() + timedelta(days=2)
    ends_at = starts_at + timedelta(minutes=30)
    patients = [
        Patient.objects.create(clinic=clinic, full_name="Patient One", phone="111"),
        Patient.objects.create(clinic=clinic, full_name="Patient Two", phone="222"),
        Patient.objects.create(clinic=clinic, full_name="Patient Three", phone="333"),
    ]

    Appointment.objects.create(clinic=clinic, patient=patients[0], service=service, starts_at=starts_at, ends_at=ends_at)
    Appointment.objects.create(clinic=clinic, patient=patients[1], service=service, starts_at=starts_at, ends_at=ends_at)

    with pytest.raises(ValidationError):
        Appointment.objects.create(clinic=clinic, patient=patients[2], service=service, starts_at=starts_at, ends_at=ends_at)


@pytest.mark.django_db
def test_same_patient_same_service_same_start_is_duplicate_even_with_capacity(clinic_setup):
    clinic, service = clinic_setup
    service.simultaneous_capacity = 2
    service.save(update_fields=["simultaneous_capacity", "updated_at"])
    patient = Patient.objects.create(clinic=clinic, full_name="Patient", phone="123")
    starts_at = timezone.now() + timedelta(days=2)
    ends_at = starts_at + timedelta(minutes=30)

    Appointment.objects.create(clinic=clinic, patient=patient, service=service, starts_at=starts_at, ends_at=ends_at)

    with pytest.raises(ValidationError):
        Appointment.objects.create(clinic=clinic, patient=patient, service=service, starts_at=starts_at, ends_at=ends_at)


@pytest.mark.django_db
def test_adjacent_same_service_appointments_do_not_consume_same_capacity(clinic_setup):
    clinic, service = clinic_setup
    patient_one = Patient.objects.create(clinic=clinic, full_name="Patient One", phone="111")
    patient_two = Patient.objects.create(clinic=clinic, full_name="Patient Two", phone="222")
    starts_at = timezone.now() + timedelta(days=2)
    ends_at = starts_at + timedelta(minutes=30)

    Appointment.objects.create(clinic=clinic, patient=patient_one, service=service, starts_at=starts_at, ends_at=ends_at)
    Appointment.objects.create(clinic=clinic, patient=patient_two, service=service, starts_at=ends_at, ends_at=ends_at + timedelta(minutes=30))

    assert Appointment.objects.filter(clinic=clinic, service=service).count() == 2


@pytest.mark.django_db
def test_double_booking_validation_is_clinic_scoped(clinic_setup):
    clinic, service = clinic_setup
    patient = Patient.objects.create(clinic=clinic, full_name="Patient", phone="123")
    starts_at = timezone.now() + timedelta(days=2)
    ends_at = starts_at + timedelta(minutes=30)
    Appointment.objects.create(clinic=clinic, patient=patient, service=service, starts_at=starts_at, ends_at=ends_at)
    with pytest.raises(ValidationError):
        Appointment.objects.create(clinic=clinic, patient=patient, service=service, starts_at=starts_at, ends_at=ends_at)


@pytest.mark.django_db
def test_cross_clinic_same_time_allowed(clinic_setup):
    clinic, service = clinic_setup
    patient = Patient.objects.create(clinic=clinic, full_name="Patient", phone="123")
    starts_at = timezone.now() + timedelta(days=2)
    ends_at = starts_at + timedelta(minutes=30)
    Appointment.objects.create(clinic=clinic, patient=patient, service=service, starts_at=starts_at, ends_at=ends_at)
    other_group = ClinicGroup.objects.create(name="Other", owner=clinic.group.owner)
    other_clinic = Clinic.objects.create(group=other_group, name="Other", slug="other-clinic")
    other_service = service.__class__.objects.create(clinic=other_clinic, name="General Consultation", duration_minutes=30)
    other_patient = Patient.objects.create(clinic=other_clinic, full_name="Other", phone="999")
    Appointment.objects.create(clinic=other_clinic, patient=other_patient, service=other_service, starts_at=starts_at, ends_at=ends_at)


@pytest.mark.django_db
def test_cancelled_appointment_frees_slot(clinic_setup):
    clinic, service = clinic_setup
    target_date = timezone.localdate() + timedelta(days=1)
    slots = generate_slots(clinic, service, target_date)
    patient = Patient.objects.create(clinic=clinic, full_name="Patient", phone="123")
    Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=slots[0]["starts_at"],
        ends_at=slots[0]["ends_at"],
        status=Appointment.STATUS_CANCELLED,
    )
    remaining = generate_slots(clinic, service, target_date)
    assert slots[0]["starts_at"] in [slot["starts_at"] for slot in remaining]


@pytest.mark.django_db
def test_invalid_status_transition_blocked(clinic_setup):
    clinic, service = clinic_setup
    patient = Patient.objects.create(clinic=clinic, full_name="Patient", phone="123")
    starts_at = timezone.now() + timedelta(days=2)
    appt = Appointment.objects.create(clinic=clinic, patient=patient, service=service, starts_at=starts_at, ends_at=starts_at + timedelta(minutes=30))
    form = AppointmentStatusForm(data={"status": Appointment.STATUS_COMPLETED, "payment_state": Appointment.PAYMENT_UNPAID}, instance=appt)
    assert not form.is_valid()


@pytest.mark.django_db
def test_staff_form_validates_same_service_capacity(clinic_setup):
    clinic, service = clinic_setup
    target_date = timezone.localdate() + timedelta(days=1)
    slots = generate_slots(clinic, service, target_date)
    patient = Patient.objects.create(clinic=clinic, full_name="Patient", phone="123")
    Appointment.objects.create(clinic=clinic, patient=patient, service=service, starts_at=slots[0]["starts_at"], ends_at=slots[0]["ends_at"])
    local_time = slots[0]["starts_at"].astimezone(ZoneInfo(clinic.timezone)).strftime("%H:%M")
    form = StaffAppointmentForm(clinic, data={
        "patient_name": "New",
        "patient_phone": "1234567",
        "patient_email": "new@example.com",
        "service": service.id,
        "date": target_date.isoformat(),
        "time": local_time,
        "status": Appointment.STATUS_PENDING,
        "payment_state": Appointment.PAYMENT_UNPAID,
        "source": Appointment.SOURCE_STAFF,
    })
    assert not form.is_valid()


@pytest.mark.django_db
def test_staff_form_allows_different_service_same_time(clinic_setup):
    clinic, cleaning = clinic_setup
    filling = cleaning.__class__.objects.create(clinic=clinic, name="Tooth Filling", duration_minutes=30)
    target_date = timezone.localdate() + timedelta(days=1)
    slots = generate_slots(clinic, cleaning, target_date)
    patient = Patient.objects.create(clinic=clinic, full_name="Patient", phone="123")
    Appointment.objects.create(clinic=clinic, patient=patient, service=cleaning, starts_at=slots[0]["starts_at"], ends_at=slots[0]["ends_at"])
    local_time = slots[0]["starts_at"].astimezone(ZoneInfo(clinic.timezone)).strftime("%H:%M")
    form = StaffAppointmentForm(clinic, data={
        "patient_name": "New",
        "patient_phone": "1234567",
        "patient_email": "new@example.com",
        "service": filling.id,
        "date": target_date.isoformat(),
        "time": local_time,
        "status": Appointment.STATUS_PENDING,
        "payment_state": Appointment.PAYMENT_UNPAID,
        "source": Appointment.SOURCE_STAFF,
    })

    assert form.is_valid(), form.errors.as_text()


@pytest.mark.django_db
def test_staff_form_rejects_existing_patient_overlapping_different_service(clinic_setup):
    clinic, cleaning = clinic_setup
    filling = cleaning.__class__.objects.create(clinic=clinic, name="Tooth Filling", duration_minutes=30)
    target_date = timezone.localdate() + timedelta(days=1)
    slots = generate_slots(clinic, cleaning, target_date)
    patient = Patient.objects.create(clinic=clinic, full_name="Patient", phone="09170001111")
    Appointment.objects.create(clinic=clinic, patient=patient, service=cleaning, starts_at=slots[0]["starts_at"], ends_at=slots[0]["ends_at"])
    local_time = slots[0]["starts_at"].astimezone(ZoneInfo(clinic.timezone)).strftime("%H:%M")
    form = StaffAppointmentForm(clinic, data={
        "patient_name": "Patient",
        "patient_phone": "0917-000-1111",
        "patient_email": "patient@example.com",
        "service": filling.id,
        "date": target_date.isoformat(),
        "time": local_time,
        "status": Appointment.STATUS_PENDING,
        "payment_state": Appointment.PAYMENT_UNPAID,
        "source": Appointment.SOURCE_STAFF,
    })

    assert not form.is_valid()
    assert "already has an active appointment" in form.errors.as_text().lower()


@pytest.mark.django_db
def test_staff_form_rejects_unavailable_date(clinic_setup):
    clinic, service = clinic_setup
    target_date = timezone.localdate() + timedelta(days=1)
    UnavailableDate.objects.create(clinic=clinic, date=target_date, reason="Holiday")

    form = StaffAppointmentForm(clinic, data={
        "patient_name": "New",
        "patient_phone": "1234",
        "patient_email": "new@example.com",
        "service": service.id,
        "date": target_date.isoformat(),
        "time": "09:00",
        "status": Appointment.STATUS_PENDING,
        "payment_state": Appointment.PAYMENT_UNPAID,
        "source": Appointment.SOURCE_STAFF,
    })

    assert not form.is_valid()
    assert "not available" in form.errors.as_text().lower()


@pytest.mark.django_db
def test_validate_slot_rejects_unavailable_date(clinic_setup):
    clinic, service = clinic_setup
    target_date = timezone.localdate() + timedelta(days=1)
    UnavailableDate.objects.create(clinic=clinic, date=target_date, reason="Holiday")
    starts_at = timezone.make_aware(datetime.combine(target_date, time(9)), ZoneInfo(clinic.timezone))
    ends_at = starts_at + timedelta(minutes=service.effective_duration())

    with pytest.raises(ValidationError, match="not available"):
        validate_slot(clinic, service, starts_at, ends_at)


@pytest.mark.django_db
def test_validate_slot_checks_unavailable_date_in_clinic_timezone(clinic_setup):
    clinic, service = clinic_setup
    target_date = timezone.localdate() + timedelta(days=1)
    clinic.business_hours.update(open_time=time(0), close_time=time(1))
    UnavailableDate.objects.create(clinic=clinic, date=target_date, reason="Holiday")
    local_start = timezone.make_aware(datetime.combine(target_date, time(0, 30)), ZoneInfo(clinic.timezone))
    starts_at = local_start.astimezone(ZoneInfo("UTC"))
    ends_at = starts_at + timedelta(minutes=service.effective_duration())

    with pytest.raises(ValidationError, match="not available"):
        validate_slot(clinic, service, starts_at, ends_at)
