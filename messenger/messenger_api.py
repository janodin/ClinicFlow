import hmac
import hashlib
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)
META_API_URL = "https://graph.facebook.com/v18.0"


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    if not payload or not signature or not secret:
        return False
    if not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def fetch_page_profile(page_access_token):
    if not page_access_token:
        return None

    try:
        response = requests.get(
            f"{META_API_URL}/me",
            params={"fields": "id,name", "access_token": page_access_token},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        logger.warning("Failed to refresh Facebook Page profile")
        return None

    page_id = data.get("id")
    page_name = data.get("name")
    if not isinstance(page_id, str) or not isinstance(page_name, str):
        return None
    return {"id": page_id, "name": page_name}


def _send_message(connection, psid, payload):
    url = f"{META_API_URL}/me/messages"
    params = {"access_token": connection.page_access_token}
    body = {"recipient": {"id": psid}, "message": payload}
    try:
        resp = requests.post(url, params=params, json=body, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException:
        logger.error("Failed to send Messenger message")
        return None


def send_messages(connection, psid, actions):
    sent_any = False
    all_sent = True
    for action in actions:
        msg_type = action.get("type")
        if msg_type == "text":
            payload = {"text": action["text"]}
            sent_any = True
            all_sent = bool(_send_message(connection, psid, payload)) and all_sent
        elif msg_type == "quick_replies":
            payload = {
                "text": action["text"],
                "quick_replies": [
                    {
                        "content_type": "text",
                        "title": opt["title"],
                        "payload": opt["payload"],
                    }
                    for opt in action["options"]
                ],
            }
            sent_any = True
            all_sent = bool(_send_message(connection, psid, payload)) and all_sent
        elif msg_type == "template":
            payload = {
                "attachment": {
                    "type": "template",
                    "payload": {
                        "template_type": "button",
                        "text": action["text"],
                        "buttons": [
                            {
                                "type": "postback",
                                "title": btn["title"],
                                "payload": btn["payload"],
                            }
                            for btn in action.get("buttons", [])
                        ],
                    },
                }
            }
            sent_any = True
            all_sent = bool(_send_message(connection, psid, payload)) and all_sent
    return sent_any and all_sent
