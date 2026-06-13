import hashlib
import json
import logging
import uuid
from datetime import timedelta

import requests
from django.conf import settings
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.utils.crypto import constant_time_compare
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from clinics.models import ClinicAISettings

from .ai_gateway import build_gateway_reply
from .ai_tools import (
    DEFAULT_AI_FALLBACK_MESSAGE,
    build_ai_context,
    build_widget_ai_context,
    book_confirmed_appointment,
    cancel_verified_appointment,
    check_availability,
    check_widget_availability,
    find_verified_appointment,
    find_widget_verified_appointment,
    get_or_create_clinic_ai_settings,
    match_services,
    match_widget_services,
    reschedule_verified_appointment,
)
from .bot_engine import handle_message
from .messenger_api import verify_signature
from .models import (
    MessengerAITurn,
    MessengerConnection,
    MessengerConversation,
    MessengerInboundMessage,
    MessengerOutboundMessage,
    MessengerProcessedMessage,
    MessengerSession,
)


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


def _payload_contains_sender(data, page_id, psid):
    if not isinstance(data, dict) or not page_id or not psid:
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
            if isinstance(sender, dict) and str(sender.get("id") or "") == psid:
                return True
    return False


def _payload_message_for_identity(data, page_id, psid, message_id):
    if not isinstance(data, dict) or not page_id or not psid:
        return None
    entries = data.get("entry", [])
    if not isinstance(entries, list):
        return None
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
            if message_id and _meta_message_id(messaging) != message_id:
                continue
            message = messaging.get("message", {})
            if not isinstance(message, dict):
                message = {}
            postback = messaging.get("postback", {})
            if not isinstance(postback, dict):
                postback = {}
            text = str(message.get("text") or "").strip()
            payload = str(postback.get("payload") or "").strip()
            if text or payload:
                return {"message": text, "postback": payload}
    return None


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


