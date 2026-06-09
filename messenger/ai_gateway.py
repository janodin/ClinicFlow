import json
import logging

from django.conf import settings

from clinics.models import ClinicAIProviderSettings, ClinicAISettings

from .ai_provider_client import AIProviderError, call_chat_completion
from .ai_tools import (
    book_confirmed_appointment,
    book_widget_confirmed_appointment,
    build_ai_context,
    build_widget_ai_context,
    cancel_verified_appointment,
    cancel_widget_verified_appointment,
    check_availability,
    check_widget_availability,
    find_verified_appointment,
    find_widget_verified_appointment,
    get_clinic_for_slug,
    get_connection_for_page,
    get_or_create_clinic_ai_settings,
    match_services,
    match_widget_services,
    reschedule_verified_appointment,
    reschedule_widget_verified_appointment,
)
from .defaults import DEFAULT_AI_FALLBACK_MESSAGE, DEFAULT_MESSENGER_AI_PROMPT


logger = logging.getLogger(__name__)

MAX_GATEWAY_MESSAGE_CHARS = 1800
MAX_GATEWAY_TOOL_CALLS_PER_RESPONSE = 4
MUTATING_TOOL_NAMES = {"book_confirmed_appointment", "cancel_verified_appointment", "reschedule_verified_appointment"}
GATEWAY_TOOL_NAMES = {
    "match_services",
    "check_availability",
    "book_confirmed_appointment",
    "find_verified_appointment",
    "cancel_verified_appointment",
    "reschedule_verified_appointment",
}
SECRET_CONTEXT_KEYS = {
    "api_key",
    "access_token",
    "app_secret",
    "page_token",
    "page_access_token",
    "token",
    "secret",
    "webhook_secret",
    "authorization",
    "password",
    "credential",
}


def _fallback_for_clinic(clinic, error):
    if clinic:
        ai_settings = get_or_create_clinic_ai_settings(clinic)
        message = ai_settings.fallback_message or DEFAULT_AI_FALLBACK_MESSAGE
    else:
        message = DEFAULT_AI_FALLBACK_MESSAGE
    return {"reply": message, "fallback": True, "error": error}


def _resolve_gateway_clinic(data):
    channel = str(data.get("channel", "")).strip().lower()
    if channel == "messenger":
        connection = get_connection_for_page(data.get("page_id", ""))
        return connection.clinic if connection else None
    if channel == "widget":
        return get_clinic_for_slug(data.get("clinic_slug", ""))
    return None


def _context_for_gateway(channel, data):
    if channel == "messenger":
        return build_ai_context(data.get("page_id", ""))
    if channel == "widget":
        return build_widget_ai_context(data.get("clinic_slug", ""))
    return {"found": False}


def _safe_context_for_prompt(value):
    if isinstance(value, dict):
        safe = {}
        for key, item in value.items():
            key_text = str(key).lower()
            normalized_key = key_text.replace("-", "_")
            if (
                normalized_key in SECRET_CONTEXT_KEYS
                or "token" in normalized_key
                or "secret" in normalized_key
                or "api_key" in normalized_key
                or "apikey" in normalized_key
                or "password" in normalized_key
                or "credential" in normalized_key
            ):
                continue
            safe[key] = _safe_context_for_prompt(item)
        return safe
    if isinstance(value, list):
        return [_safe_context_for_prompt(item) for item in value]
    return value


def _system_message(clinic, context):
    ai_settings = get_or_create_clinic_ai_settings(clinic)
    instructions = (ai_settings.instructions or DEFAULT_MESSENGER_AI_PROMPT).strip()
    safe_context = _safe_context_for_prompt(context)
    return {
        "role": "system",
        "content": "\n\n".join([
            instructions,
            "Clinic context JSON:",
            json.dumps(safe_context, default=str),
        ]),
    }


def _clean_gateway_content(value):
    return str(value or "").strip()[:MAX_GATEWAY_MESSAGE_CHARS]


def _messages_for_request(clinic, context, data):
    messages = [_system_message(clinic, context)]
    history = data.get("history", [])
    if isinstance(history, list):
        for item in history[-16:]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role", "")).strip().lower()
            if role not in {"user", "assistant"}:
                continue
            content = _clean_gateway_content(item.get("content", ""))
            if content:
                messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": _clean_gateway_content(data.get("message", ""))})
    return messages


def _provider_settings_for_clinic(clinic):
    provider_settings, _ = ClinicAIProviderSettings.objects.get_or_create(clinic=clinic)
    return provider_settings


def _provider_model_attempts(provider_settings):
    primary_model = (provider_settings.model or "").strip()
    fallback_model = (provider_settings.fallback_model or "").strip() or primary_model
    return [("primary", primary_model), ("fallback", fallback_model)]


