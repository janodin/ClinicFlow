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

from .ai_tools import (
    build_ai_context,
    build_widget_ai_context,
    book_confirmed_appointment,
    book_widget_confirmed_appointment,
    check_availability,
    check_widget_availability,
    match_services,
    match_widget_services,
)
from .bot_engine import handle_message
from .messenger_api import verify_signature
from .models import MessengerConnection, MessengerSession


logger = logging.getLogger(__name__)


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


def _active_connection_for_page(page_id):
    if not page_id:
        return None
    try:
        return MessengerConnection.objects.select_related("clinic").get(
            page_id=page_id,
            is_active=True,
            clinic__is_active=True,
        )
    except (MessengerConnection.DoesNotExist, MessengerConnection.MultipleObjectsReturned):
        return None


def _verified_messenger_connections_for_request(request):
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not signature:
        return {}

    verified = {}
    connections = MessengerConnection.objects.select_related("clinic").filter(
        app_secret__gt="",
        is_active=True,
        clinic__is_active=True,
    )
    for connection in connections:
        if verify_signature(request.body, signature, connection.app_secret):
            verified[connection.page_id] = connection
    return verified


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
    if not all(isinstance(value, str) for value in [page_id, raw_body, signature]):
        return JsonResponse({"verified": False}, status=200)

    connection = _active_connection_for_page(page_id)
    signature_valid = bool(
        connection
        and connection.app_secret
        and verify_signature(raw_body.encode("utf-8"), signature, connection.app_secret)
    )
    verified = False
    if signature_valid:
        try:
            raw_data = json.loads(raw_body)
        except (json.JSONDecodeError, TypeError):
            raw_data = None
        verified = _payload_matches_page(raw_data, page_id)

    return JsonResponse({"verified": verified}, status=200)


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
        msg_payload = {"recipient": {"id": psid}}
        if action["type"] == "text":
            msg_payload["message"] = {"text": action["text"]}
        elif action["type"] == "quick_replies":
            quick_replies = [
                {"content_type": "text", "title": opt["title"], "payload": opt["payload"]}
                for opt in action.get("options", [])
            ]
            msg_payload["message"] = {"text": action["text"], "quick_replies": quick_replies}
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

    page_id = data.get("page_id", "")
    psid = data.get("psid", "")
    text = data.get("text", "")
    postback = data.get("postback", "")

    if not page_id or not psid:
        return JsonResponse({"replies": [], "page_token": ""}, status=200)

    connection = _active_connection_for_page(page_id)
    if not connection:
        return JsonResponse({"replies": [], "page_token": ""}, status=200)

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

        for entry in data.get("entry", []):
            entry_id = str(entry.get("id") or "")
            for messaging in entry.get("messaging", []):
                recipient = messaging.get("recipient", {})
                if not isinstance(recipient, dict):
                    return HttpResponse(status=403)
                recipient_id = str(recipient.get("id") or "")
                if not recipient_id or recipient_id != entry_id or recipient_id not in verified_connections:
                    return HttpResponse(status=403)

        for entry in data.get("entry", []):
            for messaging in entry.get("messaging", []):
                sender_id = messaging.get("sender", {}).get("id")
                recipient = messaging.get("recipient", {})
                if not isinstance(recipient, dict):
                    continue
                recipient_id = recipient.get("id")
                message = messaging.get("message", {})
                postback = messaging.get("postback", {})
                text = message.get("text", "")
                payload_str = postback.get("payload", "")

                if not sender_id or not recipient_id:
                    continue

                connection = verified_connections.get(recipient_id)
                if not connection:
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
