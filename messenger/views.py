import json
import logging
from datetime import timedelta

import requests
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.utils.crypto import constant_time_compare
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from clinics.models import ClinicAISettings

from .ai_tools import (
    DEFAULT_AI_FALLBACK_MESSAGE,
    build_ai_context,
    build_widget_ai_context,
    book_confirmed_appointment,
    book_widget_confirmed_appointment,
    cancel_verified_appointment,
    cancel_widget_verified_appointment,
    check_availability,
    check_widget_availability,
    find_verified_appointment,
    find_widget_verified_appointment,
    get_or_create_clinic_ai_settings,
    match_services,
    match_widget_services,
    reschedule_verified_appointment,
    reschedule_widget_verified_appointment,
)
from .bot_engine import handle_message
from .messenger_api import verify_signature
from .models import MessengerConnection, MessengerProcessedMessage, MessengerSession


logger = logging.getLogger(__name__)
MESSENGER_QUICK_REPLY_LIMIT = 13
MESSENGER_QUICK_REPLY_TITLE_LIMIT = 20


def _verify_shared_secret(request):
    expected_secret = getattr(settings, "N8N_WEBHOOK_SECRET", "")
    provided_secret = request.headers.get("X-N8N-Webhook-Secret", "")
    return bool(expected_secret) and constant_time_compare(provided_secret, expected_secret)


def _verify_n8n_secret(request):
    return _verify_shared_secret(request)


def _verify_ai_tool_secret(request):
    return _verify_shared_secret(request)


def _json_body(request):
    try:
        return json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _meta_page_id_from_payload(data):
    if not isinstance(data, dict):
        return ""
    for entry in data.get("entry", []):
        if not isinstance(entry, dict):
            continue
        entry_id = entry.get("id")
        if entry_id:
            return str(entry_id)
        for messaging in entry.get("messaging", []):
            if not isinstance(messaging, dict):
                continue
            recipient = messaging.get("recipient", {})
            if not isinstance(recipient, dict):
                continue
            recipient_id = recipient.get("id")
            if recipient_id:
                return str(recipient_id)
    return ""


def _payload_matches_page(data, page_id):
    if not isinstance(data, dict) or not page_id:
        return False
    entries = data.get("entry", [])
    if not isinstance(entries, list):
        return False
    for entry in entries:
        if not isinstance(entry, dict):
            return False
        entry_id = str(entry.get("id") or "")
        if entry_id != page_id:
            return False
        messaging_items = entry.get("messaging", [])
        if not isinstance(messaging_items, list):
            return False
        for messaging in messaging_items:
            if not isinstance(messaging, dict):
                return False
            recipient = messaging.get("recipient", {})
            if not isinstance(recipient, dict):
                return False
            recipient_id = str(recipient.get("id") or "")
            if recipient_id != page_id:
                return False
    return True


def _payload_contains_message_identity(data, page_id, psid, message_id):
    if not isinstance(data, dict) or not page_id or not psid or not message_id:
        return False
    entries = data.get("entry", [])
    if not isinstance(entries, list):
        return False
    for entry in entries:
        if not isinstance(entry, dict) or str(entry.get("id") or "") != page_id:
            continue
        messaging_items = entry.get("messaging", [])
        if not isinstance(messaging_items, list):
            continue
        for messaging in messaging_items:
            if not isinstance(messaging, dict):
                continue
            sender = messaging.get("sender", {})
            if not isinstance(sender, dict) or str(sender.get("id") or "") != psid:
                continue
            if _meta_message_id(messaging) == message_id:
                return True
    return False


def _active_connection_for_page(page_id):
    if not page_id:
        return None
    try:
        return MessengerConnection.objects.select_related("clinic").get(
            page_id=page_id,
            page_access_token__gt="",
            is_active=True,
            clinic__is_active=True,
            clinic__requires_onboarding=False,
        )
    except (MessengerConnection.DoesNotExist, MessengerConnection.MultipleObjectsReturned):
        return None


def _uses_messenger_ai_mode(connection):
    if not connection:
        return False
    ai_settings = get_or_create_clinic_ai_settings(connection.clinic)
    return ai_settings.safe_messenger_response_mode == ClinicAISettings.MESSENGER_MODE_AI


def _messenger_ai_fallback_action(connection):
    ai_settings = get_or_create_clinic_ai_settings(connection.clinic)
    return {
        "type": "text",
        "text": ai_settings.fallback_message or DEFAULT_AI_FALLBACK_MESSAGE,
    }


