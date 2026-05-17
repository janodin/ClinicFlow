import json
from datetime import timedelta

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .bot_engine import handle_message
from .messenger_api import send_messages, verify_signature
from .models import MessengerConnection, MessengerSession


@csrf_exempt
@require_http_methods(["GET", "POST"])
def webhook(request):
    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")
        if mode == "subscribe" and token == settings.MESSENGER_VERIFY_TOKEN:
            return HttpResponse(challenge)
        return HttpResponse(status=403)

    if request.method == "POST":
        signature = request.headers.get("X-Hub-Signature-256", "")
        payload = request.body
        if not verify_signature(payload, signature, settings.MESSENGER_APP_SECRET):
            return HttpResponse(status=403)

        try:
            data = json.loads(payload.decode("utf-8"))
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
                if actions:
                    send_messages(connection, sender_id, actions)

        return HttpResponse(status=200)
