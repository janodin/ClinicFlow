import requests
from django.conf import settings

from messenger.defaults import DEFAULT_AI_FALLBACK_MESSAGE


class AssistantUnavailable(Exception):
    pass


def fallback_message_for(ai_settings):
    return ai_settings.fallback_message or DEFAULT_AI_FALLBACK_MESSAGE


def call_assistant_webhook(clinic, message, history, session_id, conversation_id=""):
    webhook_url = getattr(settings, "ASSISTANT_N8N_WEBHOOK_URL", "")
    if not webhook_url:
        raise AssistantUnavailable("Assistant n8n webhook URL is not configured.")

    secret = getattr(settings, "N8N_WEBHOOK_SECRET", "").strip()
    if not secret:
        raise AssistantUnavailable("Assistant n8n webhook secret is not configured.")
    headers = {"X-N8N-Webhook-Secret": secret}

    response = requests.post(
        webhook_url,
        json={
            "channel": "widget",
            "clinic_id": clinic.id,
            "clinic_slug": clinic.slug,
            "message": message,
            "history": history[-10:],
            "session_id": session_id,
            "conversation_id": conversation_id,
        },
        headers=headers,
        timeout=getattr(settings, "ASSISTANT_N8N_TIMEOUT_SECONDS", 12),
        allow_redirects=False,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise AssistantUnavailable("Assistant n8n webhook returned an invalid response.")
    reply_value = data.get("reply") or data.get("message") or ""
    if not isinstance(reply_value, str):
        raise AssistantUnavailable("Assistant n8n webhook returned an invalid reply.")
    reply = reply_value.strip()
    if not reply:
        raise AssistantUnavailable("Assistant n8n webhook returned an empty reply.")
    return reply[:getattr(settings, "WIDGET_AI_CHAT_MAX_REPLY_LENGTH", 1800)]
