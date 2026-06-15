from datetime import datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo
import json

import requests
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.http import require_POST

from appointments.models import Appointment
from clinics.models import Clinic, ClinicAISettings
from messenger.callback_urls import build_n8n_callback_urls
from patients.models import Patient, normalize_phone
from scheduling.utils import generate_slots
from widget.ai_client import AssistantUnavailable, call_assistant_webhook, fallback_message_for
from yakap.services import create_appointment_yakap_snapshot, is_public_yakap_request_allowed, public_yakap_badge_label


MIN_BOOKING_PHONE_DIGITS = 7
SLOT_CONFLICT_MESSAGE = "That slot is no longer available. Please choose another time."
PAST_APPOINTMENT_TIME_MESSAGE = "Please choose today or a future appointment date/time. Previous dates and past times are not available."
WIDGET_AI_DEFAULT_MAX_MESSAGE_LENGTH = 1000
WIDGET_AI_DEFAULT_RATE_LIMIT = 20
WIDGET_AI_DEFAULT_RATE_WINDOW_SECONDS = 300
WIDGET_AI_CONVERSATION_ID_MAX_LENGTH = 64
GUEST_FULL_NAME_MAX_LENGTH = 160
GUEST_PHONE_MAX_LENGTH = 40
GUEST_EMAIL_MAX_LENGTH = 254
GUEST_REASON_MAX_LENGTH = 2000
WIDGET_PUBLIC_BOOKING_DEFAULT_RATE_LIMIT = 5
WIDGET_PUBLIC_BOOKING_DEFAULT_RATE_WINDOW_SECONDS = 300
BOOKING_RATE_LIMIT_MESSAGE = "Too many booking attempts. Please wait before trying again."


def _clinic_localdate(clinic):
    return timezone.now().astimezone(ZoneInfo(clinic.timezone)).date()


def _find_next_available_date(clinic, service, from_date, max_days=14):
    if service is None:
        return None
    for i in range(1, max_days + 1):
        d = from_date + timedelta(days=i)
        slots = generate_slots(clinic, service, d)
        if slots:
            return d
    return None


def _enabled_yakap_settings(clinic):
    try:
        yakap_settings = clinic.yakap_settings
    except ObjectDoesNotExist:
        return None
    return yakap_settings if yakap_settings.is_enabled else None


def _parse_service_id(value):
    if not value:
        return None
    try:
        service_id = int(value)
    except (TypeError, ValueError):
        return None
    return service_id if service_id > 0 else None


def _booking_context(clinic, request):
    services = clinic.services.filter(is_active=True, is_archived=False).select_related("yakap_rule", "yakap_rule__category")
    service_id = _parse_service_id(request.GET.get("service"))
    service = services.filter(pk=service_id).first() if service_id else services.first()
    date_str = request.GET.get("date")
    clinic_today = _clinic_localdate(clinic)
    selected_date = clinic_today + timedelta(days=1)
    if date_str:
        selected_date = parse_date(date_str) or selected_date
    slots = []
    if service:
        slots = generate_slots(clinic, service, selected_date)
    next_available_date = None
    if not slots:
        next_available_date = _find_next_available_date(clinic, service, selected_date)
    dates = [clinic_today + timedelta(days=i) for i in range(1, 15)]
    yakap_settings = _enabled_yakap_settings(clinic)
    promotable_service_ids = []
    if yakap_settings:
        for item in services:
            if is_public_yakap_request_allowed(clinic, item, settings=yakap_settings):
                promotable_service_ids.append(item.id)
                item.public_yakap_badge_label = public_yakap_badge_label(item.yakap_rule)
    return {
        "clinic": clinic,
        "services": services,
        "service": service,
        "dates": dates,
        "selected_date": selected_date,
        "slots": slots,
        "next_available_date": next_available_date,
        "yakap_settings": yakap_settings,
        "yakap_promotable_service_ids": promotable_service_ids,
        "has_public_yakap_services": bool(promotable_service_ids),
    }


def _get_public_clinic_or_404(clinic_slug):
    return get_object_or_404(Clinic, slug=clinic_slug, is_active=True, requires_onboarding=False)


