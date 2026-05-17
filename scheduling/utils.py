from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from appointments.models import Appointment
from scheduling.models import BlockedTime, ClinicBusinessHour, UnavailableDate


def _localize(clinic, date_value, time_value):
    tz = ZoneInfo(clinic.timezone)
    return timezone.make_aware(datetime.combine(date_value, time_value), tz)


def _inside_break(start_time, end_time, break_start, break_end):
    if not break_start or not break_end:
        return False
    return start_time < break_end and end_time > break_start


def get_working_window(clinic, date_value):
    weekday = date_value.weekday()
    clinic_hours = ClinicBusinessHour.objects.filter(clinic=clinic, weekday=weekday, is_open=True).first()
    if clinic_hours:
        return clinic_hours.open_time, clinic_hours.close_time, clinic_hours.break_start, clinic_hours.break_end
    return None


def slot_is_available(clinic, starts_at, ends_at):
    return not (
        Appointment.objects.filter(
            clinic=clinic,
            starts_at__lt=ends_at,
            ends_at__gt=starts_at,
        )
        .exclude(status=Appointment.STATUS_CANCELLED)
        .exists()
        or BlockedTime.objects.filter(
            clinic=clinic,
            starts_at__lt=ends_at,
            ends_at__gt=starts_at,
        )
        .exists()
    )


def slot_is_available_for_appointment(clinic, starts_at, ends_at, exclude_appointment=None):
    qs = Appointment.objects.filter(
        clinic=clinic,
        starts_at__lt=ends_at,
        ends_at__gt=starts_at,
    ).exclude(status=Appointment.STATUS_CANCELLED)
    if exclude_appointment:
        qs = qs.exclude(pk=exclude_appointment.pk)
    if qs.exists():
        return False
    blocked_qs = BlockedTime.objects.filter(
        clinic=clinic,
        starts_at__lt=ends_at,
        ends_at__gt=starts_at,
    )
    if blocked_qs.exists():
        return False
    return True


def validate_slot(clinic, starts_at, ends_at, exclude_appointment=None):
    from django.core.exceptions import ValidationError
    window = get_working_window(clinic, starts_at.date())
    if not window:
        raise ValidationError("Clinic is not open on this day.")
    open_time, close_time, break_start, break_end = window
    if starts_at.time() < open_time or ends_at.time() > close_time:
        raise ValidationError("Selected time is outside working hours.")
    if _inside_break(starts_at.time(), ends_at.time(), break_start, break_end):
        raise ValidationError("Selected time overlaps with a scheduled break.")
    if not slot_is_available_for_appointment(clinic, starts_at, ends_at, exclude_appointment):
        raise ValidationError("This slot is not available.")


def _date_is_unavailable(clinic, date_value):
    return UnavailableDate.objects.filter(clinic=clinic, date=date_value).exists()


def generate_slots(clinic, service, date_value):
    if _date_is_unavailable(clinic, date_value):
        return []
    duration = service.effective_duration()
    window = get_working_window(clinic, date_value)
    if not window:
        return []
    open_time, close_time, break_start, break_end = window
    tz = ZoneInfo(clinic.timezone)
    now = timezone.now().astimezone(tz)
    cursor = _localize(clinic, date_value, open_time)
    close_dt = _localize(clinic, date_value, close_time)
    slots = []
    while cursor + timedelta(minutes=duration) <= close_dt:
        end = cursor + timedelta(minutes=duration)
        if cursor > now and not _inside_break(cursor.time(), end.time(), break_start, break_end):
            utc_start = cursor.astimezone(ZoneInfo("UTC"))
            utc_end = end.astimezone(ZoneInfo("UTC"))
            if slot_is_available(clinic, utc_start, utc_end):
                slots.append({"starts_at": utc_start, "ends_at": utc_end, "label": cursor.strftime("%I:%M %p").lstrip("0")})
        cursor = end
    return slots
