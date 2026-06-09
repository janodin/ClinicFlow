from datetime import date, datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from django.utils import timezone

from appointments.models import Appointment
from clinics.models import Clinic, ClinicAISettings
from patients.models import normalize_phone
from scheduling.models import Weekday
from scheduling.utils import generate_slots, validate_slot
from widget.views import PAST_APPOINTMENT_TIME_MESSAGE, _process_guest_booking

from .defaults import DEFAULT_AI_FALLBACK_MESSAGE, DEFAULT_MESSENGER_AI_PROMPT
from .models import MessengerConnection, MessengerConversation


STALE_MESSENGER_TURN_ERROR = "This Messenger request was superseded by a newer user message. Please use the latest conversation turn."


def get_or_create_clinic_ai_settings(clinic):
    settings, _ = ClinicAISettings.objects.get_or_create(clinic=clinic)
    return settings


def get_clinic_for_slug(clinic_slug):
    if not clinic_slug:
        return None
    return Clinic.objects.filter(slug=clinic_slug, is_active=True, requires_onboarding=False).first()


def _clean_turn_sequence(value):
    try:
        sequence = int(value)
    except (TypeError, ValueError):
        return 0
    return sequence if sequence > 0 else 0


def _validate_messenger_turn_metadata(connection, psid="", turn_token="", input_sequence=None, lock=False):
    clean_psid = str(psid or "").strip()
    clean_turn_token = str(turn_token or "").strip()
    clean_input_sequence = _clean_turn_sequence(input_sequence)
    if not clean_turn_token and not clean_input_sequence:
        return ""
    if not connection or not clean_psid or not clean_turn_token or not clean_input_sequence:
        return STALE_MESSENGER_TURN_ERROR
    conversations = MessengerConversation.objects.filter(connection=connection, psid=clean_psid)
    if lock:
        conversations = conversations.select_for_update()
    conversation = conversations.first()
    if not conversation:
        return STALE_MESSENGER_TURN_ERROR
    if (
        conversation.active_turn_token != clean_turn_token
        or conversation.active_input_sequence != clean_input_sequence
        or conversation.last_sequence > clean_input_sequence
    ):
        return STALE_MESSENGER_TURN_ERROR
    return ""


def _ai_payload_for_clinic(clinic):
    ai_settings = get_or_create_clinic_ai_settings(clinic)
    return {
        "is_ai_enabled": ai_settings.is_ai_enabled,
        "messenger_response_mode": ai_settings.safe_messenger_response_mode,
        "communication_tone": ai_settings.safe_communication_tone,
        "communication_tone_label": ai_settings.communication_tone_label,
        "custom_tone_instructions": ai_settings.custom_tone_instructions,
        "instructions": ai_settings.instructions or DEFAULT_MESSENGER_AI_PROMPT,
        "fallback_message": ai_settings.fallback_message or DEFAULT_AI_FALLBACK_MESSAGE,
        "settings_updated_at": ai_settings.updated_at.isoformat(),
    }


def _website_ai_disabled_response_for_clinic(clinic):
    ai_settings = get_or_create_clinic_ai_settings(clinic)
    if not ai_settings.is_ai_enabled:
        return {
            "found": True,
            "disabled": True,
            "fallback_message": ai_settings.fallback_message or DEFAULT_AI_FALLBACK_MESSAGE,
        }
    return None


def _service_payload(service):
    return {
        "id": service.id,
        "name": service.name,
        "description": service.description,
        "duration_minutes": service.effective_duration(),
        "price": str(service.price),
        "display_price": service.display_price,
    }


def _slot_payload(clinic, slot):
    local_start = slot["starts_at"].astimezone(ZoneInfo(clinic.timezone))
    local_end = slot["ends_at"].astimezone(ZoneInfo(clinic.timezone))
    return {
        "starts_at": slot["starts_at"].isoformat(),
        "ends_at": slot["ends_at"].isoformat(),
        "local_starts_at": local_start.isoformat(),
        "local_ends_at": local_end.isoformat(),
        "label": slot.get("label") or local_start.strftime("%I:%M %p").lstrip("0"),
    }


def _time_payload(value):
    return value.strftime("%H:%M") if value else None


def _business_hours_payload(clinic):
    hours_by_weekday = {hour.weekday: hour for hour in clinic.business_hours.all()}
    weekday_labels = dict(Weekday.choices)
    payload = []
    for weekday in range(7):
        hour = hours_by_weekday.get(weekday)
        payload.append({
            "weekday": weekday,
            "day": weekday_labels[weekday],
            "is_open": bool(hour and hour.is_open),
            "open_time": _time_payload(hour.open_time) if hour else None,
            "close_time": _time_payload(hour.close_time) if hour else None,
            "break_start": _time_payload(hour.break_start) if hour else None,
            "break_end": _time_payload(hour.break_end) if hour else None,
        })
    return payload