@xframe_options_exempt
def widget_book(request, clinic_slug):
    clinic = _get_public_clinic_or_404(clinic_slug)
    source = _public_booking_source(request)
    if request.method == "POST":
        appointment, error = _process_guest_booking(clinic, request, source)
        if request.headers.get("HX-Request"):
            if error:
                status = 429 if error == BOOKING_RATE_LIMIT_MESSAGE else 409
                return render(request, "widget/partials/booking_error.html", {"clinic": clinic, "error": error, "widget_source": source}, status=status)
            return render(request, "widget/partials/booking_success.html", {"clinic": clinic, "appointment": appointment, "widget_source": source})
        if error:
            return redirect("widget:home", clinic_slug=clinic.slug)
        return render(request, "widget/booking_success.html", {"clinic": clinic, "appointment": appointment, "widget_source": source})
    return redirect("widget:home", clinic_slug=clinic.slug)


@xframe_options_exempt
def widget_home(request, clinic_slug):
    clinic = _get_public_clinic_or_404(clinic_slug)
    context = _booking_context(clinic, request)
    context["faqs"] = clinic.faqs.filter(is_active=True)
    context["widget_source"] = _public_booking_source(request)
    context["widget_ai_max_message_length"] = getattr(settings, "WIDGET_AI_CHAT_MAX_MESSAGE_LENGTH", WIDGET_AI_DEFAULT_MAX_MESSAGE_LENGTH)
    return render(request, "widget/widget.html", context)


def widget_slots(request, clinic_slug):
    clinic = _get_public_clinic_or_404(clinic_slug)
    return render(request, "widget/partials/slots.html", _booking_context(clinic, request))


def _public_booking_source(request):
    if request.GET.get("source") == Appointment.SOURCE_EMBED:
        return Appointment.SOURCE_EMBED
    return Appointment.SOURCE_CHAT_WIDGET


def _validate_guest_identity(full_name, phone, email, reason=""):
    if not full_name or not phone:
        return "Please provide your full name and phone number."
    if len(full_name) > GUEST_FULL_NAME_MAX_LENGTH:
        return "Please keep your full name under 160 characters."
    if len(phone) > GUEST_PHONE_MAX_LENGTH:
        return "Please keep your phone number under 40 characters."
    if len(normalize_phone(phone)) < MIN_BOOKING_PHONE_DIGITS:
        return "Please enter a valid phone number."
    if not email:
        return "Please provide your email address."
    if len(email) > GUEST_EMAIL_MAX_LENGTH:
        return "Please keep your email address under 254 characters."
    try:
        validate_email(email)
    except ValidationError:
        return "Please enter a valid email address."
    if len(reason) > GUEST_REASON_MAX_LENGTH:
        return "Please keep appointment notes under 2000 characters."
    return ""


def _client_ip(request):
    return request.META.get("REMOTE_ADDR", "unknown")


def _rate_limit_increment_allowed(key, limit, window_seconds):
    if cache.add(key, 1, timeout=window_seconds):
        return True
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=window_seconds)
        return True
    return count <= limit


def _public_booking_rate_limit_error(clinic, request, phone, email):
    limit = getattr(settings, "WIDGET_PUBLIC_BOOKING_RATE_LIMIT", WIDGET_PUBLIC_BOOKING_DEFAULT_RATE_LIMIT)
    if limit <= 0:
        return ""
    window_seconds = getattr(
        settings,
        "WIDGET_PUBLIC_BOOKING_RATE_WINDOW_SECONDS",
        WIDGET_PUBLIC_BOOKING_DEFAULT_RATE_WINDOW_SECONDS,
    )
    ip = _client_ip(request)
    identity = normalize_phone(phone) or email.lower()
    keys = [f"widget_booking_rate:clinic:{clinic.id}:ip:{ip}"]
    if identity:
        keys.append(f"widget_booking_rate:clinic:{clinic.id}:identity:{identity}")
    for key in keys:
        if not _rate_limit_increment_allowed(key, limit, window_seconds):
            return BOOKING_RATE_LIMIT_MESSAGE
    return ""


