import json
from datetime import timedelta

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .bot_engine import handle_message
from .models import MessengerConnection, MessengerSession


@csrf_exempt
@require_http_methods(["POST"])
def n8n_webhook(request):
    """Receive webhook calls from n8n and return reply actions."""
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
        return JsonResponse({"replies": []}, status=200)

    try:
        connection = MessengerConnection.objects.select_related("clinic").get(
            page_id=page_id, is_active=True
        )
    except MessengerConnection.DoesNotExist:
        return JsonResponse({"replies": []}, status=200)

    session, _ = MessengerSession.objects.get_or_create(
        connection=connection, psid=psid,
        defaults={"state": MessengerSession.STATE_GREETING, "data": {}}
    )

    # Timeout check
    timeout = timezone.now() - timedelta(minutes=getattr(settings, "MESSENGER_SESSION_TIMEOUT_MINUTES", 30))
    if session.last_activity_at < timeout:
        session.reset()

    actions = handle_message(session, text, postback)
    return JsonResponse({"replies": actions or []}, status=200)


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

                handle_message(session, text, payload_str)

        return HttpResponse(status=200)
