import json
import logging
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from clinics.models import ClinicAIProviderSettings, ClinicAISettings
from patients.models import normalize_phone

from .ai_provider_client import AIProviderError, call_chat_completion
from .ai_tools import (
    book_confirmed_appointment,
    book_voice_widget_confirmed_appointment,
    book_widget_confirmed_appointment,
    build_ai_context,
    build_widget_ai_context,
    cancel_verified_appointment,
    cancel_widget_verified_appointment,
    check_availability,
    check_widget_availability,
    find_verified_appointment,
    find_widget_verified_appointment,
    get_clinic_for_slug,
    get_connection_for_page,
    get_or_create_clinic_ai_settings,
    match_services,
    match_widget_services,
    reschedule_verified_appointment,
    reschedule_widget_verified_appointment,
)
from .defaults import DEFAULT_AI_FALLBACK_MESSAGE, DEFAULT_MESSENGER_AI_PROMPT
from .models import MessengerConversation


logger = logging.getLogger(__name__)

MAX_GATEWAY_MESSAGE_CHARS = 1800
MAX_GATEWAY_TOOL_CALLS_PER_RESPONSE = 4
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)")
MUTATING_TOOL_NAMES = {"book_confirmed_appointment", "cancel_verified_appointment", "reschedule_verified_appointment"}
GATEWAY_TOOL_NAMES = {
    "match_services",
    "check_availability",
    "book_confirmed_appointment",
    "find_verified_appointment",
    "cancel_verified_appointment",
    "reschedule_verified_appointment",
}
SECRET_CONTEXT_KEYS = {
    "api_key",
    "access_token",
    "app_secret",
    "page_token",
    "page_access_token",
    "token",
    "secret",
    "webhook_secret",
    "authorization",
    "password",
    "credential",
}
CURRENT_BOOKING_SAFETY_RULES = """Current KliniAssist booking safety rules:
- Collect service, local date/time, full name, phone, and email before asking for final booking confirmation.
- If the patient gives a date/time but no service, ask for the service only before asking for patient details.
- Do not infer a patient's full name from booking, service, date, or time messages.
- Do not say the patient mentioned something earlier unless that exact detail is present in conversation history or known patient details.
- Do not describe email as optional for bookings.
- Before booking, summarize service, local date/time, full name, phone, and email, then ask for explicit confirmation.
- Do not call book_confirmed_appointment in the same turn where the patient first provides or changes a required booking detail.
- If the requested service is not an active clinic service, say it is unavailable; do not substitute a different service unless the patient explicitly accepts it.
- If the patient uses a weekday such as this Saturday, keep the weekday and calendar date consistent with the clinic timezone."""
YAKAP_AI_SAFETY_RULES = """YAKAP safety rules:
- If the patient wants to request YAKAP, direct them to the booking form so the service-gated YAKAP checkbox can be validated server-side.
- Do not promise YAKAP eligibility, free care, official PhilHealth approval, or official remaining balance.
- Do not invent or quote YAKAP covered amounts from the public AI context."""
CORE_AI_SAFETY_RULES = """Core KliniAssist assistant safety rules:
- Only answer using the clinic context JSON, active services, FAQs, current clinic date/time, and tool results.
- Do not assign a doctor or provider unless the clinic context explicitly names one for that service or FAQ.
- If doctor/provider information is missing, say you do not have that information and offer clinic contact details if available.
- Before saying any date/time is available, unavailable, fully booked, open, or closed, call check_availability in the current turn and base the claim only on its result."""
BLOCKED_AVAILABILITY_TOOL_MESSAGE = (
    "check_availability can only be used when the current patient message asks about "
    "booking availability, dates, times, or chooses a specific slot. Answer the current "
    "patient message from clinic context instead of repeating previous slots."
)
BLOCKED_AVAILABILITY_SAFE_REPLY = (
    "I got your message.\n\n"
    "To continue booking your appointment, please reply YES to confirm the details, "
    "or send the service/date/time you want to change."
)
BLOCKED_EXACT_SLOT_TOOL_MESSAGE = (
    "exact_slot_tool_blocked: check_availability with preferred_starts_at requires the "
    "current patient message to include a specific time or clearly select a listed option. "
    "Ask a clarifying question instead of repeating the previous slot."
)
WEEKDAY_NAMES = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
OUT_OF_SCOPE_SYSTEM_PATTERNS = [
    r"\bsystem integrations?\b",
    r"\bintegrat(?:e|ing|ion|ions)\b.{0,40}\b(?:system|software|platform|api|workflow|webhook)\b",
    r"\b(?:system|software|platform|api|workflow|webhook)\b.{0,40}\bintegrat(?:e|ing|ion|ions)\b",
    r"\btechnical implementation\b",
    r"\bimplement(?:ation|ing)?\b.{0,40}\b(?:system|software|platform|feature|integration)\b",
    r"\b(?:system|software|platform|feature|integration)\b.{0,40}\bimplement(?:ation|ing)?\b",
    r"\bsoftware architecture\b",
    r"\btechnical setup\b",
    r"\binternal features?\b",
    r"\bsystem architecture\b",
    r"\bwhat\s+software\b.{0,80}\b(?:booking|widget|system|platform)\b",
    r"\bsource code\b",
    r"\bcodebase\b",
    r"\bdatabase schema\b",
    r"\bn8n workflow\b",
]


def _is_out_of_scope_system_question(message):
    text = str(message or "").strip().lower()
    if not text:
        return False
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in OUT_OF_SCOPE_SYSTEM_PATTERNS)


def _scoped_out_of_scope_reply(clinic):
    clinic_name = clinic.name if clinic else "the clinic"
    return (
        f"I can help with {clinic_name} services, FAQs, and appointments. "
        "I don't have information about system integrations or technical implementation."
    )


def _fallback_for_clinic(clinic, error):
    if clinic:
        ai_settings = get_or_create_clinic_ai_settings(clinic)
        message = ai_settings.fallback_message or DEFAULT_AI_FALLBACK_MESSAGE
    else:
        message = DEFAULT_AI_FALLBACK_MESSAGE
    return {"reply": message, "fallback": True, "error": error}


def _resolve_gateway_clinic(data):
    channel = str(data.get("channel", "")).strip().lower()
    if channel == "messenger":
        connection = get_connection_for_page(data.get("page_id", ""))
        return connection.clinic if connection else None
    if channel in {"widget", "voice"}:
        return get_clinic_for_slug(data.get("clinic_slug", ""))
    return None


def _context_for_gateway(channel, data):
    if channel == "messenger":
        return build_ai_context(data.get("page_id", ""))
    if channel == "widget":
        return build_widget_ai_context(data.get("clinic_slug", ""))
    if channel == "voice":
        context = build_widget_ai_context(data.get("clinic_slug", ""))
        if context.get("found"):
            context["channel"] = "voice"
        return context
    return {"found": False}


