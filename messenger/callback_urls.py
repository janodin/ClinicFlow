from django.urls import reverse


MESSENGER_CALLBACK_URL_NAMES = {
    "messenger_webhook_url": "messenger:webhook",
    "meta_signature_verify_url": "messenger:meta_signature_verify",
    "messenger_ai_context_url": "messenger:ai_context",
    "ai_gateway_reply_url": "messenger:ai_gateway_reply",
    "messenger_ai_turn_register_url": "messenger:ai_turn_register",
    "messenger_ai_turn_claim_url": "messenger:ai_turn_claim",
    "messenger_ai_turn_send_reply_url": "messenger:ai_turn_send_reply",
    "messenger_n8n_webhook_url": "messenger:n8n_webhook",
}

WIDGET_CALLBACK_URL_NAMES = {
    "widget_ai_context_url": "messenger:widget_ai_context",
    "ai_gateway_reply_url": "messenger:ai_gateway_reply",
    "messenger_n8n_webhook_url": "messenger:n8n_webhook",
}


def build_n8n_callback_urls(request, channel):
    if channel == "messenger":
        names = MESSENGER_CALLBACK_URL_NAMES
    elif channel == "widget":
        names = WIDGET_CALLBACK_URL_NAMES
    else:
        raise ValueError("Unsupported n8n callback URL channel.")

    return {
        key: request.build_absolute_uri(reverse(url_name))
        for key, url_name in names.items()
    }
