from datetime import datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo
import json

import requests
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.http import require_POST

from appointments.models import Appointment
from clinics.models import Clinic, ClinicAISettings
from patients.models import Patient, normalize_phone
from scheduling.utils import generate_slots
from widget.ai_client import AssistantUnavailable, call_assistant_webhook, fallback_message_for


MIN_BOOKING_PHONE_DIGITS = 7
SLOT_CONFLICT_MESSAGE = "That slot is no longer available. Please choose another time."


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


def _booking_context(clinic, request):
    services = clinic.services.filter(is_active=True, is_archived=False)
    service_id = request.GET.get("service")
    service = services.filter(pk=service_id).first() if service_id else services.first()
    date_str = request.GET.get("date")
    clinic_today = _clinic_localdate(clinic)
    selected_date = clinic_today + timedelta(days=1)
    if date_str:
        try:
            selected_date = timezone.datetime.fromisoformat(date_str).date()
        except ValueError:
            pass
    slots = []
    if service:
        slots = generate_slots(clinic, service, selected_date)
    next_available_date = None
    if not slots:
        next_available_date = _find_next_available_date(clinic, service, selected_date)
    dates = [clinic_today + timedelta(days=i) for i in range(1, 15)]
    return {
        "clinic": clinic,
        "services": services,
        "service": service,
        "dates": dates,
        "selected_date": selected_date,
        "slots": slots,
        "next_available_date": next_available_date,
    }


def _get_public_clinic_or_404(clinic_slug):
    return get_object_or_404(Clinic, slug=clinic_slug, is_active=True, requires_onboarding=False)


@xframe_options_exempt
def widget_book(request, clinic_slug):
    clinic = _get_public_clinic_or_404(clinic_slug)
    if request.method == "POST":
        appointment, error = _process_guest_booking(clinic, request.POST, _public_booking_source(request))
        if request.headers.get("HX-Request"):
            if error:
                return render(request, "widget/partials/booking_error.html", {"clinic": clinic, "error": error}, status=409)
            return render(request, "widget/partials/booking_success.html", {"clinic": clinic, "appointment": appointment})
        if error:
            return redirect("widget:home", clinic_slug=clinic.slug)
        return render(request, "widget/booking_success.html", {"clinic": clinic, "appointment": appointment})
    return redirect("widget:home", clinic_slug=clinic.slug)


@xframe_options_exempt
def widget_home(request, clinic_slug):
    clinic = _get_public_clinic_or_404(clinic_slug)
    context = _booking_context(clinic, request)
    context["faqs"] = clinic.faqs.filter(is_active=True)
    context["widget_source"] = _public_booking_source(request)
    return render(request, "widget/widget.html", context)


def widget_slots(request, clinic_slug):
    clinic = _get_public_clinic_or_404(clinic_slug)
    return render(request, "widget/partials/slots.html", _booking_context(clinic, request))


def _public_booking_source(request):
    if request.GET.get("source") == Appointment.SOURCE_EMBED:
        return Appointment.SOURCE_EMBED
    return Appointment.SOURCE_CHAT_WIDGET


def _validate_guest_identity(full_name, phone, email):
    if not full_name or not phone:
        return "Please provide your full name and phone number."
    if len(normalize_phone(phone)) < MIN_BOOKING_PHONE_DIGITS:
        return "Please enter a valid phone number."
    if email:
        try:
            validate_email(email)
        except ValidationError:
            return "Please enter a valid email address."
    return ""


