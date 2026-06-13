from datetime import time, timedelta
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from appointments.forms import AppointmentStatusForm, StaffAppointmentForm
from appointments.models import Appointment
from clinics.models import Clinic, ClinicGroup
from patients.models import Patient
from scheduling.models import ClinicBusinessHour
from services.models import Service


class AppointmentInvariantTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner@example.com", email="owner@example.com", password="pass")
        self.group = ClinicGroup.objects.create(name="Group", owner=self.user)
        self.clinic = Clinic.objects.create(group=self.group, name="Clinic A", slug="clinic-a")
        self.other_clinic = Clinic.objects.create(group=self.group, name="Clinic B", slug="clinic-b")
        self.service = Service.objects.create(clinic=self.clinic, name="Consultation", duration_minutes=30)
        self.other_service = Service.objects.create(clinic=self.other_clinic, name="Other Consultation", duration_minutes=30)
        self.patient = Patient.objects.create(clinic=self.clinic, full_name="Patient A", phone="09170000000")
        self.other_patient = Patient.objects.create(clinic=self.other_clinic, full_name="Patient B", phone="09171111111")
        self.starts_at = timezone.now() + timedelta(days=1)

    def test_appointment_rejects_cross_clinic_patient(self):
        appointment = Appointment(
            clinic=self.clinic,
            patient=self.other_patient,
            service=self.service,
            starts_at=self.starts_at,
            ends_at=self.starts_at + timedelta(minutes=30),
        )

        with self.assertRaises(ValidationError) as exc:
            appointment.full_clean()

        self.assertIn("patient", exc.exception.message_dict)

    def test_appointment_rejects_cross_clinic_service(self):
        appointment = Appointment(
            clinic=self.clinic,
            patient=self.patient,
            service=self.other_service,
            starts_at=self.starts_at,
            ends_at=self.starts_at + timedelta(minutes=30),
        )

        with self.assertRaises(ValidationError) as exc:
            appointment.full_clean()

        self.assertIn("service", exc.exception.message_dict)

    def test_status_form_allows_payment_only_update(self):
        appointment = Appointment.objects.create(
            clinic=self.clinic,
            patient=self.patient,
            service=self.service,
            starts_at=self.starts_at,
            ends_at=self.starts_at + timedelta(minutes=30),
            status=Appointment.STATUS_PENDING,
            payment_state=Appointment.PAYMENT_UNPAID,
        )

        form = AppointmentStatusForm(
            data={"status": Appointment.STATUS_PENDING, "payment_state": Appointment.PAYMENT_PAID_AT_CLINIC},
            instance=appointment,
        )

        self.assertTrue(form.is_valid(), form.errors.as_text())

    def test_staff_form_excludes_archived_services(self):
        archived_service = Service.objects.create(
            clinic=self.clinic,
            name="Archived Consultation",
            duration_minutes=30,
            is_active=True,
            is_archived=True,
        )
        target_date = timezone.localdate() + timedelta(days=1)
        ClinicBusinessHour.objects.create(
            clinic=self.clinic,
            weekday=target_date.weekday(),
            is_open=True,
            open_time=time(9),
            close_time=time(17),
        )

        form = StaffAppointmentForm(self.clinic)
        self.assertNotIn(archived_service, form.fields["service"].queryset)

        post_form = StaffAppointmentForm(
            self.clinic,
            data={
                "patient_name": "New Patient",
                "patient_phone": "09172222222",
                "patient_email": "new.patient@example.com",
                "date": target_date.isoformat(),
                "time": "09:00",
                "service": archived_service.id,
                "status": Appointment.STATUS_PENDING,
                "payment_state": Appointment.PAYMENT_UNPAID,
                "source": Appointment.SOURCE_STAFF,
                "reason": "",
            },
        )

        self.assertFalse(post_form.is_valid())
        self.assertIn("service", post_form.errors)

    def test_staff_form_requires_patient_email(self):
        target_date = timezone.localdate() + timedelta(days=1)
        ClinicBusinessHour.objects.create(
            clinic=self.clinic,
            weekday=target_date.weekday(),
            is_open=True,
            open_time=time(9),
            close_time=time(17),
        )

        form = StaffAppointmentForm(
            self.clinic,
            data={
                "patient_name": "New Patient",
                "patient_phone": "09172222222",
                "patient_email": "",
                "date": target_date.isoformat(),
                "time": "09:00",
                "service": self.service.id,
                "status": Appointment.STATUS_PENDING,
                "payment_state": Appointment.PAYMENT_UNPAID,
                "source": Appointment.SOURCE_STAFF,
                "reason": "",
            },
        )

        self.assertFalse(form.is_valid())
        self.assertIn("patient_email", form.errors)

    def test_staff_form_initializes_existing_appointment_in_clinic_timezone(self):
        self.clinic.timezone = "America/Los_Angeles"
        self.clinic.save(update_fields=["timezone"])
        clinic_tz = ZoneInfo(self.clinic.timezone)
        local_start = timezone.datetime(2026, 1, 10, 23, 30, tzinfo=clinic_tz)
        appointment = Appointment.objects.create(
            clinic=self.clinic,
            patient=self.patient,
            service=self.service,
            starts_at=local_start,
            ends_at=local_start + timedelta(minutes=30),
        )

        form = StaffAppointmentForm(self.clinic, instance=Appointment.objects.get(pk=appointment.pk))

        self.assertEqual(form.fields["date"].initial, local_start.date())
        self.assertEqual(form.fields["time"].initial, local_start.time().replace(second=0, microsecond=0))

    def test_staff_form_rejects_invalid_status_transition(self):
        target_date = timezone.localdate() + timedelta(days=1)
        ClinicBusinessHour.objects.create(
            clinic=self.clinic,
            weekday=target_date.weekday(),
            is_open=True,
            open_time=time(9),
            close_time=time(17),
        )
        starts_at = timezone.make_aware(timezone.datetime.combine(target_date, time(9)))
        appointment = Appointment.objects.create(
            clinic=self.clinic,
            patient=self.patient,
            service=self.service,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=30),
            status=Appointment.STATUS_COMPLETED,
        )

        form = StaffAppointmentForm(
            self.clinic,
            data={
                "patient_name": self.patient.full_name,
                "patient_phone": self.patient.phone,
                "patient_email": "patient@example.com",
                "date": target_date.isoformat(),
                "time": "09:00",
                "service": self.service.id,
                "status": Appointment.STATUS_PENDING,
                "payment_state": Appointment.PAYMENT_UNPAID,
                "source": Appointment.SOURCE_STAFF,
                "reason": "",
            },
            instance=appointment,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("status", form.errors)

    def test_staff_form_rejects_short_patient_phone(self):
        target_date = timezone.localdate() + timedelta(days=1)
        ClinicBusinessHour.objects.create(
            clinic=self.clinic,
            weekday=target_date.weekday(),
            is_open=True,
            open_time=time(9),
            close_time=time(17),
        )

        form = StaffAppointmentForm(
            self.clinic,
            data={
                "patient_name": "New Patient",
                "patient_phone": "123456",
                "patient_email": "new.patient@example.com",
                "date": target_date.isoformat(),
                "time": "09:00",
                "service": self.service.id,
                "status": Appointment.STATUS_PENDING,
                "payment_state": Appointment.PAYMENT_UNPAID,
                "source": Appointment.SOURCE_STAFF,
                "reason": "",
            },
        )

        self.assertFalse(form.is_valid())
        self.assertIn("patient_phone", form.errors)
