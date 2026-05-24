from datetime import date, datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.http import Http404
from django.utils import timezone

from appointments.models import Appointment
from scheduling.utils import generate_slots
from widget.views import _process_guest_booking

from .defaults import DEFAULT_MESSENGER_AI_PROMPT
from .models import MessengerConnection


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


def _parse_datetime(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value))
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed.astimezone(dt_timezone.utc)


def _ai_disabled_response(connection):
    ai_settings = getattr(connection, "ai_settings", None)
    if ai_settings and not ai_settings.is_ai_enabled:
        return {
            "found": True,
            "disabled": True,
            "fallback_message": ai_settings.fallback_message,
        }
    return None


def get_connection_for_page(page_id):
    if not page_id:
        return None
    return (
        MessengerConnection.objects.select_related("clinic", "ai_settings")
        .filter(page_id=page_id, is_active=True, clinic__is_active=True)
        .first()
    )


def build_ai_context(page_id):
    connection = get_connection_for_page(page_id)
    if not connection:
        return {"found": False}

    clinic = connection.clinic
    ai_settings = getattr(connection, "ai_settings", None)
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
        "ai": {
            "is_ai_enabled": True if ai_settings is None else ai_settings.is_ai_enabled,
            "instructions": DEFAULT_MESSENGER_AI_PROMPT if ai_settings is None else (ai_settings.instructions or DEFAULT_MESSENGER_AI_PROMPT),
            "fallback_message": "" if ai_settings is None else ai_settings.fallback_message,
        },
        "services": [_service_payload(service) for service in services],
        "faqs": [{"question": faq.question, "answer": faq.answer} for faq in faqs],
    }


def match_services(page_id, query):
    connection = get_connection_for_page(page_id)
    if not connection:
        return {"found": False, "matches": []}
    disabled = _ai_disabled_response(connection)
    if disabled:
        return {**disabled, "matches": []}
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


def _slots_for_date(clinic, service, date_value):
    return [_slot_payload(clinic, slot) for slot in generate_slots(clinic, service, date_value)]


def check_availability(page_id, service_id, preferred_starts_at=None, preferred_date=None):
    connection = get_connection_for_page(page_id)
    if not connection:
        return {"found": False, "available": False, "alternatives": []}
    disabled = _ai_disabled_response(connection)
    if disabled:
        return {**disabled, "available": False, "alternatives": []}

    clinic = connection.clinic
    service = clinic.services.filter(pk=service_id, is_active=True, is_archived=False).first()
    if not service:
        return {"found": True, "available": False, "error": "Service not found.", "alternatives": []}

    try:
        requested_start = _parse_datetime(preferred_starts_at) if preferred_starts_at else None
        if requested_start:
            target_date = requested_start.astimezone(ZoneInfo(clinic.timezone)).date()
        elif preferred_date:
            target_date = date.fromisoformat(str(preferred_date))
        else:
            target_date = timezone.localdate() + timedelta(days=1)
    except (ValueError, TypeError):
        return {"found": True, "available": False, "error": "Invalid date or time.", "alternatives": []}

    raw_slots = generate_slots(clinic, service, target_date)
    selected = None
    if requested_start:
        selected = next((slot for slot in raw_slots if slot["starts_at"] == requested_start), None)
    alternatives = raw_slots
    if requested_start:
        alternatives = sorted(raw_slots, key=lambda slot: abs(slot["starts_at"] - requested_start))
        alternatives = [slot for slot in alternatives if slot["starts_at"] != requested_start]

    search_date = target_date
    while len(alternatives) < 3 and search_date < target_date + timedelta(days=14):
        search_date += timedelta(days=1)
        alternatives.extend(generate_slots(clinic, service, search_date))

    return {
        "found": True,
        "available": selected is not None or (requested_start is None and bool(alternatives)),
        "selected_slot": _slot_payload(clinic, selected) if selected else None,
        "alternatives": [_slot_payload(clinic, slot) for slot in alternatives[:3]],
    }


def book_confirmed_appointment(page_id, service_id, starts_at, full_name, phone, confirmed, email="", reason=""):
    if confirmed is not True:
        return {
            "created": False,
            "error": "Appointment creation requires explicit user confirmation.",
        }

    connection = get_connection_for_page(page_id)
    if not connection:
        return {"created": False, "error": "Messenger connection not found."}
    disabled = _ai_disabled_response(connection)
    if disabled:
        return {**disabled, "created": False, "error": "Messenger AI is disabled for this clinic."}

    try:
        appointment, error = _process_guest_booking(connection.clinic, {
            "service": service_id,
            "starts_at": starts_at,
            "full_name": full_name,
            "phone": phone,
            "email": email,
            "reason": reason,
        }, Appointment.SOURCE_MESSENGER)
    except (Http404, ValueError, TypeError) as exc:
        return {"created": False, "error": str(exc)}

    if error:
        return {"created": False, "error": error}

    local_start = appointment.starts_at.astimezone(ZoneInfo(connection.clinic.timezone))
    return {
        "created": True,
        "appointment": {
            "id": appointment.id,
            "reference_code": appointment.reference_code,
            "service": appointment.service.name,
            "status": appointment.status,
            "starts_at": appointment.starts_at.isoformat(),
            "local_starts_at": local_start.isoformat(),
            "patient_name": appointment.patient.full_name,
            "patient_phone": appointment.patient.phone,
        },
    }