def _unavailable_dates_payload(clinic):
    return [
        {"date": unavailable.date.isoformat(), "reason": unavailable.reason}
        for unavailable in clinic.unavailable_dates.order_by("date")
    ]


def _clinic_localdate(clinic):
    return timezone.now().astimezone(ZoneInfo(clinic.timezone)).date()


def _parse_datetime(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value))
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed.astimezone(dt_timezone.utc)


def _parse_clinic_datetime(clinic, value):
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, ZoneInfo(clinic.timezone))
    return parsed.astimezone(dt_timezone.utc)


def _validation_error_text(error):
    if hasattr(error, "messages"):
        return " ".join(str(message) for message in error.messages)
    return str(error)


APPOINTMENT_LOOKUP_ERROR = "Appointment not found. Please check the reference code and phone number."
CONFIRMATION_REQUIRED_ERROR = "Appointment change requires explicit user confirmation."


def _availability_error_response(error, requested_date=None):
    return {
        "found": True,
        "available": False,
        "error": error,
        "selected_slot": None,
        "alternatives": [],
        "suggestion_type": "none",
        "requested_date": requested_date.isoformat() if requested_date else None,
        "suggested_date": None,
    }


def _appointment_summary(clinic, appointment):
    local_start = appointment.starts_at.astimezone(ZoneInfo(clinic.timezone))
    digits = normalize_phone(appointment.patient.phone)
    return {
        "reference_code": appointment.reference_code,
        "service_id": appointment.service_id,
        "service": appointment.service.name,
        "status": appointment.status,
        "starts_at": appointment.starts_at.isoformat(),
        "local_starts_at": local_start.isoformat(),
        "patient_name": appointment.patient.full_name,
        "patient_phone_last4": digits[-4:] if len(digits) >= 4 else digits,
        "local_date_label": local_start.strftime("%A, %B %d"),
        "local_time_label": local_start.strftime("%I:%M %p").lstrip("0"),
    }


def _verified_appointment_for_clinic(clinic, reference_code, phone):
    reference = (reference_code or "").strip().upper()
    normalized_phone = normalize_phone(phone)
    if not reference or not normalized_phone:
        return None, "Please provide the appointment reference code and phone number."

    appointment = (
        clinic.appointments.select_related("patient", "service")
        .filter(reference_code__iexact=reference, patient__normalized_phone=normalized_phone)
        .first()
    )
    if not appointment:
        return None, APPOINTMENT_LOOKUP_ERROR
    if appointment.starts_at <= timezone.now():
        return None, "Past appointments cannot be changed through the assistant."
    if appointment.status not in {Appointment.STATUS_PENDING, Appointment.STATUS_CONFIRMED}:
        return None, "This appointment cannot be changed through the assistant."
    return appointment, ""


def _find_verified_appointment_for_clinic(clinic, reference_code, phone):
    appointment, error = _verified_appointment_for_clinic(clinic, reference_code, phone)
    if error:
        return {"found": False, "error": error}
    return {"found": True, "appointment": _appointment_summary(clinic, appointment)}


def get_connection_for_page(page_id):
    if not page_id:
        return None
    return (
        MessengerConnection.objects.select_related("clinic")
        .filter(
            page_id=page_id,
            page_access_token__gt="",
            is_active=True,
            clinic__is_active=True,
            clinic__requires_onboarding=False,
        )
        .first()
    )


def build_ai_context(page_id):
    connection = get_connection_for_page(page_id)
    if not connection:
        return {"found": False}

    clinic = connection.clinic
    services = clinic.services.filter(is_active=True, is_archived=False).order_by("name")
    faqs = clinic.faqs.filter(is_active=True).order_by("question")
    clinic_now = timezone.now().astimezone(ZoneInfo(clinic.timezone))
    return {
        "found": True,
        "page_id": connection.page_id,
        "page_token": connection.page_access_token,
        "page_token_available": bool(connection.page_access_token),
        "current_time": {
            "timezone": clinic.timezone,
            "now": clinic_now.isoformat(),
            "today": clinic_now.date().isoformat(),
        },
        "clinic": {
            "id": clinic.id,
            "name": clinic.name,
            "address": clinic.address,
            "phone": clinic.phone,
            "email": clinic.email,
            "timezone": clinic.timezone,
        },
        "ai": _ai_payload_for_clinic(clinic),
        "services": [_service_payload(service) for service in services],
        "faqs": [{"question": faq.question, "answer": faq.answer} for faq in faqs],
        "business_hours": _business_hours_payload(clinic),
        "unavailable_dates": _unavailable_dates_payload(clinic),
    }