def _call_provider_with_fallback(provider_settings, messages, tools):
    last_error = "empty_provider_reply"
    for model_role, model in _provider_model_attempts(provider_settings):
        try:
            provider_message = call_chat_completion(
                provider_settings,
                messages,
                tools=tools,
                model=model,
                model_role=model_role,
            )
        except AIProviderError:
            last_error = "ai_provider_error"
            logger.warning(
                "AI gateway provider request failed",
                extra={
                    "clinic_id": provider_settings.clinic_id,
                    "model_role": model_role,
                },
            )
            continue

        tool_calls = provider_message.get("tool_calls") or []
        if tool_calls or _clean_gateway_content(provider_message.get("content", "")):
            return provider_message, ""

        last_error = "empty_provider_reply"
        logger.warning(
            "AI gateway provider returned empty reply",
            extra={
                "clinic_id": provider_settings.clinic_id,
                "model_role": model_role,
            },
        )
    return None, last_error


def _gateway_ai_enabled(channel, clinic):
    ai_settings = get_or_create_clinic_ai_settings(clinic)
    if channel == "messenger":
        return ai_settings.safe_messenger_response_mode == ClinicAISettings.MESSENGER_MODE_AI
    return ai_settings.is_ai_enabled


def _tool_definitions():
    return [
        {
            "type": "function",
            "function": {
                "name": "match_services",
                "description": "Find active clinic services matching a patient query.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Service name or need described by the patient."},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "check_availability",
                "description": "Check available appointment slots for a clinic service.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service_id": {"type": "integer"},
                        "preferred_starts_at": {"type": "string", "description": "Optional ISO date-time requested by the patient."},
                        "preferred_date": {"type": "string", "description": "Optional ISO date requested by the patient."},
                    },
                    "required": ["service_id"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "find_verified_appointment",
                "description": "Find a future appointment after verifying reference code and phone number.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reference_code": {"type": "string"},
                        "phone": {"type": "string"},
                    },
                    "required": ["reference_code", "phone"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "cancel_verified_appointment",
                "description": "Cancel a verified future appointment after explicit patient confirmation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reference_code": {"type": "string"},
                        "phone": {"type": "string"},
                        "confirmed": {"type": "boolean"},
                        "reason": {"type": "string"},
                    },
                    "required": ["reference_code", "phone", "confirmed"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "reschedule_verified_appointment",
                "description": "Reschedule a verified future appointment after explicit patient confirmation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reference_code": {"type": "string"},
                        "phone": {"type": "string"},
                        "starts_at": {"type": "string", "description": "New ISO date-time requested by the patient."},
                        "confirmed": {"type": "boolean"},
                    },
                    "required": ["reference_code", "phone", "starts_at", "confirmed"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "book_confirmed_appointment",
                "description": "Create an appointment only after the patient explicitly confirms the full booking details.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service_id": {"type": "integer"},
                        "starts_at": {"type": "string", "description": "Confirmed ISO appointment start time."},
                        "full_name": {"type": "string"},
                        "phone": {"type": "string"},
                        "email": {"type": "string"},
                        "reason": {"type": "string"},
                        "confirmed": {"type": "boolean"},
                    },
                    "required": ["service_id", "starts_at", "full_name", "phone", "email", "confirmed"],
                    "additionalProperties": False,
                },
            },
        },
    ]