def _safe_context_for_prompt(value):
    if isinstance(value, dict):
        safe = {}
        for key, item in value.items():
            key_text = str(key).lower()
            normalized_key = key_text.replace("-", "_")
            if (
                normalized_key in SECRET_CONTEXT_KEYS
                or normalized_key == "instructions"
                or "token" in normalized_key
                or "secret" in normalized_key
                or "api_key" in normalized_key
                or "apikey" in normalized_key
                or "password" in normalized_key
                or "credential" in normalized_key
            ):
                continue
            safe[key] = _safe_context_for_prompt(item)
        return safe
    if isinstance(value, list):
        return [_safe_context_for_prompt(item) for item in value]
    return value


def _current_turn_texts(data):
    channel = str(data.get("channel", "")).strip().lower()
    if channel == "messenger":
        return _messenger_new_turn_texts(data.get("message", ""))
    text = str(data.get("message", "")).strip()
    return [text] if text else []


def _text_has_contact_detail(text):
    value = str(text or "")
    return bool(
        EMAIL_RE.search(value)
        or PHONE_RE.search(value)
        or re.search(r"\b(?:my name|full name|phone|email)\b", value, flags=re.IGNORECASE)
    )


SPECIFIC_TIME_RE = re.compile(r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b|\b(?:[01]?\d|2[0-3]):[0-5]\d\b", re.IGNORECASE)


def _text_mentions_specific_time(text):
    return bool(SPECIFIC_TIME_RE.search(str(text or "")))


def _current_turn_mentions_specific_time(data):
    return any(_text_mentions_specific_time(text) for text in _current_turn_texts(data))


def _latest_current_turn_time_text(data):
    for text in reversed(_current_turn_texts(data)):
        if _text_mentions_specific_time(text):
            return str(text or "").lower()
    return ""


def _current_turn_selects_listed_option(data):
    text = "\n".join(_current_turn_texts(data)).lower()
    if not text:
        return False
    if re.fullmatch(r"\s*[1-9]\s*", text):
        return True
    return bool(re.search(
        r"\b(?:that one|this one|the first|first one|1st|the second|second one|2nd|the third|third one|3rd|"
        r"earliest|latest|option\s+[1-9]|number\s+[1-9]|slot\s+[1-9])\b",
        text,
    ))


def _local_start_from_availability_args(channel, data, args):
    clinic = _clinic_for_tool(channel, data)
    if not clinic or not isinstance(args, dict) or not args.get("preferred_starts_at"):
        return None
    try:
        parsed = datetime.fromisoformat(str(args.get("preferred_starts_at")).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    clinic_tz = ZoneInfo(clinic.timezone)
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, clinic_tz)
    return parsed.astimezone(clinic_tz)


def _current_turn_mentions_tool_time(channel, data, args):
    local_start = _local_start_from_availability_args(channel, data, args)
    if not local_start:
        return _current_turn_mentions_specific_time(data)
    text = _latest_current_turn_time_text(data)
    if not text:
        return False
    return any(marker in text for marker in _time_markers_for_summary(local_start))


def _current_turn_mentions_past_date(data):
    text = "\n".join(_current_turn_texts(data)).lower()
    return bool(re.search(r"\b(?:yesterday|past|previous|last\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|week|month|year))\b", text))


def _availability_tool_args_are_explicit_past_request(channel, data, args):
    local_start = _local_start_from_availability_args(channel, data, args)
    if not local_start:
        return False
    return local_start < timezone.now().astimezone(local_start.tzinfo) and _current_turn_mentions_past_date(data)


def _availability_tool_args_match_current_turn(channel, data, args):
    if not isinstance(args, dict):
        return _blocked_exact_slot_tool_result()
    if args.get("preferred_starts_at") and not (
        _current_turn_mentions_tool_time(channel, data, args) or _current_turn_selects_listed_option(data)
        or _availability_tool_args_are_explicit_past_request(channel, data, args)
    ):
        return _blocked_exact_slot_tool_result()
    return None


def _text_confirms_booking(text):
    return bool(
        re.search(
            r"\b(?:yes|confirm|confirmed|go ahead|book it|please book|finalize|proceed|oo|opo|sige|tuloy(?:\s+na)?|ituloy|go\s+na)\b",
            str(text or ""),
            flags=re.IGNORECASE,
        )
    )


def _confirmed_in_current_turn(data):
    texts = _current_turn_texts(data)
    if not texts:
        return False
    if any(_text_has_contact_detail(text) for text in texts):
        return False
    return any(_text_confirms_booking(text) for text in texts)


def _messenger_new_turn_texts(value):
    text = str(value or "").strip()
    if not text:
        return []
    marker = "New Messenger messages in order:"
    if marker in text:
        text = text.split(marker, 1)[1]
        text = text.split("Treat the new messages", 1)[0]
    lines = [line.strip() for line in text.splitlines()]
    bullet_texts = [line[2:].strip() for line in lines if line.startswith("- ") and line[2:].strip()]
    return bullet_texts or [text]


def _clinic_for_tool(channel, data):
    if channel == "messenger":
        connection = get_connection_for_page(data.get("page_id", ""))
        return connection.clinic if connection else None
    if channel == "widget":
        return get_clinic_for_slug(data.get("clinic_slug", ""))
    if channel == "voice":
        return get_clinic_for_slug(data.get("clinic_slug", ""))
    return None


def _mentioned_weekday(texts):
    text = "\n".join(str(text or "") for text in texts).lower()
    for name, weekday in WEEKDAY_NAMES.items():
        if re.search(rf"\b(?:this\s+|next\s+)?{name}\b", text):
            return name.capitalize(), weekday
    return "", None


def _current_turn_allows_availability_tool(data):
    texts = [text.strip() for text in _current_turn_texts(data) if str(text or "").strip()]
    if not texts:
        return False
    text = "\n".join(texts)
    lower = text.lower()

    greeting_pattern = r"(?:hi|hello|hey|good\s+(?:morning|afternoon|evening)|kumusta|kamusta|thanks|thank you)[!.\s]*"
    if all(re.fullmatch(greeting_pattern, item, flags=re.IGNORECASE) for item in texts):
        return False
    provider_terms = r"(?:doctors?|providers?|dentists?|physicians?)"
    if re.search(rf"\b(?:who(?:'s|\s+is)?|which|what)\b.{{0,50}}\b{provider_terms}\b", lower):
        return False
    if re.search(rf"\b{provider_terms}\b.{{0,50}}\b(?:available|availability|working|on\s+duty)\b", lower):
        return False
    if re.search(rf"\b(?:available|availability|working|on\s+duty)\b.{{0,50}}\b{provider_terms}\b", lower):
        return False
    appointment_availability_cue = re.search(
        r"\b(?:available|availability|unavailable|fully\s+booked|slots?)\b",
        lower,
    )
    time_word_cue = re.search(r"\btimes?\b", lower)
    clinic_info_question = re.search(
        r"\b(?:location|located|address|directions?|contact|phone|email|hours?)\b|"
        r"\bwhere\s+(?:are\s+you|is\s+(?:the\s+)?clinic)\b|"
        r"\b(?:are\s+you|is\s+(?:the\s+)?clinic)\s+(?:open|closed)\b|"
        r"\bwhat\s+time\s+(?:are\s+you|is\s+(?:the\s+)?clinic)\s+open\b",
        lower,
    )
    if clinic_info_question and not appointment_availability_cue:
        return False

    booking_cue = re.search(r"\b(?:appointment|book|booking|schedule|reschedule)\b", lower)
    date_or_time_value = re.search(
        r"\b(?:today|tomorrow|this\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
        r"next\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
        r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b|"
        r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b|"
        r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
        r"aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}(?:,\s*\d{4})?\b|"
        r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b|\b(?:[01]?\d|2[0-3]):[0-5]\d\b",
        lower,
    )
    return bool(
        appointment_availability_cue
        or time_word_cue
        or booking_cue
        or date_or_time_value
        or _current_turn_selects_listed_option(data)
    )


def _blocked_availability_tool_result():
    return {
        "found": False,
        "availability_tool_blocked": True,
        "message": BLOCKED_AVAILABILITY_TOOL_MESSAGE,
    }


def _blocked_exact_slot_tool_result():
    return {
        "found": False,
        "available": False,
        "exact_slot_tool_blocked": True,
        "message": BLOCKED_EXACT_SLOT_TOOL_MESSAGE,
    }


def _target_date_from_tool_args(clinic, args):
    try:
        if args.get("preferred_starts_at") or args.get("starts_at"):
            value = str(args.get("preferred_starts_at") or args.get("starts_at")).replace("Z", "+00:00")
            parsed = datetime.fromisoformat(value)
            if timezone.is_naive(parsed):
                parsed = timezone.make_aware(parsed, ZoneInfo(clinic.timezone))
            return parsed.astimezone(ZoneInfo(clinic.timezone)).date()
        if args.get("preferred_date"):
            return date.fromisoformat(str(args.get("preferred_date")))
    except (TypeError, ValueError):
        return None
    return None


def _next_weekday_date(clinic, weekday):
    today = timezone.now().astimezone(ZoneInfo(clinic.timezone)).date()
    days = (weekday - today.weekday()) % 7
    if days == 0:
        days = 7
    return today + timedelta(days=days)


def _weekday_mismatch_result(channel, data, args, *, mutation=False):
    clinic = _clinic_for_tool(channel, data)
    if clinic is None:
        return None
    weekday_name, weekday = _mentioned_weekday(_current_turn_texts(data))
    if weekday is None:
        return None
    target_date = _target_date_from_tool_args(clinic, args)
    if target_date is None or target_date.weekday() == weekday:
        return None
    expected_date = _next_weekday_date(clinic, weekday)
    message = (
        "Requested weekday does not match the date sent to availability. "
        f"The patient asked for {weekday_name}; use {expected_date.isoformat()} "
        f"for this {weekday_name} in the clinic timezone."
    )
    if mutation:
        return {"created": False, "error": message}
    return {
        "found": True,
        "available": False,
        "error": message,
        "selected_slot": None,
        "alternatives": [],
        "suggestion_type": "weekday_mismatch",
        "requested_date": target_date.isoformat(),
        "suggested_date": expected_date.isoformat(),
    }


def _extract_name_from_contact_text(text, phone_text=""):
    candidate = EMAIL_RE.sub(" ", str(text or ""))
    if phone_text:
        candidate = candidate.replace(phone_text, " ")
    candidate = PHONE_RE.sub(" ", candidate)
    candidate = re.sub(
        r"\b(?:yes|confirm|please|thanks|thank you|book|booking|appointment|for|my|name|full name|phone|number|email|is|ako si)\b",
        " ",
        candidate,
        flags=re.IGNORECASE,
    )
    candidate = re.sub(r"[^A-Za-z' -]", " ", candidate)
    candidate = re.sub(r"\s+", " ", candidate).strip(" -")
    if len(candidate) < 2 or not re.search(r"[A-Za-z]", candidate):
        return ""
    return candidate[:160]


def _text_has_booking_or_date_cue(text):
    value = str(text or "").lower()
    return bool(re.search(
        r"\b(?:book|booking|appointment|schedule|service|slot|available|availability|interested|looking|lunch|today|tomorrow|"
        r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
        r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
        r"aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b|"
        r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b|\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b",
        value,
    ))


def _trim_explicit_name_candidate(candidate):
    value = str(candidate or "").strip()
    value = re.split(
        r"\b(?:and\s+i\b|and\s+my\b|phone\b|email\b|book\b|booking\b|appointment\b|schedule\b|service\b|for\b)\b",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return value.strip(" ,.-")


def _candidate_looks_like_non_name(candidate):
    value = str(candidate or "").strip().lower()
    return bool(re.search(
        r"\b(?:i|i'm|am|new|here|available|availability|interested|looking|want|wants|need|needs)\b",
        value,
    ))


def _extract_explicit_name_from_text(text, phone_text=""):
    value = str(text or "")
    patterns = [
        r"\bmy\s+(?:full\s+)?name\s+is\s+([A-Za-z][A-Za-z' -]{1,160})",
        r"\bfull\s+name\s*[:\-]?\s*([A-Za-z][A-Za-z' -]{1,160})",
        r"\bako\s+si\s+([A-Za-z][A-Za-z' -]{1,160})",
    ]
    for pattern in patterns:
        match = re.search(pattern, value, flags=re.IGNORECASE)
        if not match:
            continue
        candidate = _trim_explicit_name_candidate(match.group(1))
        if _text_has_booking_or_date_cue(candidate):
            return ""
        return _extract_name_from_contact_text(candidate, phone_text)
    return ""


def _extract_booking_name_before_contact(text, phone_text=""):
    value = str(text or "")
    contact_starts = []
    email_match = EMAIL_RE.search(value)
    if email_match:
        contact_starts.append(email_match.start())
    phone_matches = list(PHONE_RE.finditer(value))
    if phone_matches:
        contact_starts.append(phone_matches[0].start())
    if not contact_starts:
        return ""
    prefix = value[:min(contact_starts)]
    time_matches = list(SPECIFIC_TIME_RE.finditer(prefix))
    if not time_matches:
        return ""
    candidate = prefix[time_matches[-1].end():].strip(" ,:;.-")
    if not candidate or _text_has_booking_or_date_cue(candidate):
        return ""
    return _extract_name_from_contact_text(candidate, phone_text)


def _extract_contact_details(text):
    details = {}
    email_match = EMAIL_RE.search(str(text or ""))
    if email_match:
        details["email"] = email_match.group(0).strip()[:254]
    phone_matches = list(PHONE_RE.finditer(str(text or "")))
    phone_text = ""
    if phone_matches:
        phone_text = phone_matches[-1].group(0).strip()
        phone = normalize_phone(phone_text)
        if len(phone) >= 9:
            details["phone"] = phone[:40]
    explicit_name = _extract_explicit_name_from_text(text, phone_text)
    if explicit_name:
        name = explicit_name
    elif (details.get("phone") or details.get("email")) and _text_has_booking_or_date_cue(text):
        name = _extract_booking_name_before_contact(text, phone_text)
    elif (details.get("phone") or details.get("email")) and not _text_has_booking_or_date_cue(text):
        name = _extract_name_from_contact_text(text, phone_text)
        if _candidate_looks_like_non_name(name):
            name = ""
    else:
        name = ""
    if name:
        details["full_name"] = name
    return details


def _payload_history_user_texts(data):
    history = data.get("history", []) if isinstance(data, dict) else []
    if not isinstance(history, list):
        return []
    return [
        str(entry.get("content", ""))
        for entry in history[-16:]
        if isinstance(entry, dict) and str(entry.get("role", "")).strip().lower() == "user"
    ]


def _messenger_history_texts_from_db(data):
    page_id = str(data.get("page_id", "")).strip()
    psid = str(data.get("psid", "")).strip()
    if not page_id or not psid:
        return []
    conversation = (
        MessengerConversation.objects.filter(
            connection__page_id=page_id,
            connection__page_access_token__gt="",
            connection__is_active=True,
            connection__clinic__is_active=True,
            connection__clinic__requires_onboarding=False,
            psid=psid,
        )
        .only("history")
        .first()
    )
    if not conversation or not isinstance(conversation.history, list):
        return []
    return [
        str(entry.get("content", ""))
        for entry in conversation.history[-16:]
        if isinstance(entry, dict) and str(entry.get("role", "")).strip().lower() == "user"
    ]


def _user_texts_for_booking_details(data):
    texts = [*_payload_history_user_texts(data)]
    if str(data.get("channel", "")).strip().lower() == "messenger":
        texts.extend(_messenger_history_texts_from_db(data))
    texts.extend(_current_turn_texts(data))
    return texts


def _known_booking_details(data):
    details = {}
    for text in _user_texts_for_booking_details(data):
        extracted = _extract_contact_details(text)
        for key in ("full_name", "phone", "email"):
            if extracted.get(key):
                details[key] = extracted[key]
    return details


def _known_patient_details_prompt(data):
    channel = str(data.get("channel", "")).strip().lower()
    if channel != "messenger":
        return ""
    details = _known_booking_details(data)
    if not details:
        return ""

    lines = [
        "Known patient booking details from this Messenger conversation:",
        "Use these as already provided; do not ask for a known field again unless the patient changes it.",
    ]
    for key in ("full_name", "phone", "email"):
        if details.get(key):
            lines.append(f"- {key}: {details[key]}")
    return "\n".join(lines)


def _latest_assistant_history_text(data):
    history = data.get("history", [])
    if not isinstance(history, list):
        return ""
    for entry in reversed(history):
        if not isinstance(entry, dict):
            continue
        if str(entry.get("role", "")).strip().lower() == "assistant":
            return str(entry.get("content", "")).strip()
    return ""


def _text_has_complete_booking_summary_terms(text):
    value = str(text or "").strip()
    if not value:
        return False
    lower = value.lower()
    if "confirm" not in lower:
        return False
    has_service = "service" in lower
    has_datetime = ("date" in lower and "time" in lower) or "date/time" in lower
    has_name = any(term in lower for term in ["full name", "name", "patient"])
    has_phone = any(term in lower for term in ["phone", "mobile", "contact number"])
    has_email = "email" in lower or "e-mail" in lower
    if not all([has_service, has_datetime, has_name, has_phone, has_email]):
        return False
    return True


def _local_start_from_booking_args(clinic, args):
    if not clinic or not isinstance(args, dict) or not args.get("starts_at"):
        return None
    try:
        parsed = datetime.fromisoformat(str(args.get("starts_at")).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    clinic_tz = ZoneInfo(clinic.timezone)
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, clinic_tz)
    return parsed.astimezone(clinic_tz)


def _date_markers_for_summary(clinic, local_start):
    clinic_today = timezone.now().astimezone(ZoneInfo(clinic.timezone)).date()
    target_date = local_start.date()
    month = local_start.strftime("%B")
    short_month = local_start.strftime("%b")
    day = str(local_start.day)
    year = str(local_start.year)
    markers = {
        target_date.isoformat(),
        f"{month} {day}",
        f"{month} {day}, {year}",
        f"{short_month} {day}",
        f"{short_month} {day}, {year}",
    }
    if target_date == clinic_today:
        markers.add("today")
    if target_date == clinic_today + timedelta(days=1):
        markers.add("tomorrow")
    return {marker.lower() for marker in markers}


def _time_markers_for_summary(local_start):
    hour_12 = local_start.strftime("%I:%M %p").lstrip("0")
    hour_24 = local_start.strftime("%H:%M")
    markers = {hour_12, hour_12.replace(" ", ""), hour_24}
    if local_start.minute == 0:
        hour_only = local_start.strftime("%I %p").lstrip("0")
        markers.add(hour_only)
        markers.add(hour_only.replace(" ", ""))
    return {marker.lower() for marker in markers}


def _booking_summary_tool_mismatch_error(text, args=None, clinic=None):
    if not clinic or not isinstance(args, dict):
        return ""
    lower = str(text or "").lower()
    service_name = ""
    try:
        service_id = int(args.get("service_id"))
    except (TypeError, ValueError):
        service_id = 0
    if service_id:
        service_name = (
            clinic.services.filter(id=service_id, is_active=True, is_archived=False)
            .values_list("name", flat=True)
            .first()
            or ""
        )
    if service_name and service_name.lower() not in lower:
        return "Appointment creation rejected because the tool service does not match the preceding booking summary."

    local_start = _local_start_from_booking_args(clinic, args)
    if local_start:
        if not any(marker in lower for marker in _date_markers_for_summary(clinic, local_start)):
            return "Appointment creation rejected because the tool date does not match the preceding booking summary."
        if not any(marker in lower for marker in _time_markers_for_summary(local_start)):
            return "Appointment creation rejected because the tool time does not match the preceding booking summary."
    return ""


def _text_has_complete_booking_summary(text, args=None, clinic=None):
    if not _text_has_complete_booking_summary_terms(text):
        return False

    value = str(text or "").strip()
    lower = value.lower()

    args = args or {}
    email = str(args.get("email") or "").strip().lower()
    if email and email not in lower:
        return False

    phone = re.sub(r"\D", "", str(args.get("phone") or ""))
    text_digits = re.sub(r"\D", "", value)
    if phone and phone[-7:] not in text_digits:
        return False

    full_name = str(args.get("full_name") or "").strip().lower()
    if full_name:
        name_parts = [part for part in re.split(r"\s+", full_name) if part]
        if name_parts and not all(part in lower for part in (name_parts[:1] + name_parts[-1:])):
            return False

    return not _booking_summary_tool_mismatch_error(value, args, clinic)


def _latest_assistant_has_complete_booking_summary(data, args=None, clinic=None):
    return _text_has_complete_booking_summary(_latest_assistant_history_text(data), args, clinic)


def _current_confirmation_followup_prompt(data):
    if not _confirmed_in_current_turn(data):
        return ""
    previous_assistant = _latest_assistant_history_text(data).lower()
    if "confirm" not in previous_assistant:
        return ""
    if "cancel" in previous_assistant or "cancellation" in previous_assistant:
        return "\n".join([
            "current patient message explicitly confirms the immediately preceding cancellation request.",
            "call cancel_verified_appointment with confirmed=true using the verified appointment details from the conversation.",
            "Do not repeat the same cancellation confirmation prompt.",
        ])
    if "reschedule" in previous_assistant and "confirm" in previous_assistant:
        return "\n".join([
            "current patient message explicitly confirms the immediately preceding reschedule request.",
            "call reschedule_verified_appointment with confirmed=true using the verified appointment details and selected new time from the conversation.",
            "Do not repeat the same reschedule confirmation prompt.",
        ])
    if ("booking" in previous_assistant or "appointment" in previous_assistant) and _latest_assistant_has_complete_booking_summary(data):
        return "\n".join([
            "current patient message explicitly confirms the immediately preceding booking request.",
            "call book_confirmed_appointment with confirmed=true using the service_id, selected appointment time, full_name, phone, and email from the immediately preceding booking summary and conversation.",
            "Do not repeat the same booking confirmation prompt.",
        ])
    return ""


def _slot_summary(slot):
    if not isinstance(slot, dict):
        return ""
    return str(slot.get("label") or slot.get("local_starts_at") or slot.get("starts_at") or "available time")


def _detail_card(title, rows, footer=""):
    lines = [title, ""]
    lines.extend(f"{label}: {value}" for label, value in rows if str(value or "").strip())
    if footer:
        lines.extend(["", footer])
    return "\n".join(lines)


def _services_list_card(names):
    lines = ["SERVICES AVAILABLE", "", "Please choose one service:", ""]
    lines.extend(f"{index}. {name}" for index, name in enumerate(names[:10], start=1))
    lines.extend(["", "Reply with the service name or number to continue booking."])
    return "\n".join(lines)


def _service_name_from_tool_args(clinic, args):
    if not clinic or not isinstance(args, dict):
        return ""
    try:
        service_id = int(args.get("service_id"))
    except (TypeError, ValueError):
        return ""
    return (
        clinic.services.filter(id=service_id, is_active=True, is_archived=False)
        .values_list("name", flat=True)
        .first()
        or ""
    )


def _format_local_date_time(value, fallback_date="", fallback_time=""):
    try:
        local_start = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return f"{fallback_date} {fallback_time}".strip()
    time_label = fallback_time or local_start.strftime("%I:%M %p").lstrip("0")
    return f"{local_start.strftime('%A, %B')} {local_start.day}, {local_start.year} at {time_label}"


def _slot_date_time_summary(slot):
    label = _slot_summary(slot)
    if not isinstance(slot, dict):
        return label
    return _format_local_date_time(slot.get("local_starts_at"), fallback_time=label) or label


def _appointment_date_time_summary(appointment):
    if not isinstance(appointment, dict):
        return ""
    return _format_local_date_time(
        appointment.get("local_starts_at"),
        fallback_date=appointment.get("local_date_label", ""),
        fallback_time=appointment.get("local_time_label", ""),
    )


def _spoken_booked_reply(appointment):
    service = appointment.get("service", "appointment")
    date_label = appointment.get("local_date_label", "")
    time_label = appointment.get("local_time_label", "")
    reference = appointment.get("reference_code", "")
    reply = f"Your {service} is booked"
    if date_label or time_label:
        reply += f" for {date_label} {time_label}".rstrip()
    if reference:
        reply += f". Reference code: {reference}"
    return reply + "."


def _display_patient_name(value):
    text = str(value or "").strip()
    return text.title() if text and text.islower() else text


def _selected_slot_booking_reply(selected, clinic=None, data=None, args=None):
    service_name = _service_name_from_tool_args(clinic, args)
    date_time = _slot_date_time_summary(selected)
    details = _known_booking_details(data or {})
    full_name = _display_patient_name(details.get("full_name", ""))
    phone = details.get("phone", "")
    email = details.get("email", "")
    missing = []
    if not service_name:
        missing.append("service")
    if not date_time:
        missing.append("date/time")
    if not full_name:
        missing.append("full name")
    if not phone:
        missing.append("phone")
    if not email:
        missing.append("email")
    if missing:
        return _detail_card(
            "AVAILABLE SLOT",
            [("Time", _slot_summary(selected)), ("Missing", ", ".join(missing))],
            "Please send the missing details so I can summarize before booking.",
        )
    return _detail_card(
        "BOOKING CONFIRMATION",
        [
            ("Service", service_name),
            ("Date/time", date_time),
            ("Patient", full_name),
            ("Phone", phone),
            ("Email", email),
        ],
        "Reply YES to book this appointment.",
    )


def _reply_from_tool_result(result, *, clinic=None, data=None, args=None):
    if not isinstance(result, dict):
        return ""
    error = str(result.get("error") or "").strip()
    if error:
        return error
    if result.get("availability_tool_blocked") is True:
        return BLOCKED_AVAILABILITY_SAFE_REPLY
    if result.get("created") is True and isinstance(result.get("appointment"), dict):
        appointment = result["appointment"]
        if str((data or {}).get("channel", "")).strip().lower() == "voice":
            return _spoken_booked_reply(appointment)
        service = appointment.get("service", "appointment")
        date_time = _appointment_date_time_summary(appointment)
        reference = appointment.get("reference_code", "")
        return _detail_card(
            "APPOINTMENT BOOKED",
            [("Service", service), ("Date/time", date_time), ("Reference code", reference)],
        )
    if result.get("cancelled") is True and isinstance(result.get("appointment"), dict):
        appointment = result["appointment"]
        service = appointment.get("service", "appointment")
        reference = appointment.get("reference_code", "")
        reply = f"Your {service} appointment has been cancelled"
        if reference:
            reply += f". Reference code: {reference}"
        return reply + "."
    if result.get("rescheduled") is True and isinstance(result.get("appointment"), dict):
        appointment = result["appointment"]
        service = appointment.get("service", "appointment")
        date_label = appointment.get("local_date_label", "")
        time_label = appointment.get("local_time_label", "")
        reference = appointment.get("reference_code", "")
        reply = f"Your {service} appointment has been rescheduled"
        if date_label or time_label:
            reply += f" for {date_label} {time_label}".rstrip()
        if reference:
            reply += f". Reference code: {reference}"
        return reply + "."
    if result.get("found") is True and isinstance(result.get("matches"), list):
        names = [str(match.get("name") or "").strip() for match in result["matches"] if isinstance(match, dict) and str(match.get("name") or "").strip()]
        if len(names) == 1:
            return f"I found {names[0]}. Please confirm the appointment date/time, full name, phone, and email so I can check availability and summarize before booking."
        if names:
            return _services_list_card(names)
        return "I could not find that service in the clinic's active services. Please choose another service."
    if result.get("available") is True:
        selected = result.get("selected_slot")
        if selected:
            return _selected_slot_booking_reply(selected, clinic=clinic, data=data, args=args)
        alternatives = result.get("alternatives") if isinstance(result.get("alternatives"), list) else []
        if alternatives:
            options = ", ".join(_slot_summary(slot) for slot in alternatives[:5])
            return f"Slots are available: {options}. Which time works best for you?"
    if result.get("available") is False:
        alternatives = result.get("alternatives") if isinstance(result.get("alternatives"), list) else []
        if alternatives:
            options = ", ".join(_slot_summary(slot) for slot in alternatives[:3])
            return f"The requested slot is not available. Nearest available options are: {options}."
        return "That appointment time is not available. Please choose another date or time."
    return ""


def _contains_unverified_availability_claim(reply):
    text = str(reply or "").lower()
    if not text:
        return False
    date_words = (
        r"(?:today|tomorrow|"
        r"\b\d{4}-\d{2}-\d{2}\b|"
        r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b|"
        r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b)"
    )
    time_words = r"(?:\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b|\b\d{1,2}:\d{2}\b)"
    technical_object_words = r"(?:system|software|widget|platform|page|portal|app)"
    appointment_cue = rf"(?:\bappointments?\b(?!\s+{technical_object_words})|\bappointment\s+times?\b)"
    booking_cue = rf"(?:\bbook(?:ing)?\b(?!\s+{technical_object_words}))"
    scheduling_cue = rf"(?:{time_words}|{date_words}|\bslots?\b|{appointment_cue}|{booking_cue})"
    availability_words = r"(?:available|unavailable|fully booked|open|closed)"
    patterns = [
        rf"{scheduling_cue}.{{0,60}}\b{availability_words}\b",
        rf"\b{availability_words}\b.{{0,60}}{scheduling_cue}",
        r"\bfully booked\b",
        r"\b(?:(?:that|this|the)\s+)?time\s+(?:is\s+)?(?:available|unavailable|open|closed)\b",
        r"\bno\s+slots?\b",
    ]
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _system_message(clinic, context, patient_details_prompt="", confirmation_followup_prompt=""):
    ai_settings = get_or_create_clinic_ai_settings(clinic)
    custom_instructions = (ai_settings.instructions or "").strip()
    default_instructions = DEFAULT_MESSENGER_AI_PROMPT.strip()
    safe_context = _safe_context_for_prompt(context)
    content_parts = [
        default_instructions,
    ]
    if custom_instructions and custom_instructions != default_instructions:
        content_parts.append("Clinic custom instructions:\n" + custom_instructions)
    content_parts.extend([
        CORE_AI_SAFETY_RULES,
        CURRENT_BOOKING_SAFETY_RULES,
        YAKAP_AI_SAFETY_RULES,
        "Clinic context JSON:",
        json.dumps(safe_context, default=str),
    ])
    if patient_details_prompt:
        content_parts.append(patient_details_prompt)
    if confirmation_followup_prompt:
        content_parts.append(confirmation_followup_prompt)
    return {
        "role": "system",
        "content": "\n\n".join(content_parts),
    }


def _clean_gateway_content(value):
    return str(value or "").strip()[:MAX_GATEWAY_MESSAGE_CHARS]


def _messages_for_request(clinic, context, data):
    messages = [_system_message(
        clinic,
        context,
        _known_patient_details_prompt(data),
        _current_confirmation_followup_prompt(data),
    )]
    history = data.get("history", [])
    if isinstance(history, list):
        for item in history[-16:]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role", "")).strip().lower()
            if role not in {"user", "assistant"}:
                continue
            content = _clean_gateway_content(item.get("content", ""))
            if content:
                messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": _clean_gateway_content(data.get("message", ""))})
    return messages


def _provider_settings_for_clinic(clinic):
    provider_settings, _ = ClinicAIProviderSettings.objects.get_or_create(clinic=clinic)
    return provider_settings


def _provider_model_attempts(provider_settings):
    primary_model = (provider_settings.model or "").strip()
    fallback_model = (provider_settings.fallback_model or "").strip() or primary_model
    return [("primary", primary_model), ("fallback", fallback_model)]


def _call_provider_with_fallback(provider_settings, messages, tools):
    last_error = "empty_provider_reply"
    for model_role, model in _provider_model_attempts(provider_settings):
        try:
            provider_message = call_chat_completion(
                provider_settings,
                messages,
                tools=tools,
                model=model,
                model_role=model_role,
            )
        except AIProviderError:
            last_error = "ai_provider_error"
            logger.warning(
                "AI gateway provider request failed",
                extra={
                    "clinic_id": provider_settings.clinic_id,
                    "model_role": model_role,
                },
            )
            continue

        tool_calls = provider_message.get("tool_calls") or []
        if tool_calls or _clean_gateway_content(provider_message.get("content", "")):
            return provider_message, ""

        last_error = "empty_provider_reply"
        logger.warning(
            "AI gateway provider returned empty reply",
            extra={
                "clinic_id": provider_settings.clinic_id,
                "model_role": model_role,
            },
        )
    return None, last_error


def _gateway_ai_enabled(channel, clinic):
    ai_settings = get_or_create_clinic_ai_settings(clinic)
    if channel == "messenger":
        return ai_settings.safe_messenger_response_mode == ClinicAISettings.MESSENGER_MODE_AI
    return ai_settings.is_ai_enabled


def _tool_definitions():
    return [
        {
            "type": "function",
            "function": {
                "name": "match_services",
                "description": "Find active clinic services matching a patient query.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Service name or need described by the patient."},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "check_availability",
                "description": "Check available appointment slots for a clinic service.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service_id": {"type": "integer"},
                        "preferred_starts_at": {"type": "string", "description": "Optional ISO date-time requested by the patient."},
                        "preferred_date": {"type": "string", "description": "Optional ISO date requested by the patient."},
                    },
                    "required": ["service_id"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "find_verified_appointment",
                "description": "Find a future appointment after verifying reference code and phone number.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reference_code": {"type": "string"},
                        "phone": {"type": "string"},
                    },
                    "required": ["reference_code", "phone"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "cancel_verified_appointment",
                "description": "Cancel a verified future appointment after explicit patient confirmation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reference_code": {"type": "string"},
                        "phone": {"type": "string"},
                        "confirmed": {"type": "boolean"},
                        "reason": {"type": "string"},
                    },
                    "required": ["reference_code", "phone", "confirmed"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "reschedule_verified_appointment",
                "description": "Reschedule a verified future appointment after explicit patient confirmation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reference_code": {"type": "string"},
                        "phone": {"type": "string"},
                        "starts_at": {"type": "string", "description": "New ISO date-time requested by the patient."},
                        "confirmed": {"type": "boolean"},
                    },
                    "required": ["reference_code", "phone", "starts_at", "confirmed"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "book_confirmed_appointment",
                "description": "Create an appointment only after the patient explicitly confirms the full booking details.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service_id": {"type": "integer"},
                        "starts_at": {"type": "string", "description": "Confirmed ISO appointment start time."},
                        "full_name": {"type": "string"},
                        "phone": {"type": "string"},
                        "email": {"type": "string"},
                        "reason": {"type": "string"},
                        "confirmed": {"type": "boolean"},
                    },
                    "required": ["service_id", "starts_at", "full_name", "phone", "email", "confirmed"],
                    "additionalProperties": False,
                },
            },
        },
    ]