def _process_guest_booking(clinic, data, source):
    full_name = data.get("full_name", "").strip()
    phone = data.get("phone", "").strip()
    email = data.get("email", "").strip()
    reason = data.get("reason", "").strip()
    error = _validate_guest_identity(full_name, phone, email)
    if error:
        return None, error

    try:
        starts_at = datetime.fromisoformat(data.get("starts_at", ""))
    except (TypeError, ValueError):
        return None, "Please choose a valid appointment time."
    if timezone.is_naive(starts_at):
        starts_at = timezone.make_aware(starts_at)
    starts_at = starts_at.astimezone(dt_timezone.utc)

    with transaction.atomic():
        locked_clinic = Clinic.objects.select_for_update().get(pk=clinic.pk)
        if locked_clinic.requires_onboarding or not locked_clinic.is_active:
            return None, "Online booking is not available for this clinic yet."
        service = locked_clinic.services.filter(is_active=True, is_archived=False, pk=data.get("service")).first()
        if service is None:
            return None, "Please choose a valid service."

        ends_at = starts_at + timedelta(minutes=service.effective_duration())
        local_date = starts_at.astimezone(ZoneInfo(locked_clinic.timezone)).date()
        available = any(
            slot["starts_at"] == starts_at
            for slot in generate_slots(locked_clinic, service, local_date)
        )
        if not available:
            return None, SLOT_CONFLICT_MESSAGE

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
  style.textContent = '@media (max-width: 640px) {{ .clinicflow-widget-frame {{ width:calc(100vw - 24px - env(safe-area-inset-right)) !important; height:calc(100dvh - 24px - env(safe-area-inset-bottom)) !important; right:max(12px, env(safe-area-inset-right)) !important; bottom:max(12px, env(safe-area-inset-bottom)) !important; border-radius:20px !important; }} }}';
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
      iframe.className = 'clinicflow-widget-frame';
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
    if (e.data && e.data.type === 'clinicflow-minimize') {{
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
            "id", "name", "duration_minutes", "price", "display_price"
        )
    )
    return JsonResponse({"message": clinic.widget_welcome_message, "services": services})


def _widget_chat_history(request, clinic):
    return request.session.get(f"widget_chat_history_{clinic.id}", [])


def _save_widget_chat_history(request, clinic, history):
    request.session[f"widget_chat_history_{clinic.id}"] = history[-10:]


WIDGET_AI_STATE = "ai"
WIDGET_AI_SUGGESTIONS = [
    {"label": "Book an appointment", "value": "I want to book an appointment", "type": "ai_prompt"},
    {"label": "Ask about services", "value": "What services are available?", "type": "ai_prompt"},
]


def _widget_ai_json(message, options=None):
    return JsonResponse({
        "state": WIDGET_AI_STATE,
        "message": message,
        "options": options or [],
        "next_action": "text_input",
    })


def _widget_ai_fallback_message(ai_settings):
    message = fallback_message_for(ai_settings)
    if "book" not in message.lower():
        message = f"{message} You can still use Book an Appointment to schedule a visit."
    return message


def _widget_ai_initial_message(clinic):
    return clinic.widget_welcome_message or "Welcome! How can we help you book an appointment today?"


def _widget_ai_message_from_action(action, value):
    text = (value or "").strip()
    if text:
        return text
    if action == "start_booking":
        return "I want to book an appointment"
    if action == "view_faqs":
        return "I have a question about the clinic"
    return ""


def _handle_widget_ai_chat(request, clinic, action, value):
    ai_settings, _ = ClinicAISettings.objects.get_or_create(clinic=clinic)

    if not ai_settings.is_ai_enabled:
        return _widget_ai_json(_widget_ai_fallback_message(ai_settings))

    if action == "init":
        return _widget_ai_json(_widget_ai_initial_message(clinic), WIDGET_AI_SUGGESTIONS)

    message = _widget_ai_message_from_action(action, value)
    if not message:
        return _widget_ai_json(_widget_ai_initial_message(clinic), WIDGET_AI_SUGGESTIONS)

    history = _widget_chat_history(request, clinic)
    if not request.session.session_key:
        request.session.create()

    try:
        reply = call_assistant_webhook(clinic, message, history, request.session.session_key)
    except (AssistantUnavailable, requests.RequestException, ValueError):
        reply = _widget_ai_fallback_message(ai_settings)

    history.extend([
        {"role": "user", "content": message},
        {"role": "assistant", "content": reply},
    ])
    _save_widget_chat_history(request, clinic, history)
    return _widget_ai_json(reply)


@require_POST
def chat_step(request, clinic_slug):
    clinic = _get_public_clinic_or_404(clinic_slug)
    action = request.POST.get("action", "")
    value = request.POST.get("value", "")

    return _handle_widget_ai_chat(request, clinic, action, value)