def build_widget_ai_context(clinic_slug):
    clinic = get_clinic_for_slug(clinic_slug)
    if not clinic:
        return {"found": False}
    services = clinic.services.filter(is_active=True, is_archived=False).order_by("name")
    faqs = clinic.faqs.filter(is_active=True).order_by("question")
    clinic_now = timezone.now().astimezone(ZoneInfo(clinic.timezone))
    return {
        "found": True,
        "channel": "widget",
        "current_time": {
            "timezone": clinic.timezone,
            "now": clinic_now.isoformat(),
            "today": clinic_now.date().isoformat(),
        },
        "clinic": {
            "id": clinic.id,
            "slug": clinic.slug,
            "name": clinic.name,
            "address": clinic.address,
            "phone": clinic.phone,
            "email": clinic.email,
            "timezone": clinic.timezone,
        },
        "ai": _ai_payload_for_clinic(clinic),
        "services": [_service_payload(service) for service in services],
        "faqs": [{"question": faq.question, "answer": faq.answer} for faq in faqs],
        "business_hours": _business_hours_payload(clinic),
        "unavailable_dates": _unavailable_dates_payload(clinic),
    }


def match_services(page_id, query):
    connection = get_connection_for_page(page_id)
    if not connection:
        return {"found": False, "matches": []}
    query_text = (query or "").strip().lower()
    services = connection.clinic.services.filter(is_active=True, is_archived=False).order_by("name")
    if query_text:
        matches = [
            service for service in services
            if query_text in service.name.lower() or query_text in service.description.lower()
        ]
    else:
        matches = list(services)
    return {"found": True, "matches": [_service_payload(service) for service in matches]}


def match_widget_services(clinic_slug, query):
    clinic = get_clinic_for_slug(clinic_slug)
    if not clinic:
        return {"found": False, "matches": []}
    disabled = _website_ai_disabled_response_for_clinic(clinic)
    if disabled:
        return {**disabled, "matches": []}
    query_text = (query or "").strip().lower()
    services = clinic.services.filter(is_active=True, is_archived=False).order_by("name")
    if query_text:
        matches = [
            service for service in services
            if query_text in service.name.lower() or query_text in service.description.lower()
        ]
    else:
        matches = list(services)
    return {"found": True, "matches": [_service_payload(service) for service in matches]}


def _slots_for_date(clinic, service, date_value):
    return [_slot_payload(clinic, slot) for slot in generate_slots(clinic, service, date_value)]


def check_availability(page_id, service_id, preferred_starts_at=None, preferred_date=None):
    connection = get_connection_for_page(page_id)
    if not connection:
        return {"found": False, "available": False, "alternatives": []}
    return _check_availability_for_clinic(connection.clinic, service_id, preferred_starts_at, preferred_date)


def _check_availability_for_clinic(clinic, service_id, preferred_starts_at=None, preferred_date=None):
    try:
        requested_start = _parse_datetime(preferred_starts_at) if preferred_starts_at else None
        if requested_start:
            target_date = requested_start.astimezone(ZoneInfo(clinic.timezone)).date()
        elif preferred_date:
            target_date = date.fromisoformat(str(preferred_date))
        else:
            target_date = _clinic_localdate(clinic) + timedelta(days=1)
    except (ValueError, TypeError):
        return _availability_error_response("Invalid date or time.")

    clinic_today = _clinic_localdate(clinic)
    if target_date < clinic_today or (requested_start and requested_start <= timezone.now()):
        return _availability_error_response(PAST_APPOINTMENT_TIME_MESSAGE, target_date)

    service = clinic.services.filter(pk=service_id, is_active=True, is_archived=False).first()
    if not service:
        return _availability_error_response("Service not found.")

    raw_slots = generate_slots(clinic, service, target_date)
    selected = None
    if requested_start:
        selected = next((slot for slot in raw_slots if slot["starts_at"] == requested_start), None)

    suggestion_type = "none"
    suggested_date = None
    if requested_start:
        alternatives = sorted(raw_slots, key=lambda slot: abs(slot["starts_at"] - requested_start))
        alternatives = [slot for slot in alternatives if slot["starts_at"] != requested_start]
        if alternatives:
            suggestion_type = "requested_date" if selected else "nearest_time"
            suggested_date = target_date
    else:
        alternatives = raw_slots
        if alternatives:
            suggestion_type = "requested_date"
            suggested_date = target_date

    if not alternatives and not selected:
        search_date = target_date
        while search_date < target_date + timedelta(days=14):
            search_date += timedelta(days=1)
            alternatives = generate_slots(clinic, service, search_date)
            if alternatives:
                suggestion_type = "next_available_date"
                suggested_date = search_date
                break

    available = selected is not None or (requested_start is None and suggested_date == target_date)

    payload_alternatives = alternatives[:3] if requested_start else alternatives

    return {
        "found": True,
        "available": available,
        "selected_slot": _slot_payload(clinic, selected) if selected else None,
        "alternatives": [_slot_payload(clinic, slot) for slot in payload_alternatives],
        "suggestion_type": suggestion_type,
        "requested_date": target_date.isoformat(),
        "suggested_date": suggested_date.isoformat() if suggested_date else None,
    }


