import json
from datetime import timedelta

import requests
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .bot_engine import handle_message
from .models import MessengerConnection, MessengerSession


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
            requests.post(url, params={"access_token": page_token}, json=msg_payload, timeout=10)
        except Exception:
            pass


@csrf_exempt
@require_http_methods(["POST"])
def n8n_webhook(request):
    """Receive webhook calls from n8n and return reply actions + page token."""
    # Verify shared secret
    expected_secret = getattr(settings, "N8N_WEBHOOK_SECRET", "")
    provided_secret = request.headers.get("X-N8N-Webhook-Secret", "")
    if expected_secret and provided_secret != expected_secret:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    try:
        data = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    page_id = data.get("page_id", "")
    psid = data.get("psid", "")
    text = data.get("text", "")
    postback = data.get("postback", "")

    if not page_id or not psid:
        return JsonResponse({"replies": [], "page_token": ""}, status=200)

    try:
        connection = MessengerConnection.objects.select_related("clinic").get(
            page_id=page_id, is_active=True
        )
    except MessengerConnection.DoesNotExist:
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
        if mode == "subscribe" and token == settings.MESSENGER_VERIFY_TOKEN:
            return HttpResponse(challenge)
        return HttpResponse(status=403)

    if request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return HttpResponse(status=400)

        for entry in data.get("entry", []):
            for messaging in entry.get("messaging", []):
                sender_id = messaging.get("sender", {}).get("id")
                recipient_id = messaging.get("recipient", {}).get("id")
                message = messaging.get("message", {})
                postback = messaging.get("postback", {})
                text = message.get("text", "")
                payload_str = postback.get("payload", "")

                if not sender_id or not recipient_id:
                    continue

                try:
                    connection = MessengerConnection.objects.select_related("clinic").get(
                        page_id=recipient_id, is_active=True
                    )
                except MessengerConnection.DoesNotExist:
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