def _process_guest_booking(clinic, request_or_data, source):
    request = request_or_data if hasattr(request_or_data, "POST") else None
    data = request.POST if request else request_or_data
    full_name = data.get("full_name", "").strip()
    phone = data.get("phone", "").strip()
    email = data.get("email", "").strip()
    reason = data.get("reason", "").strip()
    yakap_requested = data.get("yakap_requested") == "on"
    error = _validate_guest_identity(full_name, phone, email, reason)
    if error:
        return None, error

    try:
        starts_at = datetime.fromisoformat(data.get("starts_at", ""))
    except (TypeError, ValueError):
        return None, "Please choose a valid appointment time."
    if timezone.is_naive(starts_at):
        starts_at = timezone.make_aware(starts_at, ZoneInfo(clinic.timezone))
    starts_at = starts_at.astimezone(dt_timezone.utc)

    with transaction.atomic():
        locked_clinic = Clinic.objects.select_for_update().get(pk=clinic.pk)
        if locked_clinic.requires_onboarding or not locked_clinic.is_active:
            return None, "Online booking is not available for this clinic yet."
        service_id = _parse_service_id(data.get("service"))
        service = locked_clinic.services.filter(is_active=True, is_archived=False, pk=service_id).first() if service_id else None
        if service is None:
            return None, "Please choose a valid service."
        if starts_at <= timezone.now():
            return None, PAST_APPOINTMENT_TIME_MESSAGE

        ends_at = starts_at + timedelta(minutes=service.effective_duration())
        local_date = starts_at.astimezone(ZoneInfo(locked_clinic.timezone)).date()
        available = any(
            slot["starts_at"] == starts_at
            for slot in generate_slots(locked_clinic, service, local_date)
        )
        if not available:
            return None, SLOT_CONFLICT_MESSAGE
        if request:
            error = _public_booking_rate_limit_error(locked_clinic, request, phone, email)
            if error:
                return None, error

        patient, _ = Patient.find_or_create_for_booking(
            clinic=locked_clinic,
            full_name=full_name,
            phone=phone,
            email=email,
            notes=reason,
        )
        try:
            appointment = Appointment.objects.create(
                clinic=locked_clinic,
                patient=patient,
                service=service,
                starts_at=starts_at,
                ends_at=ends_at,
                status=Appointment.STATUS_CONFIRMED if locked_clinic.booking_approval_mode == Clinic.APPROVAL_AUTO else Appointment.STATUS_PENDING,
                source=source,
                reason=reason,
            )
        except ValidationError:
            return None, SLOT_CONFLICT_MESSAGE
        yakap_settings = _enabled_yakap_settings(locked_clinic)
        if yakap_requested and is_public_yakap_request_allowed(locked_clinic, service, settings=yakap_settings):
            create_appointment_yakap_snapshot(appointment, requested=True)
    return appointment, None


def embed_js(request, clinic_slug):
    clinic = _get_public_clinic_or_404(clinic_slug)
    src = request.build_absolute_uri(reverse("widget:home", args=[clinic.slug])) + "?source=embed"
    accent = clinic.safe_widget_accent_color
    body = f"""
(function() {{
  var accent = {json.dumps(accent)};
  var src = {json.dumps(src)};
  var iframe;
  var style = document.createElement('style');
  style.textContent = '@media (max-width: 640px) {{ .kliniassist-widget-frame {{ width:calc(100vw - 24px - env(safe-area-inset-right)) !important; height:calc(100dvh - 24px - env(safe-area-inset-bottom)) !important; right:max(12px, env(safe-area-inset-right)) !important; bottom:max(12px, env(safe-area-inset-bottom)) !important; border-radius:20px !important; }} }}';
  document.head.appendChild(style);
  var launcher = document.createElement('button');
  launcher.setAttribute('type', 'button');
  launcher.setAttribute('aria-label', 'Open booking widget');
  launcher.setAttribute('title', 'Book an appointment');
  launcher.innerHTML = '<svg aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/><path d="M8 14h.01"/><path d="M12 14h.01"/><path d="M16 14h.01"/></svg>';
  launcher.style.cssText = 'position:fixed;bottom:max(16px, env(safe-area-inset-bottom));right:max(16px, env(safe-area-inset-right));width:60px;height:60px;border-radius:50%;border:none;z-index:9999;background:' + accent + ';color:white;cursor:pointer;box-shadow:0 10px 24px rgba(8,51,68,0.22);display:flex;align-items:center;justify-content:center;transition:transform .2s, box-shadow .2s;outline:3px solid transparent;outline-offset:3px;';
  launcher.addEventListener('mouseenter', function() {{ launcher.style.transform = 'scale(1.05)'; }});
  launcher.addEventListener('mouseleave', function() {{ launcher.style.transform = 'scale(1)'; }});
  launcher.addEventListener('focus', function() {{ launcher.style.outlineColor = 'rgba(8,51,68,0.35)'; }});
  launcher.addEventListener('blur', function() {{ launcher.style.outlineColor = 'transparent'; }});
  launcher.addEventListener('click', function() {{
    if (!iframe) {{
      iframe = document.createElement('iframe');
      iframe.className = 'kliniassist-widget-frame';
      iframe.src = src;
      iframe.style.cssText = 'position:fixed;bottom:max(16px, env(safe-area-inset-bottom));right:max(16px, env(safe-area-inset-right));width:420px;max-width:calc(100vw - 32px - env(safe-area-inset-right));height:680px;max-height:calc(100dvh - 32px - env(safe-area-inset-bottom));border:none;z-index:9999;background:transparent;border-radius:24px;box-shadow:0 20px 50px rgba(0,0,0,0.2);opacity:0;transform:translateY(20px);transition:opacity .3s, transform .3s;';
      iframe.allow = 'clipboard-write';
      document.body.appendChild(iframe);
      requestAnimationFrame(function() {{ iframe.style.opacity = '1'; iframe.style.transform = 'translateY(0)'; }});
    }} else {{
      iframe.style.display = 'block';
      requestAnimationFrame(function() {{ iframe.style.opacity = '1'; iframe.style.transform = 'translateY(0)'; }});
    }}
    launcher.style.display = 'none';
  }});
  document.body.appendChild(launcher);
  window.addEventListener('message', function(e) {{
    if (e.data && e.data.type === 'kliniassist-minimize') {{
      if (iframe) {{
        iframe.style.opacity = '0';
        iframe.style.transform = 'translateY(20px)';
        setTimeout(function() {{ iframe.style.display = 'none'; }}, 300);
      }}
      launcher.style.display = 'flex';
    }}
  }});
}})();
"""
    return HttpResponse(body, content_type="application/javascript")


