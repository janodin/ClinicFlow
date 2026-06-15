def overlapping_active_appointments(clinic, service, starts_at, ends_at, exclude_appointment=None):
    from appointments.models import Appointment

    qs = Appointment.objects.filter(
        clinic=clinic,
        service=service,
        starts_at__lt=ends_at,
        ends_at__gt=starts_at,
    ).exclude(status=Appointment.STATUS_CANCELLED)
    if exclude_appointment and exclude_appointment.pk:
        qs = qs.exclude(pk=exclude_appointment.pk)
    return qs


def service_capacity_available(clinic, service, starts_at, ends_at, exclude_appointment=None):
    capacity = service.simultaneous_capacity or 1
    return overlapping_active_appointments(
        clinic,
        service,
        starts_at,
        ends_at,
        exclude_appointment=exclude_appointment,
    ).count() < capacity


def overlapping_active_patient_appointments(clinic, patient, starts_at, ends_at, exclude_appointment=None):
    from appointments.models import Appointment

    qs = Appointment.objects.filter(
        clinic=clinic,
        patient=patient,
        starts_at__lt=ends_at,
        ends_at__gt=starts_at,
    ).exclude(status=Appointment.STATUS_CANCELLED)
    if exclude_appointment and exclude_appointment.pk:
        qs = qs.exclude(pk=exclude_appointment.pk)
    return qs


def patient_has_overlapping_active_appointment(clinic, patient, starts_at, ends_at, exclude_appointment=None):
    return overlapping_active_patient_appointments(
        clinic,
        patient,
        starts_at,
        ends_at,
        exclude_appointment=exclude_appointment,
    ).exists()


def duplicate_active_appointment_exists(clinic, patient, service, starts_at, exclude_appointment=None):
    from appointments.models import Appointment

    qs = Appointment.objects.filter(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=starts_at,
    ).exclude(status=Appointment.STATUS_CANCELLED)
    if exclude_appointment and exclude_appointment.pk:
        qs = qs.exclude(pk=exclude_appointment.pk)
    return qs.exists()
