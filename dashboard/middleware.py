import json

from django.contrib import messages


def _toast_type(tags):
    tag_set = set(str(tags).split())
    for tag in ("error", "warning", "info", "success"):
        if tag in tag_set:
            return tag
    return "success"


class HtmxMessagesMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.headers.get("HX-Request"):
            msgs = []
            for message in messages.get_messages(request):
                msgs.append(
                    {
                        "message": str(message),
                        "type": _toast_type(message.tags),
                    }
                )
            if msgs:
                toast_detail = msgs[0] if len(msgs) == 1 else msgs
                trigger_payload = {"toast-message": toast_detail}
                existing = response.get("HX-Trigger")
                if existing:
                    try:
                        existing_triggers = json.loads(existing)
                        existing_triggers.update(trigger_payload)
                        trigger_payload = existing_triggers
                    except json.JSONDecodeError:
                        # Existing value is a plain string event name; wrap it
                        trigger_payload = {existing: True, "toast-message": toast_detail}
                response["HX-Trigger"] = json.dumps(trigger_payload)
        return response
