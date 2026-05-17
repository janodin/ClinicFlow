import json

from django.contrib import messages


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
                        "type": "error" if message.tags == "error" else "success",
                    }
                )
            if msgs:
                trigger_payload = {"toast-message": msgs[0]}
                existing = response.get("HX-Trigger")
                if existing:
                    try:
                        existing_triggers = json.loads(existing)
                        existing_triggers.update(trigger_payload)
                        trigger_payload = existing_triggers
                    except json.JSONDecodeError:
                        # Existing value is a plain string event name; wrap it
                        trigger_payload = {existing: True, "toast-message": msgs[0]}
                response["HX-Trigger"] = json.dumps(trigger_payload)
        return response
