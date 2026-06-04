import re
from datetime import date, timedelta, datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone

from appointments.models import Appointment
from clinics.models import ClinicFAQ
from scheduling.utils import generate_slots
from widget.views import _process_guest_booking, _find_next_available_date
from .faq_matcher import match_faq
from .models import MessengerSession


MESSENGER_QUICK_REPLY_LIMIT = 13
MESSENGER_QUICK_REPLY_TITLE_LIMIT = 20


def _quick_reply(text, options):
    safe_options = []
    for option in list(options or [])[:MESSENGER_QUICK_REPLY_LIMIT]:
        safe_options.append({
            "title": str(option.get("title", ""))[:MESSENGER_QUICK_REPLY_TITLE_LIMIT],
            "payload": str(option.get("payload", "")),
        })
    return {"type": "quick_replies", "text": text, "options": safe_options}


def _text(text):
    return {"type": "text", "text": text}


def _next_step_options():
    return [
        {"title": "Book an appointment", "payload": "start_booking"},
        {"title": "View FAQs", "payload": "view_faqs"},
        {"title": "Clinic info", "payload": "clinic_info"},
    ]


def _next_step_quick_reply(text="What would you like to do next?"):
    return _quick_reply(text, _next_step_options())


def _reset_with_next_steps(session, actions):
    session.reset()
    actions.append(_next_step_quick_reply())
    return actions


def _service_selection_or_next_steps(session, actions, message="Which service would you like to book?"):
    service_options = _service_options(session.connection.clinic)
    if service_options:
        session.state = MessengerSession.STATE_SELECT_SERVICE
        session.data = {}
        actions.append(_quick_reply(message, service_options))
        session.save()
        return actions
    actions.append(_text("No bookable services are available right now."))
    return _reset_with_next_steps(session, actions)


def _service_options(clinic):
    services = clinic.services.filter(is_active=True, is_archived=False)
    return [{"title": s.name, "payload": str(s.id)} for s in services]


def _reset_to_service_selection(session, actions, message="That service is no longer available. Please choose another:"):
    return _service_selection_or_next_steps(session, actions, message)


def _time_options(slots):
    return [{"title": slot["label"], "payload": slot["starts_at"].isoformat()} for slot in slots]


def _parse_name_phone(text):
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if len(lines) < 2:
        return None, None
    full_name = lines[0]
    phone = lines[1]
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 7:
        return None, None
    return full_name, phone


def _parse_name_phone_email(text):
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if len(lines) < 3:
        return None, None, None
    full_name, phone = _parse_name_phone("\n".join(lines[:2]))
    email = lines[2]
    if not full_name or not phone:
        return None, None, None
    try:
        validate_email(email)
    except ValidationError:
        return None, None, None
    return full_name, phone, email


def _clinic_localdate(clinic):
    return timezone.now().astimezone(ZoneInfo(clinic.timezone)).date()