def chat_api(request, clinic_slug):
    clinic = _get_public_clinic_or_404(clinic_slug)
    services = list(
        clinic.services.filter(is_active=True, is_archived=False).values(
            "id", "name", "duration_minutes"
        )
    )
    return JsonResponse({"message": clinic.widget_welcome_message, "services": services})


def _clean_widget_conversation_id(value):
    cleaned = "".join(
        char for char in (value or "").strip()
        if char.isalnum() or char in {"-", "_", ":"}
    )
    return cleaned[:WIDGET_AI_CONVERSATION_ID_MAX_LENGTH] or "default"


def _widget_chat_history_version_key(clinic, conversation_id="default"):
    return f"widget_chat_history_version_{clinic.id}_{conversation_id}"


def _widget_chat_history_key(clinic, conversation_id="default"):
    return f"widget_chat_history_{clinic.id}_{conversation_id}"


def _widget_chat_history_updated_at_key(clinic, conversation_id="default"):
    return f"widget_chat_history_updated_at_{clinic.id}_{conversation_id}"


def _widget_chat_history_timeout():
    try:
        minutes = int(getattr(
            settings,
            "WIDGET_AI_CHAT_HISTORY_TIMEOUT_MINUTES",
            getattr(settings, "MESSENGER_SESSION_TIMEOUT_MINUTES", 30),
        ))
    except (TypeError, ValueError):
        minutes = 30
    return timedelta(minutes=minutes)


def _widget_chat_history_expired(request, clinic, conversation_id="default"):
    history = request.session.get(_widget_chat_history_key(clinic, conversation_id), [])
    if not history:
        return False
    raw_updated_at = request.session.get(_widget_chat_history_updated_at_key(clinic, conversation_id))
    if not raw_updated_at:
        return True
    try:
        updated_at = datetime.fromisoformat(raw_updated_at)
    except (TypeError, ValueError):
        return True
    if timezone.is_naive(updated_at):
        updated_at = timezone.make_aware(updated_at, dt_timezone.utc)
    return updated_at < timezone.now() - _widget_chat_history_timeout()


def _widget_chat_history(request, clinic, ai_settings=None, conversation_id="default"):
    history_key = _widget_chat_history_key(clinic, conversation_id)
    if ai_settings:
        current_version = ai_settings.updated_at.isoformat()
        version_key = _widget_chat_history_version_key(clinic, conversation_id)
        if request.session.get(version_key) != current_version:
            request.session[history_key] = []
            request.session[version_key] = current_version
            request.session.modified = True
            return []
    if _widget_chat_history_expired(request, clinic, conversation_id):
        request.session[history_key] = []
        request.session[_widget_chat_history_updated_at_key(clinic, conversation_id)] = timezone.now().isoformat()
        request.session.modified = True
        return []
    return request.session.get(history_key, [])


def _save_widget_chat_history(request, clinic, history, ai_settings=None, conversation_id="default"):
    request.session[_widget_chat_history_key(clinic, conversation_id)] = history[-10:]
    request.session[_widget_chat_history_updated_at_key(clinic, conversation_id)] = timezone.now().isoformat()
    if ai_settings:
        request.session[_widget_chat_history_version_key(clinic, conversation_id)] = ai_settings.updated_at.isoformat()