def _stable_messenger_fallback_message_id(page_id, psid, message, postback):
    payload = json.dumps(
        {
            "page_id": page_id,
            "psid": psid,
            "message": message,
            "postback": postback,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return "fallback:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _stable_json_hash(value):
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _mark_messenger_message_processed(connection, psid, message_id):
    if not message_id:
        return False
    _, created = MessengerProcessedMessage.objects.get_or_create(
        connection=connection,
        psid=psid,
        message_id=message_id,
    )
    return not created


def _clean_turn_sequence(value):
    try:
        sequence = int(value)
    except (TypeError, ValueError):
        return 0
    return sequence if sequence > 0 else 0


def _locked_messenger_conversation(connection, psid):
    conversation, _ = MessengerConversation.objects.get_or_create(
        connection=connection,
        psid=psid,
        defaults={"history": []},
    )
    return MessengerConversation.objects.select_for_update().get(pk=conversation.pk)


def _messenger_ai_conversation_timeout():
    try:
        minutes = int(getattr(settings, "MESSENGER_SESSION_TIMEOUT_MINUTES", 30))
    except (TypeError, ValueError):
        minutes = 30
    return timedelta(minutes=minutes)


def _messenger_ai_last_user_activity_at(conversation):
    return (
        conversation.inbound_messages.order_by("-created_at")
        .values_list("created_at", flat=True)
        .first()
        or conversation.updated_at
    )


def _expire_stale_messenger_ai_conversation(conversation):
    timeout = _messenger_ai_conversation_timeout()
    if _messenger_ai_last_user_activity_at(conversation) >= timezone.now() - timeout:
        return
    conversation.history = []
    conversation.completed_sequence = conversation.last_sequence
    conversation.active_turn_token = ""
    conversation.active_input_sequence = 0
    conversation.save(update_fields=[
        "history",
        "completed_sequence",
        "active_turn_token",
        "active_input_sequence",
        "updated_at",
    ])


def _serialize_turn_message(message):
    return {
        "sequence": message.sequence,
        "text": message.text,
        "postback": message.postback,
    }


def _pending_turn_messages(conversation, input_sequence):
    return list(
        conversation.inbound_messages.filter(
            sequence__gt=conversation.completed_sequence,
            sequence__lte=input_sequence,
        ).order_by("sequence")
    )


def _turn_user_content(messages):
    return "\n".join(
        (message.text or message.postback or "").strip()
        for message in messages
        if (message.text or message.postback or "").strip()
    )


def _compose_turn_prompt(conversation, messages):
    lines = []
    lines.append("New Messenger messages in order:")
    for message in messages:
        content = (message.text or message.postback or "").strip()
        if content:
            lines.append(f"- {content}")
    lines.append("")
    lines.append("Treat the new messages as one user turn. If later messages correct or complete earlier messages, use the latest complete intent.")
    return "\n".join(lines).strip()


def _turn_payload(conversation, turn):
    messages = _pending_turn_messages(conversation, turn.input_sequence)
    history = conversation.history[-16:] if isinstance(conversation.history, list) else []
    return {
        "turn_token": turn.token,
        "input_sequence": turn.input_sequence,
        "messages": [_serialize_turn_message(message) for message in messages],
        "message": _compose_turn_prompt(conversation, messages),
        "history": history,
    }


def _validate_locked_messenger_turn(connection, psid, turn_token, input_sequence):
    clean_turn_token = str(turn_token or "").strip()
    clean_input_sequence = _clean_turn_sequence(input_sequence)
    if not clean_turn_token and not clean_input_sequence:
        return True
    clean_psid = str(psid or "").strip()
    if not connection or not clean_psid or not clean_turn_token or not clean_input_sequence:
        return False
    conversation = MessengerConversation.objects.select_for_update().filter(
        connection=connection,
        psid=clean_psid,
    ).first()
    if not conversation:
        return False
    return (
        conversation.active_turn_token == clean_turn_token
        and conversation.active_input_sequence == clean_input_sequence
        and conversation.last_sequence <= clean_input_sequence
    )


def _messenger_turn_is_current(data):
    page_id = str(data.get("page_id", "")).strip()
    psid = str(data.get("psid", "")).strip()
    turn_token = str(data.get("turn_token", "")).strip()
    input_sequence = _clean_turn_sequence(data.get("input_sequence"))
    if not page_id or not psid or not turn_token or not input_sequence:
        return False
    connection = _active_connection_for_page(page_id)
    if not connection:
        return False
    with transaction.atomic():
        return _validate_locked_messenger_turn(connection, psid, turn_token, input_sequence)


def _messenger_turn_context(data):
    if not _messenger_turn_is_current(data):
        return {"found": False}
    return build_ai_context(data.get("page_id", ""))


def _messenger_gateway_reply(data):
    if str(data.get("channel", "")).strip().lower() == "messenger" and not _messenger_turn_is_current(data):
        return {"reply": DEFAULT_AI_FALLBACK_MESSAGE, "fallback": True, "error": MESSENGER_AI_MUTATION_TURN_ERROR}
    return build_gateway_reply(data)


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


MESSENGER_AI_MUTATION_TURN_ERROR = "Messenger appointment mutation requires current turn metadata."
WIDGET_AI_MUTATION_GATEWAY_ERROR = "Widget AI appointment mutations must use the AI gateway."


def _has_messenger_mutation_turn_binding(data):
    return bool(
        str(data.get("page_id", "")).strip()
        and str(data.get("psid", "")).strip()
        and str(data.get("turn_token", "")).strip()
        and _clean_turn_sequence(data.get("input_sequence"))
    )


def _missing_messenger_turn_response(result_key):
    return {result_key: False, "error": MESSENGER_AI_MUTATION_TURN_ERROR}


def _legacy_widget_mutation_response(result_key):
    return {result_key: False, "error": WIDGET_AI_MUTATION_GATEWAY_ERROR}


def _ai_book_handler(data):
    if not _has_messenger_mutation_turn_binding(data):
        return _missing_messenger_turn_response("created")
    return book_confirmed_appointment(
        data.get("page_id", ""),
        data.get("service_id"),
        data.get("starts_at"),
        data.get("full_name", ""),
        data.get("phone", ""),
        _normalize_confirmed(data.get("confirmed", False)),
        data.get("email", ""),
        data.get("reason", ""),
        data.get("psid", ""),
        data.get("turn_token", ""),
        data.get("input_sequence"),
    )


def _ai_cancel_handler(data):
    if not _has_messenger_mutation_turn_binding(data):
        return _missing_messenger_turn_response("cancelled")
    return cancel_verified_appointment(
        data.get("page_id", ""),
        data.get("reference_code", ""),
        data.get("phone", ""),
        _normalize_confirmed(data.get("confirmed", False)),
        data.get("reason", ""),
        data.get("psid", ""),
        data.get("turn_token", ""),
        data.get("input_sequence"),
    )


def _ai_reschedule_handler(data):
    if not _has_messenger_mutation_turn_binding(data):
        return _missing_messenger_turn_response("rescheduled")
    return reschedule_verified_appointment(
        data.get("page_id", ""),
        data.get("reference_code", ""),
        data.get("phone", ""),
        data.get("starts_at", ""),
        _normalize_confirmed(data.get("confirmed", False)),
        data.get("psid", ""),
        data.get("turn_token", ""),
        data.get("input_sequence"),
    )


@csrf_exempt
@require_http_methods(["POST"])
def ai_context(request):
    return _ai_tool_response(request, _messenger_turn_context)


@csrf_exempt
@require_http_methods(["POST"])
def ai_gateway_reply(request):
    return _ai_tool_response(request, _messenger_gateway_reply)


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
    return _ai_tool_response(request, _ai_book_handler)


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
    return _ai_tool_response(request, _ai_cancel_handler)


@csrf_exempt
@require_http_methods(["POST"])
def ai_appointment_reschedule(request):
    return _ai_tool_response(request, _ai_reschedule_handler)


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
        clean_psid = psid.strip() if isinstance(psid, str) else ""
        clean_message_id = message_id.strip()
        duplicate = False
        if verified and not _payload_contains_message_identity(raw_data, page_id, clean_psid, clean_message_id):
            verified = False
            response["verified"] = False
        if verified and clean_psid:
            duplicate = MessengerInboundMessage.objects.filter(
                conversation__connection=connection,
                conversation__psid=clean_psid,
                message_id=clean_message_id,
            ).exists()
        response["duplicate"] = duplicate
    return JsonResponse(response, status=200)


@csrf_exempt
@require_http_methods(["POST"])
def ai_turn_register(request):
    if not _verify_ai_tool_secret(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)
    data = _json_body(request)
    if data is None:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({"error": "Invalid request data"}, status=400)

    page_id = data.get("page_id", "")
    psid = data.get("psid", "")
    message_id = data.get("message_id", "")
    message = data.get("message", "")
    postback = data.get("postback", "")
    raw_body = data.get("raw_body", "")
    signature = data.get("signature", "")
    if not all(isinstance(value, str) for value in [page_id, psid, message_id, message, postback, raw_body, signature]):
        return JsonResponse({"error": "Invalid request data"}, status=400)
    clean_page_id = page_id.strip()
    clean_psid = psid.strip()
    clean_message_id = message_id.strip()
    clean_message = message.strip()
    clean_postback = postback.strip()
    if not clean_page_id or not clean_psid or (not clean_message and not clean_postback):
        return JsonResponse({
            "registered": False,
            "duplicate": False,
            "process_now": False,
            "superseded_previous": False,
        }, status=200)

    connection = _active_connection_for_page(clean_page_id)
    if not connection:
        return JsonResponse({
            "registered": False,
            "duplicate": False,
            "process_now": False,
            "superseded_previous": False,
        }, status=200)
    app_secret = _meta_app_secret_for_connection(connection)
    raw_data = None
    signature_valid = bool(
        raw_body.strip()
        and signature.strip()
        and app_secret
        and verify_signature(raw_body.encode("utf-8"), signature, app_secret)
    )
    if signature_valid:
        try:
            raw_data = json.loads(raw_body)
        except (json.JSONDecodeError, TypeError):
            raw_data = None
    signed_message = _payload_message_for_identity(raw_data, clean_page_id, clean_psid, clean_message_id)
    identity_valid = signed_message is not None
    if not (
        signature_valid
        and _payload_matches_page(raw_data, clean_page_id)
        and identity_valid
    ):
        return JsonResponse({
            "registered": False,
            "duplicate": False,
            "process_now": False,
            "superseded_previous": False,
        }, status=200)
    clean_message = signed_message["message"]
    clean_postback = signed_message["postback"]

    with transaction.atomic():
        conversation = _locked_messenger_conversation(connection, clean_psid)
        _expire_stale_messenger_ai_conversation(conversation)
        inbound_message_id = clean_message_id or _stable_messenger_fallback_message_id(
            clean_page_id,
            clean_psid,
            clean_message,
            clean_postback,
        )
        if MessengerInboundMessage.objects.filter(
            conversation=conversation,
            message_id=inbound_message_id,
        ).exists():
            return JsonResponse({
                "registered": False,
                "duplicate": True,
                "process_now": False,
                "superseded_previous": False,
            }, status=200)

        next_sequence = conversation.last_sequence + 1
        MessengerInboundMessage.objects.create(
            conversation=conversation,
            message_id=inbound_message_id,
            sequence=next_sequence,
            text=clean_message,
            postback=clean_postback,
        )
        active_turn = None
        if conversation.active_turn_token:
            active_turn = MessengerAITurn.objects.select_for_update().filter(
                conversation=conversation,
                token=conversation.active_turn_token,
            ).first()
        superseded_previous = bool(
            active_turn
            and active_turn.status in [MessengerAITurn.STATUS_ACTIVE, MessengerAITurn.STATUS_CLAIMED]
        )
        if superseded_previous:
            active_turn.status = MessengerAITurn.STATUS_SUPERSEDED
            active_turn.save(update_fields=["status", "updated_at"])

        turn = MessengerAITurn.objects.create(
            conversation=conversation,
            token=uuid.uuid4().hex,
            input_sequence=next_sequence,
        )
        conversation.last_sequence = next_sequence
        conversation.active_turn_token = turn.token
        conversation.active_input_sequence = next_sequence
        conversation.save(update_fields=[
            "last_sequence",
            "active_turn_token",
            "active_input_sequence",
            "updated_at",
        ])
        payload = _turn_payload(conversation, turn)

    return JsonResponse({
        "registered": True,
        "duplicate": False,
        "process_now": True,
        "superseded_previous": superseded_previous,
        **payload,
    }, status=200)


@csrf_exempt
@require_http_methods(["POST"])
def ai_turn_claim(request):
    if not _verify_ai_tool_secret(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)
    data = _json_body(request)
    if data is None:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({"error": "Invalid request data"}, status=400)
    page_id = data.get("page_id", "")
    psid = data.get("psid", "")
    turn_token = data.get("turn_token", "")
    if not all(isinstance(value, str) for value in [page_id, psid, turn_token]):
        return JsonResponse({"error": "Invalid request data"}, status=400)

    connection = _active_connection_for_page(page_id.strip())
    if not connection:
        return JsonResponse({"claimed": False, "stale": True, "has_pending": False}, status=200)

    with transaction.atomic():
        conversation = MessengerConversation.objects.select_for_update().filter(
            connection=connection,
            psid=psid.strip(),
        ).first()
        if not conversation:
            return JsonResponse({"claimed": False, "stale": True, "has_pending": False}, status=200)
        if conversation.active_turn_token != turn_token.strip():
            return JsonResponse({
                "claimed": False,
                "stale": True,
                "has_pending": conversation.last_sequence > conversation.completed_sequence,
            }, status=200)
        turn = MessengerAITurn.objects.select_for_update().filter(conversation=conversation, token=turn_token.strip()).first()
        if not turn:
            return JsonResponse({
                "claimed": False,
                "stale": True,
                "has_pending": conversation.last_sequence > conversation.completed_sequence,
            }, status=200)
        if turn.status == MessengerAITurn.STATUS_CLAIMED:
            return JsonResponse({"claimed": False, "stale": False, "has_pending": False}, status=200)
        if turn.status != MessengerAITurn.STATUS_ACTIVE:
            return JsonResponse({
                "claimed": False,
                "stale": turn.status in [MessengerAITurn.STATUS_SUPERSEDED, MessengerAITurn.STATUS_STALE],
                "has_pending": conversation.last_sequence > conversation.completed_sequence,
            }, status=200)
        turn.status = MessengerAITurn.STATUS_CLAIMED
        turn.save(update_fields=["status", "updated_at"])
        payload = _turn_payload(conversation, turn)

    return JsonResponse({"claimed": True, "stale": False, **payload}, status=200)


@csrf_exempt
@require_http_methods(["POST"])
def ai_turn_complete(request):
    if not _verify_ai_tool_secret(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)
    data = _json_body(request)
    if data is None:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({"error": "Invalid request data"}, status=400)
    page_id = data.get("page_id", "")
    psid = data.get("psid", "")
    turn_token = data.get("turn_token", "")
    reply_text = data.get("reply_text", "")
    input_sequence = _clean_turn_sequence(data.get("input_sequence"))
    if not all(isinstance(value, str) for value in [page_id, psid, turn_token, reply_text]) or not input_sequence:
        return JsonResponse({"error": "Invalid request data"}, status=400)

    connection = _active_connection_for_page(page_id.strip())
    if not connection:
        return JsonResponse({"send_reply": False, "stale": True, "has_pending": False}, status=200)

    with transaction.atomic():
        conversation = MessengerConversation.objects.select_for_update().filter(
            connection=connection,
            psid=psid.strip(),
        ).first()
        if not conversation:
            return JsonResponse({"send_reply": False, "stale": True, "has_pending": False}, status=200)
        turn = MessengerAITurn.objects.filter(conversation=conversation, token=turn_token.strip()).first()
        is_current = bool(
            turn
            and turn.status in [MessengerAITurn.STATUS_ACTIVE, MessengerAITurn.STATUS_CLAIMED]
            and conversation.active_turn_token == turn_token.strip()
            and conversation.active_input_sequence == input_sequence
            and turn.input_sequence == input_sequence
        )
        if not is_current:
            if turn and turn.status in [MessengerAITurn.STATUS_ACTIVE, MessengerAITurn.STATUS_CLAIMED]:
                turn.status = MessengerAITurn.STATUS_STALE
                turn.save(update_fields=["status", "updated_at"])
            return JsonResponse({
                "send_reply": False,
                "stale": True,
                "has_pending": conversation.last_sequence > conversation.completed_sequence,
            }, status=200)

        messages = _pending_turn_messages(conversation, input_sequence)
        clean_reply = reply_text.strip()
        history = conversation.history if isinstance(conversation.history, list) else []
        user_content = _turn_user_content(messages)
        if user_content and clean_reply:
            history = (history + [
                {"role": "user", "content": user_content},
                {"role": "assistant", "content": clean_reply},
            ])[-16:]
        conversation.history = history
        conversation.completed_sequence = input_sequence
        conversation.active_turn_token = ""
        conversation.active_input_sequence = 0
        conversation.save(update_fields=[
            "history",
            "completed_sequence",
            "active_turn_token",
            "active_input_sequence",
            "updated_at",
        ])
        turn.status = MessengerAITurn.STATUS_COMPLETED
        turn.reply_text = clean_reply
        turn.save(update_fields=["status", "reply_text", "updated_at"])
        has_pending = conversation.last_sequence > conversation.completed_sequence

    return JsonResponse({"send_reply": True, "stale": False, "has_pending": has_pending}, status=200)


@csrf_exempt
@require_http_methods(["POST"])
def ai_turn_authorize_send(request):
    if not _verify_ai_tool_secret(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)
    data = _json_body(request)
    if data is None:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({"error": "Invalid request data"}, status=400)
    page_id = data.get("page_id", "")
    psid = data.get("psid", "")
    turn_token = data.get("turn_token", "")
    input_sequence = _clean_turn_sequence(data.get("input_sequence"))
    if not all(isinstance(value, str) for value in [page_id, psid, turn_token]) or not input_sequence:
        return JsonResponse({"error": "Invalid request data"}, status=400)

    connection = _active_connection_for_page(page_id.strip())
    if not connection:
        return JsonResponse({"send_reply": False, "stale": True, "has_pending": False}, status=200)

    conversation = MessengerConversation.objects.filter(
        connection=connection,
        psid=psid.strip(),
    ).first()
    if not conversation:
        return JsonResponse({"send_reply": False, "stale": True, "has_pending": False}, status=200)

    turn = MessengerAITurn.objects.filter(conversation=conversation, token=turn_token.strip()).first()
    is_send_current = bool(
        turn
        and turn.status == MessengerAITurn.STATUS_COMPLETED
        and turn.input_sequence == input_sequence
        and conversation.completed_sequence == input_sequence
        and conversation.last_sequence == input_sequence
    )
    if not is_send_current:
        return JsonResponse({
            "send_reply": False,
            "stale": True,
            "has_pending": conversation.last_sequence > conversation.completed_sequence,
        }, status=200)

    return JsonResponse({"send_reply": True, "stale": False, "has_pending": False}, status=200)


def _facebook_body_for_turn(psid, reply_text, facebook_body):
    if isinstance(facebook_body, dict):
        message = facebook_body.get("message")
        if not isinstance(message, dict):
            return None
    else:
        clean_reply = str(reply_text or "").strip()
        if not clean_reply:
            return None
        message = {"text": clean_reply}
    return {
        "messaging_type": "RESPONSE",
        "recipient": {"id": psid},
        "message": message,
    }


def _facebook_bodies_for_turn(psid, reply_text, facebook_body, facebook_bodies=None):
    if facebook_bodies is not None:
        if not isinstance(facebook_bodies, list):
            return None
        if facebook_bodies:
            bodies = []
            for body in facebook_bodies:
                prepared_body = _facebook_body_for_turn(psid, "", body)
                if prepared_body is None:
                    return None
                bodies.append(prepared_body)
            return bodies

    prepared_body = _facebook_body_for_turn(psid, reply_text, facebook_body)
    if prepared_body is None:
        return None
    return [prepared_body]


def _record_messenger_outbound_messages(turn, facebook_bodies):
    outbound_messages = []
    for body_index, body in enumerate(facebook_bodies):
        body_hash = _stable_json_hash(body)
        outbound, created = MessengerOutboundMessage.objects.select_for_update().get_or_create(
            turn=turn,
            body_index=body_index,
            defaults={
                "body_hash": body_hash,
                "body": body,
                "status": MessengerOutboundMessage.STATUS_PENDING,
            },
        )
        if not created and outbound.status in [
            MessengerOutboundMessage.STATUS_PENDING,
            MessengerOutboundMessage.STATUS_FAILED,
        ] and (
            outbound.body_hash != body_hash or outbound.body != body
        ):
            outbound.body_hash = body_hash
            outbound.body = body
            outbound.status = MessengerOutboundMessage.STATUS_PENDING
            outbound.error = ""
            outbound.save(update_fields=["body_hash", "body", "status", "error", "updated_at"])
        outbound_messages.append(outbound)
    return outbound_messages


def _send_reply_payload(send_reply, stale, has_pending, sent, error=""):
    payload = {
        "send_reply": send_reply,
        "stale": stale,
        "has_pending": has_pending,
        "sent": sent,
    }
    if error:
        payload["error"] = error
    return payload


def _complete_messenger_turn_after_send(connection, clean_psid, clean_turn_token, input_sequence, reply_text):
    with transaction.atomic():
        conversation = MessengerConversation.objects.select_for_update().filter(
            connection=connection,
            psid=clean_psid,
        ).first()
        if not conversation:
            return _send_reply_payload(False, True, False, False)
        turn = MessengerAITurn.objects.select_for_update().filter(
            conversation=conversation,
            token=clean_turn_token,
        ).first()
        if not turn or turn.input_sequence != input_sequence or turn.status in [
            MessengerAITurn.STATUS_SUPERSEDED,
            MessengerAITurn.STATUS_STALE,
        ]:
            return _send_reply_payload(
                False,
                True,
                conversation.last_sequence > conversation.completed_sequence,
                False,
            )

        clean_reply = reply_text.strip()
        should_record_reply = turn.status != MessengerAITurn.STATUS_COMPLETED
        if should_record_reply and conversation.completed_sequence < input_sequence:
            messages = _pending_turn_messages(conversation, input_sequence)
        elif should_record_reply:
            messages = list(conversation.inbound_messages.filter(sequence=input_sequence).order_by("sequence"))
        else:
            messages = []
        if should_record_reply:
            history = conversation.history if isinstance(conversation.history, list) else []
            user_content = _turn_user_content(messages)
            if user_content and clean_reply:
                history = (history + [
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": clean_reply},
                ])[-16:]
            conversation.history = history
        if conversation.completed_sequence < input_sequence:
            conversation.completed_sequence = input_sequence
        if conversation.active_turn_token == clean_turn_token:
            conversation.active_turn_token = ""
            conversation.active_input_sequence = 0
        conversation.save(update_fields=[
            "history",
            "completed_sequence",
            "active_turn_token",
            "active_input_sequence",
            "updated_at",
        ])
        turn.status = MessengerAITurn.STATUS_COMPLETED
        turn.reply_text = clean_reply
        turn.save(update_fields=["status", "reply_text", "updated_at"])
        has_pending = conversation.last_sequence > conversation.completed_sequence

    return _send_reply_payload(True, False, has_pending, True)


def _reset_failed_messenger_turn_after_send(connection, clean_psid, clean_turn_token, input_sequence):
    with transaction.atomic():
        conversation = MessengerConversation.objects.select_for_update().filter(
            connection=connection,
            psid=clean_psid,
        ).first()
        if not conversation:
            return False
        turn = MessengerAITurn.objects.select_for_update().filter(
            conversation=conversation,
            token=clean_turn_token,
            input_sequence=input_sequence,
        ).first()
        if turn and turn.status == MessengerAITurn.STATUS_SENDING:
            if (
                conversation.active_turn_token == clean_turn_token
                and conversation.active_input_sequence == input_sequence
            ):
                turn.status = MessengerAITurn.STATUS_ACTIVE
            else:
                turn.status = MessengerAITurn.STATUS_STALE
            turn.save(update_fields=["status", "updated_at"])
        return conversation.last_sequence > input_sequence


@csrf_exempt
@require_http_methods(["POST"])
def ai_turn_send_reply(request):
    if not _verify_ai_tool_secret(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)
    data = _json_body(request)
    if data is None:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({"error": "Invalid request data"}, status=400)
    page_id = data.get("page_id", "")
    psid = data.get("psid", "")
    turn_token = data.get("turn_token", "")
    reply_text = data.get("reply_text", "")
    input_sequence = _clean_turn_sequence(data.get("input_sequence"))
    if not all(isinstance(value, str) for value in [page_id, psid, turn_token, reply_text]) or not input_sequence:
        return JsonResponse({"error": "Invalid request data"}, status=400)
    clean_psid = psid.strip()
    facebook_bodies = _facebook_bodies_for_turn(
        clean_psid,
        reply_text,
        data.get("facebook_body"),
        data.get("facebook_bodies"),
    )
    if not clean_psid or facebook_bodies is None:
        return JsonResponse({"error": "Invalid request data"}, status=400)

    connection = _active_connection_for_page(page_id.strip())
    if not connection:
        return JsonResponse({"send_reply": False, "stale": True, "has_pending": False, "sent": False}, status=200)

    clean_turn_token = turn_token.strip()
    complete_after_claim = ""
    with transaction.atomic():
        conversation = MessengerConversation.objects.select_for_update().filter(
            connection=connection,
            psid=clean_psid,
        ).first()
        if not conversation:
            return JsonResponse({"send_reply": False, "stale": True, "has_pending": False, "sent": False}, status=200)
        turn = MessengerAITurn.objects.select_for_update().filter(conversation=conversation, token=clean_turn_token).first()
        is_completed_retry = bool(
            turn
            and turn.status == MessengerAITurn.STATUS_COMPLETED
            and turn.input_sequence == input_sequence
            and conversation.completed_sequence >= input_sequence
        )
        if is_completed_retry:
            has_pending = conversation.last_sequence > conversation.completed_sequence
            if MessengerOutboundMessage.objects.filter(
                turn=turn,
                body_index__lt=len(facebook_bodies),
                status=MessengerOutboundMessage.STATUS_UNKNOWN,
            ).exists():
                return JsonResponse(_send_reply_payload(
                    False,
                    False,
                    has_pending,
                    False,
                    "facebook_send_status_unknown",
                ), status=200)
            return JsonResponse(_send_reply_payload(True, False, has_pending, True), status=200)
        if turn and turn.status == MessengerAITurn.STATUS_SENDING and turn.input_sequence == input_sequence:
            sending_exists = MessengerOutboundMessage.objects.filter(
                turn=turn,
                body_index__lt=len(facebook_bodies),
                status=MessengerOutboundMessage.STATUS_SENDING,
            ).exists()
            if sending_exists:
                return JsonResponse(_send_reply_payload(
                    False,
                    False,
                    conversation.last_sequence > input_sequence,
                    False,
                    "facebook_send_in_progress",
                ), status=200)
            if MessengerOutboundMessage.objects.filter(
                turn=turn,
                body_index__lt=len(facebook_bodies),
                status=MessengerOutboundMessage.STATUS_UNKNOWN,
            ).exists():
                complete_after_claim = "unknown"
            elif not MessengerOutboundMessage.objects.filter(
                turn=turn,
                body_index__lt=len(facebook_bodies),
            ).exclude(status=MessengerOutboundMessage.STATUS_SENT).exists():
                complete_after_claim = "sent"
        is_current = bool(
            turn
            and turn.status in [MessengerAITurn.STATUS_ACTIVE, MessengerAITurn.STATUS_CLAIMED]
            and conversation.active_turn_token == clean_turn_token
            and conversation.active_input_sequence == input_sequence
            and turn.input_sequence == input_sequence
            and conversation.last_sequence == input_sequence
        )
        if not is_current and not complete_after_claim:
            if turn and turn.status in [MessengerAITurn.STATUS_ACTIVE, MessengerAITurn.STATUS_CLAIMED]:
                turn.status = MessengerAITurn.STATUS_STALE
                turn.save(update_fields=["status", "updated_at"])
            return JsonResponse(_send_reply_payload(
                False,
                True,
                conversation.last_sequence > conversation.completed_sequence,
                False,
            ), status=200)

        outbound_ids_to_send = []
        if is_current:
            outbound_messages = _record_messenger_outbound_messages(turn, facebook_bodies)
            if any(outbound.status == MessengerOutboundMessage.STATUS_SENDING for outbound in outbound_messages):
                return JsonResponse(_send_reply_payload(
                    False,
                    False,
                    conversation.last_sequence > input_sequence,
                    False,
                    "facebook_send_in_progress",
                ), status=200)
            for outbound in outbound_messages:
                if outbound.status in [
                    MessengerOutboundMessage.STATUS_PENDING,
                    MessengerOutboundMessage.STATUS_FAILED,
                ]:
                    outbound_ids_to_send.append(outbound.pk)
            if outbound_ids_to_send:
                turn.status = MessengerAITurn.STATUS_SENDING
                turn.reply_text = reply_text.strip()
                turn.save(update_fields=["status", "reply_text", "updated_at"])
            elif MessengerOutboundMessage.objects.filter(
                turn=turn,
                body_index__lt=len(facebook_bodies),
                status=MessengerOutboundMessage.STATUS_UNKNOWN,
            ).exists():
                complete_after_claim = "unknown"
            elif not MessengerOutboundMessage.objects.filter(
                turn=turn,
                body_index__lt=len(facebook_bodies),
            ).exclude(status=MessengerOutboundMessage.STATUS_SENT).exists():
                complete_after_claim = "sent"

    if complete_after_claim:
        result = _complete_messenger_turn_after_send(connection, clean_psid, clean_turn_token, input_sequence, reply_text)
        if complete_after_claim == "unknown":
            result.update({"send_reply": False, "sent": False, "error": "facebook_send_status_unknown"})
        return JsonResponse(result, status=200)

    for outbound_index, outbound_id in enumerate(outbound_ids_to_send):
        with transaction.atomic():
            outbound = MessengerOutboundMessage.objects.select_for_update().get(pk=outbound_id)
            if outbound.status == MessengerOutboundMessage.STATUS_SENT:
                continue
            if outbound.status == MessengerOutboundMessage.STATUS_UNKNOWN:
                result = _complete_messenger_turn_after_send(connection, clean_psid, clean_turn_token, input_sequence, reply_text)
                result.update({"send_reply": False, "sent": False, "error": "facebook_send_status_unknown"})
                return JsonResponse(result, status=200)
            if outbound.status == MessengerOutboundMessage.STATUS_SENDING:
                return JsonResponse(_send_reply_payload(
                    False,
                    False,
                    False,
                    False,
                    "facebook_send_in_progress",
                ), status=200)
            outbound.status = MessengerOutboundMessage.STATUS_SENDING
            outbound.error = ""
            outbound.save(update_fields=["status", "error", "updated_at"])
            outbound_body = outbound.body
        try:
            response = requests.post(
                "https://graph.facebook.com/v18.0/me/messages",
                headers={"Authorization": f"Bearer {connection.page_access_token}"},
                json=outbound_body,
                timeout=10,
                allow_redirects=False,
            )
        except requests.RequestException:
            logger.error("Messenger turn reply delivery status unknown")
            with transaction.atomic():
                unknown_outbound = MessengerOutboundMessage.objects.select_for_update().get(pk=outbound_id)
                unknown_outbound.status = MessengerOutboundMessage.STATUS_UNKNOWN
                unknown_outbound.error = "facebook_send_status_unknown"
                unknown_outbound.save(update_fields=["status", "error", "updated_at"])
                MessengerOutboundMessage.objects.filter(
                    pk__in=outbound_ids_to_send[outbound_index + 1:],
                    status__in=[
                        MessengerOutboundMessage.STATUS_PENDING,
                        MessengerOutboundMessage.STATUS_FAILED,
                    ],
                ).update(status=MessengerOutboundMessage.STATUS_UNKNOWN, error="facebook_send_status_unknown")
            result = _complete_messenger_turn_after_send(connection, clean_psid, clean_turn_token, input_sequence, reply_text)
            result.update({"send_reply": False, "sent": False, "error": "facebook_send_status_unknown"})
            return JsonResponse(result, status=200)
        try:
            response.raise_for_status()
        except requests.RequestException:
            logger.error("Failed to send Messenger turn reply")
            with transaction.atomic():
                failed_outbound = MessengerOutboundMessage.objects.select_for_update().get(pk=outbound_id)
                failed_outbound.status = MessengerOutboundMessage.STATUS_FAILED
                failed_outbound.error = "facebook_send_failed"
                failed_outbound.save(update_fields=["status", "error", "updated_at"])
            has_pending = _reset_failed_messenger_turn_after_send(connection, clean_psid, clean_turn_token, input_sequence)
            return JsonResponse(_send_reply_payload(
                False,
                False,
                has_pending,
                False,
                "facebook_send_failed",
            ), status=502)
        with transaction.atomic():
            sent_outbound = MessengerOutboundMessage.objects.select_for_update().get(pk=outbound_id)
            sent_outbound.status = MessengerOutboundMessage.STATUS_SENT
            sent_outbound.error = ""
            sent_outbound.save(update_fields=["status", "error", "updated_at"])

    with transaction.atomic():
        conversation = MessengerConversation.objects.select_for_update().filter(
            connection=connection,
            psid=clean_psid,
        ).first()
        if not conversation:
            return JsonResponse({"send_reply": False, "stale": True, "has_pending": False, "sent": False}, status=200)
        turn = MessengerAITurn.objects.select_for_update().filter(conversation=conversation, token=clean_turn_token).first()
        is_current = bool(
            turn
            and turn.status == MessengerAITurn.STATUS_SENDING
            and turn.input_sequence == input_sequence
            and conversation.last_sequence >= input_sequence
        )
        if not is_current:
            return JsonResponse(_send_reply_payload(
                False,
                True,
                conversation.last_sequence > input_sequence,
                False,
            ), status=200)
        if MessengerOutboundMessage.objects.filter(
            turn=turn,
            body_index__lt=len(facebook_bodies),
            status=MessengerOutboundMessage.STATUS_UNKNOWN,
        ).exists():
            complete_after_send = "unknown"
        elif MessengerOutboundMessage.objects.filter(
            turn=turn,
            body_index__lt=len(facebook_bodies),
            status=MessengerOutboundMessage.STATUS_SENDING,
        ).exists():
            return JsonResponse(_send_reply_payload(
                False,
                False,
                conversation.last_sequence > input_sequence,
                False,
                "facebook_send_in_progress",
            ), status=200)
        elif MessengerOutboundMessage.objects.filter(
            turn=turn,
            body_index__lt=len(facebook_bodies),
        ).exclude(status=MessengerOutboundMessage.STATUS_SENT).exists():
            has_pending = _reset_failed_messenger_turn_after_send(connection, clean_psid, clean_turn_token, input_sequence)
            return JsonResponse(_send_reply_payload(
                False,
                False,
                has_pending,
                False,
                "facebook_send_failed",
            ), status=502)
        else:
            complete_after_send = "sent"

    result = _complete_messenger_turn_after_send(connection, clean_psid, clean_turn_token, input_sequence, reply_text)
    if complete_after_send == "unknown":
        result.update({"send_reply": False, "sent": False, "error": "facebook_send_status_unknown"})
    return JsonResponse(result, status=200)


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
    return _ai_tool_response(request, lambda data: _legacy_widget_mutation_response("created"))


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
    return _ai_tool_response(request, lambda data: _legacy_widget_mutation_response("cancelled"))


@csrf_exempt
@require_http_methods(["POST"])
def widget_ai_appointment_reschedule(request):
    return _ai_tool_response(request, lambda data: _legacy_widget_mutation_response("rescheduled"))


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
            response = requests.post(
                url,
                headers={"Authorization": f"Bearer {page_token}"},
                json=msg_payload,
                timeout=10,
                allow_redirects=False,
            )
            response.raise_for_status()
        except requests.RequestException:
            logger.error("Failed to send Messenger reply")


@csrf_exempt
@require_http_methods(["POST"])
def n8n_webhook(request):
    """Receive webhook calls from n8n and return reply actions."""
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
    turn_token = data.get("turn_token", "")
    input_sequence = data.get("input_sequence")
    if not all(isinstance(value, str) for value in [page_id, psid, text, postback, turn_token]):
        return JsonResponse({"error": "Invalid request data"}, status=400)

    if not page_id or not psid:
        return JsonResponse({"replies": []}, status=200)

    connection = _active_connection_for_page(page_id)
    if not connection:
        return JsonResponse({"replies": []}, status=200)
    force_quick_replies = data.get("force_quick_replies") is True
    if _uses_messenger_ai_mode(connection) and not force_quick_replies:
        return JsonResponse({
            "replies": [_messenger_ai_fallback_action(connection)],
        }, status=200)

    with transaction.atomic():
        if not _validate_locked_messenger_turn(connection, psid, turn_token, input_sequence):
            return JsonResponse({
                "replies": [],
                "page_id": page_id,
                "psid": psid,
                "stale": True,
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