def check_widget_availability(clinic_slug, service_id, preferred_starts_at=None, preferred_date=None):
    clinic = get_clinic_for_slug(clinic_slug)
    if not clinic:
        return {"found": False, "available": False, "alternatives": []}
    disabled = _website_ai_disabled_response_for_clinic(clinic)
    if disabled:
        return {**disabled, "available": False, "alternatives": []}
    return _check_availability_for_clinic(clinic, service_id, preferred_starts_at, preferred_date)


def find_verified_appointment(page_id, reference_code, phone):
    connection = get_connection_for_page(page_id)
    if not connection:
        return {"found": False, "error": APPOINTMENT_LOOKUP_ERROR}
    return _find_verified_appointment_for_clinic(connection.clinic, reference_code, phone)


def find_widget_verified_appointment(clinic_slug, reference_code, phone):
    clinic = get_clinic_for_slug(clinic_slug)
    if not clinic:
        return {"found": False, "error": APPOINTMENT_LOOKUP_ERROR}
    disabled = _website_ai_disabled_response_for_clinic(clinic)
    if disabled:
        return {**disabled, "found": False, "error": "AI is disabled for this clinic."}
    return _find_verified_appointment_for_clinic(clinic, reference_code, phone)


def cancel_verified_appointment(page_id, reference_code, phone, confirmed, reason="", psid="", turn_token="", input_sequence=None):
    connection = get_connection_for_page(page_id)
    if not connection:
        return {"cancelled": False, "error": APPOINTMENT_LOOKUP_ERROR}
    with transaction.atomic():
        stale_error = _validate_messenger_turn_metadata(connection, psid, turn_token, input_sequence, lock=True)
        if stale_error:
            return {"cancelled": False, "error": stale_error}
        return _cancel_verified_appointment_for_clinic(connection.clinic, reference_code, phone, confirmed, reason)


def cancel_widget_verified_appointment(clinic_slug, reference_code, phone, confirmed, reason=""):
    clinic = get_clinic_for_slug(clinic_slug)
    if not clinic:
        return {"cancelled": False, "error": APPOINTMENT_LOOKUP_ERROR}
    disabled = _website_ai_disabled_response_for_clinic(clinic)
    if disabled:
        return {**disabled, "cancelled": False, "error": "AI is disabled for this clinic."}
    return _cancel_verified_appointment_for_clinic(clinic, reference_code, phone, confirmed, reason)


def _cancel_verified_appointment_for_clinic(clinic, reference_code, phone, confirmed, reason=""):
    if confirmed is not True:
        return {"cancelled": False, "error": CONFIRMATION_REQUIRED_ERROR}

    with transaction.atomic():
        locked_clinic = Clinic.objects.select_for_update().get(pk=clinic.pk)
        appointment, error = _verified_appointment_for_clinic(locked_clinic, reference_code, phone)
        if error:
            return {"cancelled": False, "error": error}
        if not appointment.can_transition_to(Appointment.STATUS_CANCELLED):
            return {"cancelled": False, "error": "This appointment cannot be cancelled through the assistant."}
        appointment.status = Appointment.STATUS_CANCELLED
        appointment.cancellation_reason = str(reason or "").strip()[:500]
        appointment.save(update_fields=["status", "cancellation_reason", "updated_at"])
        return {"cancelled": True, "appointment": _appointment_summary(locked_clinic, appointment)}


def reschedule_verified_appointment(page_id, reference_code, phone, starts_at, confirmed, psid="", turn_token="", input_sequence=None):
    connection = get_connection_for_page(page_id)
    if not connection:
        return {"rescheduled": False, "error": APPOINTMENT_LOOKUP_ERROR}
    with transaction.atomic():
        stale_error = _validate_messenger_turn_metadata(connection, psid, turn_token, input_sequence, lock=True)
        if stale_error:
            return {"rescheduled": False, "error": stale_error}
        return _reschedule_verified_appointment_for_clinic(connection.clinic, reference_code, phone, starts_at, confirmed)