def handle_message(session, text, postback):
    clinic = session.connection.clinic
    state = session.state
    data = session.data
    actions = []

    lower = (text or "").lower().strip()

    # Global cancel command (outside collect_info)
    if state != MessengerSession.STATE_COLLECT_INFO and lower in ("cancel", "cancel appointment"):
        appt = (
            Appointment.objects.filter(
                clinic=clinic,
                source=Appointment.SOURCE_MESSENGER,
                status__in=[Appointment.STATUS_PENDING, Appointment.STATUS_CONFIRMED],
                starts_at__gte=timezone.now(),
                starts_at__lte=timezone.now() + timedelta(days=7),
                messenger_psid=session.psid,
            )
            .order_by("starts_at")
            .first()
        )
        if appt:
            appt.status = Appointment.STATUS_CANCELLED
            appt.save(update_fields=["status"])
            actions.append(_text(f"Your appointment ({appt.reference_code}) has been cancelled."))
        else:
            actions.append(_text("I couldn't find a pending or confirmed appointment to cancel."))
        session.reset()
        actions.append(_next_step_quick_reply())
        return actions

    if postback and postback.startswith("faq:"):
        try:
            faq_id = int(postback.split(":")[1])
            faq = clinic.faqs.get(pk=faq_id, is_active=True)
            actions.append(_text(f"Q: {faq.question}\nA: {faq.answer}"))
        except (ValueError, ClinicFAQ.DoesNotExist):
            actions.append(_text("Sorry, that FAQ is no longer available."))
        session.state = MessengerSession.STATE_GREETING
        session.save()
        actions.append(_next_step_quick_reply())
        return actions

    if state == MessengerSession.STATE_GREETING:
        if postback == "start_booking" or lower in ("book", "appointment", "schedule", "book an appointment"):
            state = MessengerSession.STATE_SELECT_SERVICE
        elif postback == "view_faqs" or lower in ("faq", "help", "question"):
            faq = match_faq(clinic, text) if text else None
            if faq:
                actions.append(_text(f"Q: {faq.question}\nA: {faq.answer}"))
                actions.append(_next_step_quick_reply())
            else:
                actions.append(_text("Here are some frequently asked questions:"))
                faqs = clinic.faqs.filter(is_active=True)
                if faqs.exists():
                    options = [{"title": f.question[:20], "payload": f"faq:{f.id}"} for f in faqs[:10]]
                    actions.append(_quick_reply("Select a question:", options))
                else:
                    actions.append(_text("No FAQs available right now."))
                    actions.append(_next_step_quick_reply())
            session.state = state
            session.save()
            return actions
        elif postback == "clinic_info" or lower in ("info", "clinic", "address", "location", "contact", "phone"):
            info_parts = [f"*{clinic.name}*"]
            if clinic.address:
                info_parts.append(f"Address: {clinic.address}")
            if clinic.phone:
                info_parts.append(f"Phone: {clinic.phone}")
            if clinic.email:
                info_parts.append(f"Email: {clinic.email}")
            info_parts.append(f"Timezone: {clinic.timezone}")
            actions.append(_text("\n".join(info_parts)))
            session.state = state
            session.save()
            actions.append(_next_step_quick_reply())
            return actions
        else:
            faq = match_faq(clinic, text) if text else None
            if faq:
                actions.append(_text(f"Q: {faq.question}\nA: {faq.answer}"))
                session.state = state
                session.save()
                actions.append(_next_step_quick_reply())
                return actions
            actions.append(_text(clinic.widget_welcome_message or "Welcome! How can we help you today?"))
            actions.append(_quick_reply("Choose an option:", _next_step_options()))
            session.state = state
            session.save()
            return actions

    if state == MessengerSession.STATE_SELECT_SERVICE:
        services = clinic.services.filter(is_active=True, is_archived=False)
        service_id = postback or text
        service = None
        try:
            service = services.filter(pk=int(service_id)).first()
        except (ValueError, TypeError):
            pass
        if service:
            data["service_id"] = service.id
            state = MessengerSession.STATE_SELECT_DATE
        else:
            return _service_selection_or_next_steps(session, actions)

    if state == MessengerSession.STATE_SELECT_DATE:
        selected_date = None
        try:
            selected_date = date.fromisoformat(postback or text)
        except (ValueError, TypeError):
            pass
        if selected_date:
            data["date"] = selected_date.isoformat()
            state = MessengerSession.STATE_SELECT_TIME
            service = clinic.services.filter(pk=data.get("service_id"), is_active=True, is_archived=False).first()
            if not service:
                return _reset_to_service_selection(session, actions)
            slots = generate_slots(clinic, service, selected_date)
            if slots:
                actions.append(_quick_reply("Here are the available times:", _time_options(slots)))
            else:
                next_d = _find_next_available_date(clinic, service, selected_date)
                if next_d:
                    actions.append(_text(f"No slots available. The next available date is {next_d.strftime('%a, %b %d')}."))
                    options = [
                        {"title": (next_d + timedelta(days=i)).strftime("%a, %b %d"), "payload": (next_d + timedelta(days=i)).isoformat()}
                        for i in range(0, 14)
                    ]
                    actions.append(_quick_reply("Choose a date:", options))
                    state = MessengerSession.STATE_SELECT_DATE
                else:
                    actions.append(_text("Sorry, no slots are available in the near future."))
                    return _reset_with_next_steps(session, actions)
            session.state = state
            session.data = data
            session.save()
            return actions
        else:
            options = [
                {"title": (_clinic_localdate(clinic) + timedelta(days=i)).strftime("%a, %b %d"), "payload": (_clinic_localdate(clinic) + timedelta(days=i)).isoformat()}
                for i in range(1, 15)
            ]
            actions.append(_quick_reply("What date works for you?", options))
            session.state = state
            session.data = data
            session.save()
            return actions

    if state == MessengerSession.STATE_SELECT_TIME:
        service_id = data.get("service_id")
        date_str = data.get("date")
        service = clinic.services.filter(pk=service_id, is_active=True, is_archived=False).first()
        if not service:
            return _reset_to_service_selection(session, actions)
        selected_date = date.fromisoformat(date_str)
        slots = generate_slots(clinic, service, selected_date)
        if postback or text:
            starts_at = None
            try:
                starts_at = datetime.fromisoformat(postback or text)
                if timezone.is_naive(starts_at):
                    starts_at = timezone.make_aware(starts_at)
                starts_at = starts_at.astimezone(dt_timezone.utc)
            except (ValueError, TypeError):
                pass
            if starts_at and any(slot["starts_at"] == starts_at for slot in slots):
                data["starts_at"] = starts_at.isoformat()
                state = MessengerSession.STATE_COLLECT_INFO
            else:
                if slots:
                    actions.append(_quick_reply("That slot is no longer available. Please choose another:", _time_options(slots)))
                else:
                    next_d = _find_next_available_date(clinic, service, selected_date)
                    if next_d:
                        actions.append(_text(f"No slots available. The next available date is {next_d.strftime('%a, %b %d')}."))
                        options = [
                            {"title": (next_d + timedelta(days=i)).strftime("%a, %b %d"), "payload": (next_d + timedelta(days=i)).isoformat()}
                            for i in range(0, 14)
                        ]
                        actions.append(_quick_reply("Choose a date:", options))
                        state = MessengerSession.STATE_SELECT_DATE
                    else:
                        actions.append(_text("Sorry, no slots are available in the near future."))
                        return _reset_with_next_steps(session, actions)
                session.state = state
                session.data = data
                session.save()
                return actions
        else:
            if slots:
                actions.append(_quick_reply("Here are the available times:", _time_options(slots)))
            else:
                next_d = _find_next_available_date(clinic, service, selected_date)
                if next_d:
                    actions.append(_text(f"No slots available. The next available date is {next_d.strftime('%a, %b %d')}."))
                    options = [
                        {"title": (next_d + timedelta(days=i)).strftime("%a, %b %d"), "payload": (next_d + timedelta(days=i)).isoformat()}
                        for i in range(0, 14)
                    ]
                    actions.append(_quick_reply("Choose a date:", options))
                    state = MessengerSession.STATE_SELECT_DATE
                else:
                    actions.append(_text("Sorry, no slots are available in the near future."))
                    return _reset_with_next_steps(session, actions)
            session.state = state
            session.data = data
            session.save()
            return actions

    if state == MessengerSession.STATE_COLLECT_INFO:
        full_name, phone, email = _parse_name_phone_email(text or "")
        if full_name and phone and email:
            data["full_name"] = full_name
            data["phone"] = phone
            data["email"] = email
            state = MessengerSession.STATE_CONFIRM
        else:
            actions.append(_text("Please provide your full name, phone number, and email.\n\nExample:\nJohn Doe\n09171234567\njohn@example.com"))
            session.state = state
            session.data = data
            session.save()
            return actions

    if state == MessengerSession.STATE_CONFIRM:
        if postback == "confirm" or lower == "confirm":
            appointment, error = _process_guest_booking(clinic, {
                "service": data.get("service_id"),
                "starts_at": data.get("starts_at"),
                "full_name": data.get("full_name"),
                "phone": data.get("phone"),
                "email": data.get("email", ""),
                "reason": "",
            }, Appointment.SOURCE_MESSENGER)
            if error:
                actions.append(_text(error))
                state = MessengerSession.STATE_SELECT_TIME
                service_id = data.get("service_id")
                date_str = data.get("date")
                service = clinic.services.filter(pk=service_id, is_active=True, is_archived=False).first()
                if not service:
                    return _reset_to_service_selection(session, actions)
                selected_date = date.fromisoformat(date_str)
                slots = generate_slots(clinic, service, selected_date)
                if slots:
                    actions.append(_quick_reply("Please choose another time:", _time_options(slots)))
                else:
                    return _reset_with_next_steps(session, actions)
                session.state = state
                session.data = data
                session.save()
                return actions
            appointment.messenger_psid = session.psid
            appointment.save(update_fields=["messenger_psid", "updated_at"])
            local_start = appointment.starts_at.astimezone(ZoneInfo(clinic.timezone))
            actions.append(_text(
                f"Your appointment is confirmed!\n"
                f"Service: {appointment.service.name}\n"
                f"Date: {local_start.strftime('%A, %B %d at %I:%M %p')}\n"
                f"Reference: {appointment.reference_code}\n\n"
                f"Reply CANCEL to cancel this appointment."
            ))
            return _reset_with_next_steps(session, actions)
        elif postback == "cancel" or lower == "cancel":
            session.reset()
            actions.append(_text("Booking cancelled."))
            actions.append(_next_step_quick_reply())
            session.save()
            return actions
        else:
            service = clinic.services.filter(pk=data.get("service_id")).first()
            if not service:
                session.state = state
                session.data = data
                session.save()
                return actions
            starts_at = datetime.fromisoformat(data.get("starts_at"))
            local_start = starts_at.astimezone(ZoneInfo(clinic.timezone))
            summary = f"{service.name} at {clinic.name} on {local_start.strftime('%A, %B %d at %I:%M %p')}"
            actions.append(_text(f"Please confirm your appointment:\n{summary}\nPatient: {data.get('full_name')}"))
            actions.append(_quick_reply("Choose an option:", [
                {"title": "Confirm", "payload": "confirm"},
                {"title": "Cancel", "payload": "cancel"},
            ]))
            session.state = state
            session.data = data
            session.save()
            return actions

    if state == MessengerSession.STATE_BOOKED:
        if postback in ("restart", "start_booking") or lower in ("book", "another", "book another"):
            return _service_selection_or_next_steps(session, actions)
        actions.append(_text("Thanks for using our booking service!"))
        return _reset_with_next_steps(session, actions)

    # Fallback
    session.reset()
    actions.append(_text("I didn't understand that. Let's start over."))
    actions.append(_quick_reply("Choose an option:", _next_step_options()))
    session.save()
    return actions