def _json_tool_arguments(call):
    function = call.get("function") if isinstance(call, dict) else None
    raw_arguments = function.get("arguments", "{}") if isinstance(function, dict) else "{}"
    if isinstance(raw_arguments, dict):
        return raw_arguments
    try:
        parsed = json.loads(raw_arguments or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _bool_value(value):
    return value is True


def _tool_name(call):
    function = call.get("function") if isinstance(call, dict) else None
    return function.get("name", "") if isinstance(function, dict) else ""


def _tool_calls_are_allowed(tool_calls, mutation_already_executed=False):
    if not isinstance(tool_calls, list):
        return False
    if len(tool_calls) > MAX_GATEWAY_TOOL_CALLS_PER_RESPONSE:
        return False
    names = [_tool_name(call) for call in tool_calls]
    if any(name not in GATEWAY_TOOL_NAMES for name in names):
        return False
    mutation_count = sum(1 for name in names if name in MUTATING_TOOL_NAMES)
    if mutation_count > 1:
        return False
    if mutation_already_executed and mutation_count:
        return False
    return True


def _execute_tool(channel, data, name, args):
    if channel == "messenger":
        page_id = data.get("page_id", "")
        psid = data.get("psid", "")
        turn_token = data.get("turn_token", "")
        input_sequence = data.get("input_sequence")
        if name == "match_services":
            return match_services(page_id, args.get("query", ""))
        if name == "check_availability":
            return check_availability(
                page_id,
                args.get("service_id"),
                preferred_starts_at=args.get("preferred_starts_at"),
                preferred_date=args.get("preferred_date"),
            )
        if name == "find_verified_appointment":
            return find_verified_appointment(page_id, args.get("reference_code", ""), args.get("phone", ""))
        if name == "cancel_verified_appointment":
            return cancel_verified_appointment(
                page_id,
                args.get("reference_code", ""),
                args.get("phone", ""),
                _bool_value(args.get("confirmed")),
                reason=args.get("reason", ""),
                psid=psid,
                turn_token=turn_token,
                input_sequence=input_sequence,
            )
        if name == "reschedule_verified_appointment":
            return reschedule_verified_appointment(
                page_id,
                args.get("reference_code", ""),
                args.get("phone", ""),
                args.get("starts_at", ""),
                _bool_value(args.get("confirmed")),
                psid=psid,
                turn_token=turn_token,
                input_sequence=input_sequence,
            )
        if name == "book_confirmed_appointment":
            return book_confirmed_appointment(
                page_id,
                args.get("service_id"),
                args.get("starts_at", ""),
                args.get("full_name", ""),
                args.get("phone", ""),
                _bool_value(args.get("confirmed")),
                email=args.get("email", ""),
                reason=args.get("reason", ""),
                psid=psid,
                turn_token=turn_token,
                input_sequence=input_sequence,
            )
    if channel == "widget":
        clinic_slug = data.get("clinic_slug", "")
        if name == "match_services":
            return match_widget_services(clinic_slug, args.get("query", ""))
        if name == "check_availability":
            return check_widget_availability(
                clinic_slug,
                args.get("service_id"),
                preferred_starts_at=args.get("preferred_starts_at"),
                preferred_date=args.get("preferred_date"),
            )
        if name == "find_verified_appointment":
            return find_widget_verified_appointment(clinic_slug, args.get("reference_code", ""), args.get("phone", ""))
        if name == "cancel_verified_appointment":
            return cancel_widget_verified_appointment(
                clinic_slug,
                args.get("reference_code", ""),
                args.get("phone", ""),
                _bool_value(args.get("confirmed")),
                reason=args.get("reason", ""),
            )
        if name == "reschedule_verified_appointment":
            return reschedule_widget_verified_appointment(
                clinic_slug,
                args.get("reference_code", ""),
                args.get("phone", ""),
                args.get("starts_at", ""),
                _bool_value(args.get("confirmed")),
            )
        if name == "book_confirmed_appointment":
            return book_widget_confirmed_appointment(
                clinic_slug,
                args.get("service_id"),
                args.get("starts_at", ""),
                args.get("full_name", ""),
                args.get("phone", ""),
                _bool_value(args.get("confirmed")),
                email=args.get("email", ""),
                reason=args.get("reason", ""),
            )
    return {"error": "Unknown tool."}


def build_gateway_reply(data):
    channel = str(data.get("channel", "")).strip().lower()
    clinic = _resolve_gateway_clinic(data)
    if not clinic:
        return _fallback_for_clinic(None, "clinic_not_found")
    if not _gateway_ai_enabled(channel, clinic):
        return _fallback_for_clinic(clinic, "ai_disabled")

    provider_settings = _provider_settings_for_clinic(clinic)
    if not provider_settings.is_configured:
        return _fallback_for_clinic(clinic, "ai_provider_unconfigured")

    context = _context_for_gateway(channel, data)
    messages = _messages_for_request(clinic, context, data)
    tools = _tool_definitions()
    max_iterations = max(1, getattr(settings, "AI_GATEWAY_MAX_TOOL_ITERATIONS", 5))
    mutation_executed = False
    for _iteration in range(max_iterations):
        provider_message, provider_error = _call_provider_with_fallback(provider_settings, messages, tools)
        if provider_message is None:
            return _fallback_for_clinic(clinic, provider_error)

        tool_calls = provider_message.get("tool_calls") or []
        if not tool_calls:
            reply = _clean_gateway_content(provider_message.get("content", ""))
            if not reply:
                return _fallback_for_clinic(clinic, "empty_provider_reply")
            return {"reply": reply, "fallback": False, "error": ""}
        if not _tool_calls_are_allowed(tool_calls, mutation_executed):
            return _fallback_for_clinic(clinic, "invalid_tool_call")

        messages.append({
            "role": "assistant",
            "content": provider_message.get("content", "") or "",
            "tool_calls": tool_calls,
        })
        for call in tool_calls:
            name = _tool_name(call)
            try:
                result = _execute_tool(channel, data, name, _json_tool_arguments(call))
            except Exception:
                logger.warning(
                    "AI gateway tool execution failed",
                    extra={"clinic_id": clinic.id, "tool_name": name},
                )
                result = {"error": "Tool execution failed."}
            if name in MUTATING_TOOL_NAMES:
                mutation_executed = True
            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id", "") if isinstance(call, dict) else "",
                "content": json.dumps(result, default=str),
            })

    return _fallback_for_clinic(clinic, "tool_loop_exceeded")