def reschedule_widget_verified_appointment(clinic_slug, reference_code, phone, starts_at, confirmed):
    clinic = get_clinic_for_slug(clinic_slug)
    if not clinic:
        return {"rescheduled": False, "error": APPOINTMENT_LOOKUP_ERROR}
    disabled = _website_ai_disabled_response_for_clinic(clinic)
    if disabled:
        return {**disabled, "rescheduled": False, "error": "AI is disabled for this clinic."}
    return _reschedule_verified_appointment_for_clinic(clinic, reference_code, phone, starts_at, confirmed)


def _reschedule_verified_appointment_for_clinic(clinic, reference_code, phone, starts_at, confirmed):
    if confirmed is not True:
        return {"rescheduled": False, "error": CONFIRMATION_REQUIRED_ERROR}

    try:
        new_starts_at = _parse_clinic_datetime(clinic, starts_at)
    except (ValueError, TypeError):
        return {"rescheduled": False, "error": "Invalid date or time."}
    if not new_starts_at:
        return {"rescheduled": False, "error": "Invalid date or time."}
    if new_starts_at <= timezone.now():
        return {"rescheduled": False, "error": PAST_APPOINTMENT_TIME_MESSAGE}

    with transaction.atomic():
        locked_clinic = Clinic.objects.select_for_update().get(pk=clinic.pk)
        appointment, error = _verified_appointment_for_clinic(locked_clinic, reference_code, phone)
        if error:
            return {"rescheduled": False, "error": error}
        duration = appointment.service.effective_duration()
        new_ends_at = new_starts_at + timedelta(minutes=duration)
        try:
            validate_slot(locked_clinic, new_starts_at, new_ends_at, exclude_appointment=appointment)
        except ValidationError as exc:
            return {"rescheduled": False, "error": _validation_error_text(exc)}
        appointment.starts_at = new_starts_at
        appointment.ends_at = new_ends_at
        appointment.save(update_fields=["starts_at", "ends_at", "updated_at"])
        return {"rescheduled": True, "appointment": _appointment_summary(locked_clinic, appointment)}


def book_confirmed_appointment(page_id, service_id, starts_at, full_name, phone, confirmed, email="", reason="", psid="", turn_token="", input_sequence=None):
    connection = get_connection_for_page(page_id)
    if not connection:
        return {"created": False, "error": "Messenger connection not found."}
    with transaction.atomic():
        stale_error = _validate_messenger_turn_metadata(connection, psid, turn_token, input_sequence, lock=True)
        if stale_error:
            return {"created": False, "error": stale_error}
        return _book_confirmed_appointment_for_clinic(
            connection.clinic,
            Appointment.SOURCE_MESSENGER,
            service_id,
            starts_at,
            full_name,
            phone,
            confirmed,
            email,
            reason,
            psid,
        )


def _book_confirmed_appointment_for_clinic(clinic, source, service_id, starts_at, full_name, phone, confirmed, email="", reason="", psid=""):
    if confirmed is not True:
        return {
            "created": False,
            "error": "Appointment creation requires explicit user confirmation.",
        }

    try:
        appointment, error = _process_guest_booking(clinic, {
            "service": service_id,
            "starts_at": starts_at,
            "full_name": full_name,
            "phone": phone,
            "email": email,
            "reason": reason,
        }, source)
    except (Http404, ValueError, TypeError) as exc:
        return {"created": False, "error": str(exc)}

    if error:
        return {"created": False, "error": error}

    if source == Appointment.SOURCE_MESSENGER and psid:
        appointment.messenger_psid = psid
        appointment.save(update_fields=["messenger_psid", "updated_at"])

    return {
        "created": True,
        "appointment": _appointment_summary(clinic, appointment),
    }


def book_widget_confirmed_appointment(clinic_slug, service_id, starts_at, full_name, phone, confirmed, email="", reason=""):
    clinic = get_clinic_for_slug(clinic_slug)
    if not clinic:
        return {"created": False, "error": "Clinic not found."}
    disabled = _website_ai_disabled_response_for_clinic(clinic)
    if disabled:
        return {**disabled, "created": False, "error": "AI is disabled for this clinic."}
    return _book_confirmed_appointment_for_clinic(
        clinic,
        Appointment.SOURCE_CHAT_WIDGET,
        service_id,
        starts_at,
        full_name,
        phone,
        confirmed,
        email,
        reason,
    )