def _widget_ai_rate_limited(request, clinic, conversation_id):
    limit = getattr(settings, "WIDGET_AI_CHAT_RATE_LIMIT", WIDGET_AI_DEFAULT_RATE_LIMIT)
    if not limit:
        return False
    window_seconds = getattr(settings, "WIDGET_AI_CHAT_RATE_WINDOW_SECONDS", WIDGET_AI_DEFAULT_RATE_WINDOW_SECONDS)
    if not request.session.session_key:
        request.session.create()
    actor = request.session.session_key or request.META.get("REMOTE_ADDR", "unknown")
    cache_key = f"widget_ai_chat_rate:{clinic.id}:{actor}"
    count = cache.get(cache_key, 0)
    if count >= limit:
        return True
    cache.set(cache_key, count + 1, timeout=window_seconds)
    return False


WIDGET_AI_STATE = "ai"
WIDGET_AI_SUGGESTIONS = []


def _widget_ai_json(message, options=None, status=200):
    return JsonResponse({
        "state": WIDGET_AI_STATE,
        "message": message,
        "options": options or [],
        "next_action": "text_input",
    }, status=status)


def _widget_ai_fallback_message(ai_settings):
    message = fallback_message_for(ai_settings)
    if "book" not in message.lower():
        message = f"{message} You can still use Book an Appointment to schedule a visit."
    return message


def _widget_ai_unavailable_message(ai_settings, error):
    if getattr(settings, "DEBUG", False) and "webhook URL is not configured" in str(error):
        return (
            "Assistant webhook is not configured locally. Set ASSISTANT_N8N_WEBHOOK_URL "
            "and N8N_WEBHOOK_SECRET, then restart Django. You can still use Book an Appointment "
            "to schedule a visit."
        )
    return _widget_ai_fallback_message(ai_settings)


def _widget_ai_initial_message(clinic):
    return clinic.widget_welcome_message or "Welcome! How can we help you book an appointment today?"


def _widget_ai_message_from_action(action, value):
    text = (value or "").strip()
    if action == "start_booking" or text == "start_booking":
        return "I want to book an appointment"
    if action == "view_faqs" or text == "view_faqs":
        return "I have a question about the clinic"
    if text:
        return text
    return ""


def _handle_widget_ai_chat(request, clinic, action, value, conversation_id="default"):
    ai_settings, _ = ClinicAISettings.objects.get_or_create(clinic=clinic)

    if not ai_settings.is_ai_enabled:
        return _widget_ai_json(_widget_ai_fallback_message(ai_settings))

    if action == "init":
        _widget_chat_history(request, clinic, ai_settings, conversation_id)
        return _widget_ai_json(_widget_ai_initial_message(clinic), WIDGET_AI_SUGGESTIONS)

    message = _widget_ai_message_from_action(action, value)
    if not message:
        return _widget_ai_json(_widget_ai_initial_message(clinic), WIDGET_AI_SUGGESTIONS)
    max_message_length = getattr(settings, "WIDGET_AI_CHAT_MAX_MESSAGE_LENGTH", WIDGET_AI_DEFAULT_MAX_MESSAGE_LENGTH)
    if len(message) > max_message_length:
        return _widget_ai_json(f"Please keep messages under {max_message_length} characters.")
    if _widget_ai_rate_limited(request, clinic, conversation_id):
        return _widget_ai_json("Too many messages. Please wait a moment before trying again.", status=429)

    history = _widget_chat_history(request, clinic, ai_settings, conversation_id)
    if not request.session.session_key:
        request.session.create()
    assistant_session_id = f"{request.session.session_key}:{conversation_id}"

    try:
        reply = call_assistant_webhook(
            clinic,
            message,
            history,
            assistant_session_id,
            conversation_id,
            build_n8n_callback_urls(request, "widget"),
        )
    except AssistantUnavailable as error:
        reply = _widget_ai_unavailable_message(ai_settings, error)
    except (requests.RequestException, ValueError):
        reply = _widget_ai_fallback_message(ai_settings)

    history.extend([
        {"role": "user", "content": message},
        {"role": "assistant", "content": reply},
    ])
    _save_widget_chat_history(request, clinic, history, ai_settings, conversation_id)
    return _widget_ai_json(reply)


@require_POST
def chat_step(request, clinic_slug):
    clinic = _get_public_clinic_or_404(clinic_slug)
    action = request.POST.get("action", "")
    value = request.POST.get("value", "")
    conversation_id = _clean_widget_conversation_id(request.POST.get("conversation_id", ""))

    return _handle_widget_ai_chat(request, clinic, action, value, conversation_id)