def _json_tool_arguments(call):
    function = call.get("function") if isinstance(call, dict) else None
    raw_arguments = function.get("arguments", "{}") if isinstance(function, dict) else "{}"
    if isinstance(raw_arguments, dict):
        return raw_arguments
    try:
        parsed = json.loads(raw_arguments or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _bool_value(value):
    return value is True


def _clean_input_sequence(value):
    try:
        sequence = int(value)
    except (TypeError, ValueError):
        return 0
    return sequence if sequence > 0 else 0


def _has_messenger_turn_binding(data):
    return bool(
        str(data.get("psid", "")).strip()
        and str(data.get("turn_token", "")).strip()
        and _clean_input_sequence(data.get("input_sequence"))
    )


def _mutation_turn_binding_error(name):
    message = "Messenger appointment mutation requires current turn metadata."
    if name == "book_confirmed_appointment":
        return {"created": False, "error": message}
    if name == "cancel_verified_appointment":
        return {"cancelled": False, "error": message}
    if name == "reschedule_verified_appointment":
        return {"rescheduled": False, "error": message}
    return {"error": message}


def _tool_name(call):
    function = call.get("function") if isinstance(call, dict) else None
    return function.get("name", "") if isinstance(function, dict) else ""


def _mutating_tool_succeeded(name, result):
    if not isinstance(result, dict):
        return False
    return (
        (name == "book_confirmed_appointment" and result.get("created") is True)
        or (name == "cancel_verified_appointment" and result.get("cancelled") is True)
        or (name == "reschedule_verified_appointment" and result.get("rescheduled") is True)
    )


def _tool_calls_are_allowed(tool_calls, mutation_already_executed=False):
    if not isinstance(tool_calls, list):
        return False
    if len(tool_calls) > MAX_GATEWAY_TOOL_CALLS_PER_RESPONSE:
        return False
    names = [_tool_name(call) for call in tool_calls]
    if any(name not in GATEWAY_TOOL_NAMES for name in names):
        return False
    mutation_count = sum(1 for name in names if name in MUTATING_TOOL_NAMES)
    if mutation_count > 1:
        return False
    if mutation_already_executed and mutation_count:
        return False
    return True


def _booking_confirmed_argument(channel, data, args):
    if not _bool_value(args.get("confirmed")):
        return False, ""
    clinic = _clinic_for_tool(channel, data)
    previous_assistant = _latest_assistant_history_text(data)
    if _confirmed_in_current_turn(data) and _latest_assistant_has_complete_booking_summary(data, args, clinic):
        return True, ""
    if _confirmed_in_current_turn(data):
        mismatch_error = _booking_summary_tool_mismatch_error(previous_assistant, args, clinic)
        if _text_has_complete_booking_summary_terms(previous_assistant) and mismatch_error:
            return False, f"{mismatch_error} Please restate the correct full summary and ask the patient to confirm again."
        return False, "Appointment creation requires explicit user confirmation after a complete booking summary with service, date/time, full name, phone, and email."
    return False, "Appointment creation requires explicit user confirmation; current patient message did not explicitly confirm the complete details."


def _appointment_change_confirmed_argument(data, args):
    if not _bool_value(args.get("confirmed")):
        return False, ""
    if _confirmed_in_current_turn(data):
        return True, ""
    return False, "Appointment change requires explicit user confirmation; current patient message did not explicitly confirm the appointment change details."


def _execute_tool(channel, data, name, args):
    if channel == "messenger":
        page_id = data.get("page_id", "")
        psid = data.get("psid", "")
        turn_token = data.get("turn_token", "")
        input_sequence = data.get("input_sequence")
        if name in MUTATING_TOOL_NAMES and not _has_messenger_turn_binding(data):
            return _mutation_turn_binding_error(name)
        if name == "match_services":
            return match_services(page_id, args.get("query", ""))
        if name == "check_availability":
            if not _current_turn_allows_availability_tool(data):
                return _blocked_availability_tool_result()
            blocked_exact_slot = _availability_tool_args_match_current_turn(channel, data, args)
            if blocked_exact_slot:
                return blocked_exact_slot
            mismatch = _weekday_mismatch_result(channel, data, args)
            if mismatch:
                return mismatch
            return check_availability(
                page_id,
                args.get("service_id"),
                preferred_starts_at=args.get("preferred_starts_at"),
                preferred_date=args.get("preferred_date"),
            )
        if name == "find_verified_appointment":
            return find_verified_appointment(page_id, args.get("reference_code", ""), args.get("phone", ""))
        if name == "cancel_verified_appointment":
            confirmed, confirmation_error = _appointment_change_confirmed_argument(data, args)
            if confirmation_error:
                return {"cancelled": False, "error": confirmation_error}
            return cancel_verified_appointment(
                page_id,
                args.get("reference_code", ""),
                args.get("phone", ""),
                confirmed,
                reason=args.get("reason", ""),
                psid=psid,
                turn_token=turn_token,
                input_sequence=input_sequence,
            )
        if name == "reschedule_verified_appointment":
            confirmed, confirmation_error = _appointment_change_confirmed_argument(data, args)
            if confirmation_error:
                return {"rescheduled": False, "error": confirmation_error}
            return reschedule_verified_appointment(
                page_id,
                args.get("reference_code", ""),
                args.get("phone", ""),
                args.get("starts_at", ""),
                confirmed,
                psid=psid,
                turn_token=turn_token,
                input_sequence=input_sequence,
            )
        if name == "book_confirmed_appointment":
            mismatch = _weekday_mismatch_result(channel, data, args, mutation=True)
            if mismatch:
                return mismatch
            confirmed, confirmation_error = _booking_confirmed_argument(channel, data, args)
            if confirmation_error:
                return {"created": False, "error": confirmation_error}
            return book_confirmed_appointment(
                page_id,
                args.get("service_id"),
                args.get("starts_at", ""),
                args.get("full_name", ""),
                args.get("phone", ""),
                confirmed,
                email=args.get("email", ""),
                reason=args.get("reason", ""),
                psid=psid,
                turn_token=turn_token,
                input_sequence=input_sequence,
            )
    if channel == "widget":
        clinic_slug = data.get("clinic_slug", "")
        if name == "match_services":
            return match_widget_services(clinic_slug, args.get("query", ""))
        if name == "check_availability":
            if not _current_turn_allows_availability_tool(data):
                return _blocked_availability_tool_result()
            blocked_exact_slot = _availability_tool_args_match_current_turn(channel, data, args)
            if blocked_exact_slot:
                return blocked_exact_slot
            mismatch = _weekday_mismatch_result(channel, data, args)
            if mismatch:
                return mismatch
            return check_widget_availability(
                clinic_slug,
                args.get("service_id"),
                preferred_starts_at=args.get("preferred_starts_at"),
                preferred_date=args.get("preferred_date"),
            )
        if name == "find_verified_appointment":
            return find_widget_verified_appointment(clinic_slug, args.get("reference_code", ""), args.get("phone", ""))
        if name == "cancel_verified_appointment":
            confirmed, confirmation_error = _appointment_change_confirmed_argument(data, args)
            if confirmation_error:
                return {"cancelled": False, "error": confirmation_error}
            return cancel_widget_verified_appointment(
                clinic_slug,
                args.get("reference_code", ""),
                args.get("phone", ""),
                confirmed,
                reason=args.get("reason", ""),
            )
        if name == "reschedule_verified_appointment":
            confirmed, confirmation_error = _appointment_change_confirmed_argument(data, args)
            if confirmation_error:
                return {"rescheduled": False, "error": confirmation_error}
            return reschedule_widget_verified_appointment(
                clinic_slug,
                args.get("reference_code", ""),
                args.get("phone", ""),
                args.get("starts_at", ""),
                confirmed,
            )
        if name == "book_confirmed_appointment":
            mismatch = _weekday_mismatch_result(channel, data, args, mutation=True)
            if mismatch:
                return mismatch
            confirmed, confirmation_error = _booking_confirmed_argument(channel, data, args)
            if confirmation_error:
                return {"created": False, "error": confirmation_error}
            return book_widget_confirmed_appointment(
                clinic_slug,
                args.get("service_id"),
                args.get("starts_at", ""),
                args.get("full_name", ""),
                args.get("phone", ""),
                confirmed,
                email=args.get("email", ""),
                reason=args.get("reason", ""),
            )
    if channel == "voice":
        clinic_slug = data.get("clinic_slug", "")
        if name == "match_services":
            return match_widget_services(clinic_slug, args.get("query", ""))
        if name == "check_availability":
            if not _current_turn_allows_availability_tool(data):
                return _blocked_availability_tool_result()
            blocked_exact_slot = _availability_tool_args_match_current_turn(channel, data, args)
            if blocked_exact_slot:
                return blocked_exact_slot
            mismatch = _weekday_mismatch_result(channel, data, args)
            if mismatch:
                return mismatch
            return check_widget_availability(
                clinic_slug,
                args.get("service_id"),
                preferred_starts_at=args.get("preferred_starts_at"),
                preferred_date=args.get("preferred_date"),
            )
        if name == "find_verified_appointment":
            return find_widget_verified_appointment(clinic_slug, args.get("reference_code", ""), args.get("phone", ""))
        if name == "cancel_verified_appointment":
            confirmed, confirmation_error = _appointment_change_confirmed_argument(data, args)
            if confirmation_error:
                return {"cancelled": False, "error": confirmation_error}
            return cancel_widget_verified_appointment(
                clinic_slug,
                args.get("reference_code", ""),
                args.get("phone", ""),
                confirmed,
                reason=args.get("reason", ""),
            )
        if name == "reschedule_verified_appointment":
            confirmed, confirmation_error = _appointment_change_confirmed_argument(data, args)
            if confirmation_error:
                return {"rescheduled": False, "error": confirmation_error}
            return reschedule_widget_verified_appointment(
                clinic_slug,
                args.get("reference_code", ""),
                args.get("phone", ""),
                args.get("starts_at", ""),
                confirmed,
            )
        if name == "book_confirmed_appointment":
            mismatch = _weekday_mismatch_result(channel, data, args, mutation=True)
            if mismatch:
                return mismatch
            confirmed, confirmation_error = _booking_confirmed_argument(channel, data, args)
            if confirmation_error:
                return {"created": False, "error": confirmation_error}
            return book_voice_widget_confirmed_appointment(
                clinic_slug,
                args.get("service_id"),
                args.get("starts_at", ""),
                args.get("full_name", ""),
                args.get("phone", ""),
                confirmed,
                email=args.get("email", ""),
                reason=args.get("reason", ""),
            )
    return {"error": "Unknown tool."}


def build_gateway_reply(data):
    channel = str(data.get("channel", "")).strip().lower()
    clinic = _resolve_gateway_clinic(data)
    if not clinic:
        return _fallback_for_clinic(None, "clinic_not_found")
    if not _gateway_ai_enabled(channel, clinic):
        return _fallback_for_clinic(clinic, "ai_disabled")
    if channel in {"widget", "voice"} and _is_out_of_scope_system_question(data.get("message", "")):
        return {"reply": _scoped_out_of_scope_reply(clinic), "fallback": False, "error": ""}

    provider_settings = _provider_settings_for_clinic(clinic)
    if not provider_settings.is_configured:
        return _fallback_for_clinic(clinic, "ai_provider_unconfigured")

    context = _context_for_gateway(channel, data)
    messages = _messages_for_request(clinic, context, data)
    tools = _tool_definitions()
    max_iterations = max(1, getattr(settings, "AI_GATEWAY_MAX_TOOL_ITERATIONS", 5))
    mutation_executed = False
    last_tool_result = None
    last_tool_name = ""
    last_tool_args = {}
    for _iteration in range(max_iterations):
        provider_message, provider_error = _call_provider_with_fallback(provider_settings, messages, tools)
        if provider_message is None:
            tool_reply = _reply_from_tool_result(last_tool_result, clinic=clinic, data=data, args=last_tool_args)
            if tool_reply:
                return {"reply": tool_reply, "fallback": False, "error": ""}
            return _fallback_for_clinic(clinic, provider_error)

        tool_calls = provider_message.get("tool_calls") or []
        if not tool_calls:
            reply = _clean_gateway_content(provider_message.get("content", ""))
            if not reply:
                return _fallback_for_clinic(clinic, "empty_provider_reply")
            if _contains_unverified_availability_claim(reply):
                if last_tool_name == "check_availability":
                    tool_reply = _reply_from_tool_result(last_tool_result, clinic=clinic, data=data, args=last_tool_args)
                    if tool_reply:
                        return {"reply": tool_reply, "fallback": False, "error": ""}
                return _fallback_for_clinic(clinic, "unverified_availability_claim")
            return {"reply": reply, "fallback": False, "error": ""}
        if not _tool_calls_are_allowed(tool_calls, mutation_executed):
            return _fallback_for_clinic(clinic, "invalid_tool_call")

        messages.append({
            "role": "assistant",
            "content": provider_message.get("content", "") or "",
            "tool_calls": tool_calls,
        })
        for call in tool_calls:
            name = _tool_name(call)
            tool_args = _json_tool_arguments(call)
            try:
                result = _execute_tool(channel, data, name, tool_args)
            except Exception:
                logger.warning(
                    "AI gateway tool execution failed",
                    extra={"clinic_id": clinic.id, "tool_name": name},
                )
                result = {"error": "Tool execution failed."}
            last_tool_result = result
            last_tool_name = name
            last_tool_args = tool_args
            if name in MUTATING_TOOL_NAMES:
                mutation_executed = True
                if _mutating_tool_succeeded(name, result):
                    reply = _reply_from_tool_result(result, clinic=clinic, data=data, args=tool_args)
                    if reply:
                        return {"reply": reply, "fallback": False, "error": ""}
            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id", "") if isinstance(call, dict) else "",
                "content": json.dumps(result, default=str),
            })

    return _fallback_for_clinic(clinic, "tool_loop_exceeded")