def _meta_app_secret_for_connection(connection):
    if not connection:
        return ""
    return connection.app_secret or getattr(settings, "MESSENGER_APP_SECRET", "")


def _verified_messenger_connections_for_request(request):
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not signature:
        return {}

    verified = {}
    connections = MessengerConnection.objects.select_related("clinic").filter(
        is_active=True,
        clinic__is_active=True,
        clinic__requires_onboarding=False,
        page_id__gt="",
        page_access_token__gt="",
    )
    for connection in connections:
        if verify_signature(request.body, signature, _meta_app_secret_for_connection(connection)):
            verified[connection.page_id] = connection
    return verified


def _meta_message_id(messaging):
    message = messaging.get("message", {})
    if not isinstance(message, dict):
        message = {}
    postback = messaging.get("postback", {})
    if not isinstance(postback, dict):
        postback = {}
    return str(message.get("mid") or postback.get("mid") or "").strip()


def _mark_messenger_message_processed(connection, psid, message_id):
    if not message_id:
        return False
    _, created = MessengerProcessedMessage.objects.get_or_create(
        connection=connection,
        psid=psid,
        message_id=message_id,
    )
    return not created


def _ai_tool_response(request, handler):
    if not _verify_ai_tool_secret(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)
    data = _json_body(request)
    if data is None:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    try:
        return JsonResponse(handler(data), status=200)
    except (AttributeError, TypeError, ValueError):
        return JsonResponse({"error": "Invalid request data"}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def ai_context(request):
    return _ai_tool_response(request, lambda data: build_ai_context(data.get("page_id", "")))


@csrf_exempt
@require_http_methods(["POST"])
def ai_services(request):
    return _ai_tool_response(request, lambda data: match_services(data.get("page_id", ""), data.get("query", "")))


@csrf_exempt
@require_http_methods(["POST"])
def ai_availability(request):
    return _ai_tool_response(request, lambda data: check_availability(
        data.get("page_id", ""),
        data.get("service_id"),
        data.get("preferred_starts_at"),
        data.get("preferred_date"),
    ))


@csrf_exempt
@require_http_methods(["POST"])
def ai_book(request):
    return _ai_tool_response(request, lambda data: book_confirmed_appointment(
        data.get("page_id", ""),
        data.get("service_id"),
        data.get("starts_at"),
        data.get("full_name", ""),
        data.get("phone", ""),
        _normalize_confirmed(data.get("confirmed", False)),
        data.get("email", ""),
        data.get("reason", ""),
        data.get("psid", ""),
    ))


@csrf_exempt
@require_http_methods(["POST"])
def ai_appointment_lookup(request):
    return _ai_tool_response(request, lambda data: find_verified_appointment(
        data.get("page_id", ""),
        data.get("reference_code", ""),
        data.get("phone", ""),
    ))


@csrf_exempt
@require_http_methods(["POST"])
def ai_appointment_cancel(request):
    return _ai_tool_response(request, lambda data: cancel_verified_appointment(
        data.get("page_id", ""),
        data.get("reference_code", ""),
        data.get("phone", ""),
        _normalize_confirmed(data.get("confirmed", False)),
        data.get("reason", ""),
    ))


@csrf_exempt
@require_http_methods(["POST"])
def ai_appointment_reschedule(request):
    return _ai_tool_response(request, lambda data: reschedule_verified_appointment(
        data.get("page_id", ""),
        data.get("reference_code", ""),
        data.get("phone", ""),
        data.get("starts_at", ""),
        _normalize_confirmed(data.get("confirmed", False)),
    ))


@csrf_exempt
@require_http_methods(["POST"])
def meta_signature_verify(request):
    if not _verify_ai_tool_secret(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)
    data = _json_body(request)
    if data is None:
        return JsonResponse({"verified": False}, status=200)
    if not isinstance(data, dict):
        return JsonResponse({"error": "Invalid request data"}, status=400)

    page_id = data.get("page_id", "")
    raw_body = data.get("raw_body", "")
    signature = data.get("signature", "")
    psid = data.get("psid", "")
    message_id = data.get("message_id", "")
    if not all(isinstance(value, str) for value in [page_id, raw_body, signature]):
        return JsonResponse({"verified": False}, status=200)

    connection = _active_connection_for_page(page_id)
    app_secret = _meta_app_secret_for_connection(connection)
    signature_valid = bool(
        connection
        and app_secret
        and verify_signature(raw_body.encode("utf-8"), signature, app_secret)
    )
    verified = False
    raw_data = None
    if signature_valid:
        try:
            raw_data = json.loads(raw_body)
        except (json.JSONDecodeError, TypeError):
            raw_data = None
        verified = _payload_matches_page(raw_data, page_id)

    response = {"verified": verified}
    if isinstance(message_id, str) and message_id.strip():
        duplicate = False
        clean_psid = psid.strip() if isinstance(psid, str) else ""
        clean_message_id = message_id.strip()
        if verified and not _payload_contains_message_identity(raw_data, page_id, clean_psid, clean_message_id):
            verified = False
            response["verified"] = False
        elif verified and connection:
            duplicate = _mark_messenger_message_processed(connection, clean_psid, clean_message_id)
        response["duplicate"] = duplicate
    return JsonResponse(response, status=200)


@csrf_exempt
@require_http_methods(["POST"])
def widget_ai_context(request):
    return _ai_tool_response(request, lambda data: build_widget_ai_context(data.get("clinic_slug", "")))


@csrf_exempt
@require_http_methods(["POST"])
def widget_ai_services(request):
    return _ai_tool_response(request, lambda data: match_widget_services(data.get("clinic_slug", ""), data.get("query", "")))


@csrf_exempt
@require_http_methods(["POST"])
def widget_ai_availability(request):
    return _ai_tool_response(request, lambda data: check_widget_availability(
        data.get("clinic_slug", ""),
        data.get("service_id"),
        data.get("preferred_starts_at"),
        data.get("preferred_date"),
    ))


@csrf_exempt
@require_http_methods(["POST"])
def widget_ai_book(request):
    return _ai_tool_response(request, lambda data: book_widget_confirmed_appointment(
        data.get("clinic_slug", ""),
        data.get("service_id"),
        data.get("starts_at"),
        data.get("full_name", ""),
        data.get("phone", ""),
        _normalize_confirmed(data.get("confirmed", False)),
        data.get("email", ""),
        data.get("reason", ""),
    ))


@csrf_exempt
@require_http_methods(["POST"])
def widget_ai_appointment_lookup(request):
    return _ai_tool_response(request, lambda data: find_widget_verified_appointment(
        data.get("clinic_slug", ""),
        data.get("reference_code", ""),
        data.get("phone", ""),
    ))


@csrf_exempt
@require_http_methods(["POST"])
def widget_ai_appointment_cancel(request):
    return _ai_tool_response(request, lambda data: cancel_widget_verified_appointment(
        data.get("clinic_slug", ""),
        data.get("reference_code", ""),
        data.get("phone", ""),
        _normalize_confirmed(data.get("confirmed", False)),
        data.get("reason", ""),
    ))


@csrf_exempt
@require_http_methods(["POST"])
def widget_ai_appointment_reschedule(request):
    return _ai_tool_response(request, lambda data: reschedule_widget_verified_appointment(
        data.get("clinic_slug", ""),
        data.get("reference_code", ""),
        data.get("phone", ""),
        data.get("starts_at", ""),
        _normalize_confirmed(data.get("confirmed", False)),
    ))


def _normalize_confirmed(value):
    """Convert n8n string 'true' to Python bool True; reject all other values."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False


def _send_facebook_reply(page_token, psid, actions):
    """Send reply actions back to Facebook using Graph API."""
    if not actions or not page_token:
        return
    url = "https://graph.facebook.com/v18.0/me/messages"
    for action in actions:
        msg_payload = {"messaging_type": "RESPONSE", "recipient": {"id": psid}}
        if action["type"] == "text":
            msg_payload["message"] = {"text": action["text"]}
        elif action["type"] == "quick_replies":
            quick_replies = [
                {
                    "content_type": "text",
                    "title": str(opt.get("title", ""))[:MESSENGER_QUICK_REPLY_TITLE_LIMIT],
                    "payload": str(opt.get("payload", "")),
                }
                for opt in action.get("options", [])[:MESSENGER_QUICK_REPLY_LIMIT]
            ]
            msg_payload["message"] = {"text": action["text"]}
            if quick_replies:
                msg_payload["message"]["quick_replies"] = quick_replies
        else:
            continue
        try:
            response = requests.post(url, params={"access_token": page_token}, json=msg_payload, timeout=10)
            response.raise_for_status()
        except requests.RequestException:
            logger.error("Failed to send Messenger reply")


@csrf_exempt
@require_http_methods(["POST"])
def n8n_webhook(request):
    """Receive webhook calls from n8n and return reply actions + page token."""
    # Verify shared secret
    if not _verify_n8n_secret(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)

    data = _json_body(request)
    if data is None:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({"error": "Invalid request data"}, status=400)

    page_id = data.get("page_id", "")
    psid = data.get("psid", "")
    text = data.get("text", "")
    postback = data.get("postback", "")
    if not all(isinstance(value, str) for value in [page_id, psid, text, postback]):
        return JsonResponse({"error": "Invalid request data"}, status=400)

    if not page_id or not psid:
        return JsonResponse({"replies": [], "page_token": ""}, status=200)

    connection = _active_connection_for_page(page_id)
    if not connection:
        return JsonResponse({"replies": [], "page_token": ""}, status=200)
    if _uses_messenger_ai_mode(connection):
        return JsonResponse({
            "replies": [_messenger_ai_fallback_action(connection)],
            "page_token": connection.page_access_token,
        }, status=200)

    session, _ = MessengerSession.objects.get_or_create(
        connection=connection, psid=psid,
        defaults={"state": MessengerSession.STATE_GREETING, "data": {}}
    )

    # Timeout check
    timeout = timezone.now() - timedelta(minutes=getattr(settings, "MESSENGER_SESSION_TIMEOUT_MINUTES", 30))
    if session.last_activity_at < timeout:
        session.reset()

    actions = handle_message(session, text, postback)
    return JsonResponse({
        "replies": actions or [],
        "page_token": connection.page_access_token,
        "page_id": page_id,
        "psid": psid,
    }, status=200)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def webhook(request):
    # Legacy direct Facebook webhook - kept for backward compatibility
    # TODO: remove once n8n migration is complete
    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")
        expected_token = getattr(settings, "MESSENGER_VERIFY_TOKEN", "")
        if mode == "subscribe" and expected_token and constant_time_compare(token or "", expected_token):
            return HttpResponse(challenge)
        return HttpResponse(status=403)

    if request.method == "POST":
        verified_connections = _verified_messenger_connections_for_request(request)
        if not verified_connections:
            return HttpResponse(status=403)

        try:
            data = json.loads(request.body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return HttpResponse(status=400)

        if not isinstance(data, dict):
            return HttpResponse(status=403)
        entries = data.get("entry", [])
        if not isinstance(entries, list):
            return HttpResponse(status=403)

        for entry in entries:
            if not isinstance(entry, dict):
                return HttpResponse(status=403)
            entry_id = str(entry.get("id") or "")
            messaging_items = entry.get("messaging", [])
            if not isinstance(messaging_items, list):
                return HttpResponse(status=403)
            for messaging in messaging_items:
                if not isinstance(messaging, dict):
                    return HttpResponse(status=403)
                recipient = messaging.get("recipient", {})
                if not isinstance(recipient, dict):
                    return HttpResponse(status=403)
                recipient_id = str(recipient.get("id") or "")
                if not recipient_id or recipient_id != entry_id or recipient_id not in verified_connections:
                    return HttpResponse(status=403)

        for entry in entries:
            for messaging in entry.get("messaging", []):
                sender = messaging.get("sender", {})
                if not isinstance(sender, dict):
                    continue
                sender_id = sender.get("id")
                recipient = messaging.get("recipient", {})
                if not isinstance(recipient, dict):
                    continue
                recipient_id = recipient.get("id")
                message = messaging.get("message", {})
                if not isinstance(message, dict):
                    message = {}
                postback = messaging.get("postback", {})
                if not isinstance(postback, dict):
                    postback = {}
                text = message.get("text", "")
                if not isinstance(text, str):
                    text = str(text)
                quick_reply = message.get("quick_reply", {})
                if not isinstance(quick_reply, dict):
                    quick_reply = {}
                payload = quick_reply.get("payload") or postback.get("payload", "")
                payload_str = str(payload or "")

                if not sender_id or not recipient_id:
                    continue
                if not text.strip() and not payload_str:
                    continue

                connection = verified_connections.get(recipient_id)
                if not connection:
                    continue
                if _uses_messenger_ai_mode(connection):
                    continue
                message_id = _meta_message_id(messaging)
                if _mark_messenger_message_processed(connection, str(sender_id), message_id):
                    continue

                session, _ = MessengerSession.objects.get_or_create(
                    connection=connection, psid=sender_id,
                    defaults={"state": MessengerSession.STATE_GREETING, "data": {}}
                )

                # Timeout check
                timeout = timezone.now() - timedelta(minutes=getattr(settings, "MESSENGER_SESSION_TIMEOUT_MINUTES", 30))
                if session.last_activity_at < timeout:
                    session.reset()

                actions = handle_message(session, text, payload_str)
                _send_facebook_reply(connection.page_access_token, sender_id, actions)

        return HttpResponse(status=200)
