# Widget Assistant AI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the widget "Chat with Assistant" use AI through a shared n8n webhook while Messenger and the widget share one clinic-level AI prompt, enable switch, and fallback message.

**Architecture:** Add `ClinicAISettings` as shared clinic-owned AI configuration. Refactor Messenger AI code to read that shared config, add widget-scoped AI tools and a server-side n8n client, and keep browser code talking only to Django. n8n owns model/provider execution and calls Django tools for context, availability, and confirmed booking.

**Tech Stack:** Django, Django ORM migrations, Django templates, Alpine.js widget UI, pytest/Django TestCase, requests, n8n workflow SDK/MCP.

---

## File Structure

- Modify: `clinics/models.py` adds `ClinicAISettings` next to other clinic-owned models.
- Create: `clinics/migrations/0006_clinic_ai_settings.py` adds the model and copies existing `MessengerAISettings` rows into shared settings.
- Modify: `messenger/forms.py` keeps `MessengerAISettingsForm` as the form class name but points it at `ClinicAISettings`.
- Modify: `dashboard/views.py` updates `messenger_settings()` to create/read/save shared clinic AI settings and allow AI settings without a Messenger connection.
- Modify: `dashboard/templates/dashboard/messenger_settings.html` updates copy from Messenger-only AI to shared AI prompt settings.
- Modify: `messenger/ai_tools.py` adds clinic-scoped AI context/services/availability/book helpers and keeps Messenger page-id wrappers.
- Modify: `messenger/views.py` adds widget AI tool endpoints protected by `X-N8N-Webhook-Secret`.
- Modify: `messenger/urls.py` exposes widget AI tool endpoints.
- Modify: `config/settings.py` adds `ASSISTANT_N8N_WEBHOOK_URL` and `ASSISTANT_N8N_TIMEOUT_SECONDS`.
- Modify: `.env.example` documents the new n8n settings.
- Create: `widget/ai_client.py` sends widget chat requests to n8n and normalizes replies.
- Modify: `widget/views.py` routes free-text chat to AI when enabled, keeps guided booking actions intact, and returns shared fallback on disabled/unavailable AI.
- Modify: `templates/widget/widget.html` ensures chat POSTs always have a CSRF token available.
- Modify: `messenger/tests.py`, `widget/tests.py`, and `dashboard/tests.py` add/adjust tests.
- Create in n8n: `Widget Assistant AI` workflow in the existing n8n project.

---

### Task 1: Add Shared Clinic AI Settings

**Files:**
- Modify: `clinics/models.py`
- Create: `clinics/migrations/0006_clinic_ai_settings.py`
- Test: `messenger/tests.py`

- [ ] **Step 1: Write failing model tests**

Append to `messenger/tests.py` near existing Messenger AI settings tests:

```python
@pytest.mark.django_db
def test_clinic_ai_settings_defaults_and_unique_clinic():
    from clinics.models import ClinicAISettings
    from messenger.defaults import DEFAULT_MESSENGER_AI_PROMPT

    clinic, connection = _create_messenger_clinic("owner_clinic_ai_defaults", "PAGE-CLINIC-AI")
    settings = ClinicAISettings.objects.create(clinic=clinic)

    assert settings.clinic == clinic
    assert settings.is_ai_enabled is True
    assert settings.instructions == DEFAULT_MESSENGER_AI_PROMPT
    assert settings.fallback_message == ""
    assert str(settings) == f"ClinicAISettings({clinic.name})"

    with pytest.raises(IntegrityError):
        ClinicAISettings.objects.create(clinic=clinic)


@pytest.mark.django_db
def test_clinic_ai_settings_manager_copies_messenger_values():
    from clinics.models import ClinicAISettings
    from messenger.models import MessengerAISettings

    clinic, connection = _create_messenger_clinic("owner_clinic_ai_copy", "PAGE-CLINIC-COPY")
    MessengerAISettings.objects.create(
        connection=connection,
        is_ai_enabled=False,
        instructions="Copied shared instructions.",
        fallback_message="Copied fallback.",
    )

    settings = ClinicAISettings.objects.create_from_messenger_settings(connection.ai_settings)

    assert settings.clinic == clinic
    assert settings.is_ai_enabled is False
    assert settings.instructions == "Copied shared instructions."
    assert settings.fallback_message == "Copied fallback."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\env\Scripts\python -m pytest messenger/tests.py::test_clinic_ai_settings_defaults_and_unique_clinic messenger/tests.py::test_clinic_ai_settings_manager_copies_messenger_values -v`

Expected: FAIL because `ClinicAISettings` does not exist.

- [ ] **Step 3: Add the shared model**

Modify `clinics/models.py`. Add this import near the top:

```python
from messenger.defaults import DEFAULT_MESSENGER_AI_PROMPT
```

Add after `ClinicFAQ`:

```python
class ClinicAISettingsManager(models.Manager):
    def create_from_messenger_settings(self, messenger_settings):
        settings, _ = self.update_or_create(
            clinic=messenger_settings.connection.clinic,
            defaults={
                "is_ai_enabled": messenger_settings.is_ai_enabled,
                "instructions": messenger_settings.instructions,
                "fallback_message": messenger_settings.fallback_message,
            },
        )
        return settings


class ClinicAISettings(TimeStampedModel):
    clinic = models.OneToOneField(Clinic, on_delete=models.CASCADE, related_name="ai_settings")
    is_ai_enabled = models.BooleanField(default=True)
    instructions = models.TextField(blank=True, default=DEFAULT_MESSENGER_AI_PROMPT)
    fallback_message = models.TextField(blank=True, default="")

    objects = ClinicAISettingsManager()

    class Meta:
        verbose_name = "Clinic AI Settings"
        verbose_name_plural = "Clinic AI Settings"

    def __str__(self):
        return f"ClinicAISettings({self.clinic.name})"
```

- [ ] **Step 4: Create migration and add data copy**

Run: `.\env\Scripts\python manage.py makemigrations clinics`

Expected: migration file for `ClinicAISettings` is created.

Edit the generated migration to include this data migration after `CreateModel`:

```python
def copy_messenger_ai_settings(apps, schema_editor):
    ClinicAISettings = apps.get_model("clinics", "ClinicAISettings")
    MessengerAISettings = apps.get_model("messenger", "MessengerAISettings")
    for messenger_settings in MessengerAISettings.objects.select_related("connection__clinic"):
        ClinicAISettings.objects.update_or_create(
            clinic_id=messenger_settings.connection.clinic_id,
            defaults={
                "is_ai_enabled": messenger_settings.is_ai_enabled,
                "instructions": messenger_settings.instructions,
                "fallback_message": messenger_settings.fallback_message,
            },
        )


def noop_reverse(apps, schema_editor):
    pass
```

Add this operation:

```python
migrations.RunPython(copy_messenger_ai_settings, noop_reverse),
```

- [ ] **Step 5: Verify**

Run: `.\env\Scripts\python manage.py migrate`

Expected: migration applies successfully.

Run: `.\env\Scripts\python manage.py check`

Expected: `System check identified no issues`.

Run: `.\env\Scripts\python -m pytest messenger/tests.py::test_clinic_ai_settings_defaults_and_unique_clinic messenger/tests.py::test_clinic_ai_settings_manager_copies_messenger_values -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add clinics/models.py clinics/migrations/0006_clinic_ai_settings.py messenger/tests.py
git commit -m "feat: add shared clinic ai settings"
```

---

### Task 2: Move Messenger Prompt UI To Shared Settings

**Files:**
- Modify: `messenger/forms.py`
- Modify: `dashboard/views.py`
- Modify: `dashboard/templates/dashboard/messenger_settings.html`
- Test: `dashboard/tests.py`

- [ ] **Step 1: Write failing dashboard tests**

Update the existing AI prompt tests in `dashboard/tests.py` to use `ClinicAISettings` instead of `MessengerAISettings`. Add this test:

```python
@pytest.mark.django_db
def test_owner_can_save_shared_ai_settings_without_messenger_connection(clinic_setup, client):
    from clinics.models import ClinicAISettings

    clinic, service, user = clinic_setup
    client.force_login(user)

    response = client.post(
        reverse("dashboard:messenger_settings"),
        {
            "_form": "ai_settings",
            "is_ai_enabled": "on",
            "instructions": "Shared website and Messenger instructions.",
            "fallback_message": "Shared fallback.",
        },
    )

    assert response.status_code == 302
    settings = ClinicAISettings.objects.get(clinic=clinic)
    assert settings.is_ai_enabled is True
    assert settings.instructions == "Shared website and Messenger instructions."
    assert settings.fallback_message == "Shared fallback."
```

- [ ] **Step 2: Run tests to verify failure**

Run: `.\env\Scripts\python -m pytest dashboard/tests.py::test_owner_can_save_messenger_ai_settings dashboard/tests.py::test_owner_can_save_shared_ai_settings_without_messenger_connection -v`

Expected: FAIL because the view still blocks AI settings when there is no Messenger connection.

- [ ] **Step 3: Update form model**

Modify `messenger/forms.py`:

```python
from clinics.models import ClinicAISettings
from messenger.models import MessengerConnection
```

Change `MessengerAISettingsForm.Meta`:

```python
class MessengerAISettingsForm(forms.ModelForm):
    class Meta:
        model = ClinicAISettings
        fields = ["is_ai_enabled", "instructions", "fallback_message"]
        help_texts = {
            "instructions": "Used by both Messenger and the website Assistant. Services, prices, and availability still come from KliniAssist.",
            "fallback_message": "Shown in both Messenger and the website Assistant when AI replies are disabled or unavailable.",
        }
```

- [ ] **Step 4: Update `messenger_settings()`**

Modify `dashboard/views.py` inside `messenger_settings()`:

```python
from clinics.models import ClinicAISettings
from messenger.forms import MessengerAISettingsForm, MessengerConnectionForm

connection = getattr(clinic, "messenger_connection", None)
ai_settings, _ = ClinicAISettings.objects.get_or_create(clinic=clinic)
post_form = request.POST.get("_form")
```

For AI settings POST, use:

```python
elif request.method == "POST" and request.POST.get("_form") == "ai_settings":
    form = MessengerConnectionForm(instance=connection)
    ai_form = MessengerAISettingsForm(request.POST, instance=ai_settings)
    if ai_form.is_valid():
        ai_form.save()
        messages.success(request, "Shared AI prompt settings saved.")
        return redirect("dashboard:messenger_settings")
```

On GET, always provide `ai_form = MessengerAISettingsForm(instance=ai_settings)`.

- [ ] **Step 5: Update template copy**

In `dashboard/templates/dashboard/messenger_settings.html`, change the card title and helper copy:

```html
<h2 class="cf-section-title">Shared AI Prompt</h2>
<p class="mt-1 text-sm text-[var(--cf-muted)]">Used by both Facebook Messenger and the website Assistant.</p>
```

Remove the branch that hides the AI prompt form until Facebook Page settings are saved.

- [ ] **Step 6: Verify dashboard tests**

Run: `.\env\Scripts\python -m pytest dashboard/tests.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add messenger/forms.py dashboard/views.py dashboard/templates/dashboard/messenger_settings.html dashboard/tests.py
git commit -m "refactor: share ai prompt settings by clinic"
```

---

### Task 3: Add Clinic-Scoped AI Tools

**Files:**
- Modify: `messenger/ai_tools.py`
- Modify: `messenger/views.py`
- Modify: `messenger/urls.py`
- Test: `messenger/tests.py`

- [ ] **Step 1: Write failing tool tests**

Append to `messenger/tests.py`:

```python
@pytest.mark.django_db
def test_build_widget_ai_context_uses_shared_clinic_settings():
    from clinics.models import ClinicAISettings
    from messenger.ai_tools import build_widget_ai_context

    clinic, connection = _create_messenger_clinic("owner_widget_context", "PAGE-WIDGET-CONTEXT")
    Service.objects.create(clinic=clinic, name="Checkup", duration_minutes=30, price=500)
    ClinicFAQ.objects.create(clinic=clinic, question="Hours?", answer="9 AM to 5 PM")
    ClinicAISettings.objects.create(clinic=clinic, is_ai_enabled=False, instructions="Shared instructions.", fallback_message="Shared fallback.")

    context = build_widget_ai_context(clinic.slug)

    assert context["found"] is True
    assert context["clinic"]["id"] == clinic.id
    assert context["ai"]["is_ai_enabled"] is False
    assert context["ai"]["instructions"] == "Shared instructions."
    assert context["ai"]["fallback_message"] == "Shared fallback."
    assert context["services"][0]["name"] == "Checkup"
    assert context["faqs"][0]["question"] == "Hours?"


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret")
def test_widget_ai_context_endpoint_requires_secret(client):
    clinic, connection = _create_messenger_clinic("owner_widget_secret", "PAGE-WIDGET-SECRET")

    response = client.post(
        reverse("messenger:widget_ai_context"),
        data=json.dumps({"clinic_slug": clinic.slug}),
        content_type="application/json",
    )

    assert response.status_code == 401
```

- [ ] **Step 2: Run tests to verify failure**

Run: `.\env\Scripts\python -m pytest messenger/tests.py::test_build_widget_ai_context_uses_shared_clinic_settings messenger/tests.py::test_widget_ai_context_endpoint_requires_secret -v`

Expected: FAIL because widget helpers and URL names do not exist.

- [ ] **Step 3: Add helpers in `messenger/ai_tools.py`**

Add imports:

```python
from clinics.models import Clinic, ClinicAISettings
```

Add shared fallback/settings helpers:

```python
DEFAULT_AI_FALLBACK_MESSAGE = "Sorry, the assistant is unavailable right now. You can still book an appointment using the booking form."


def get_or_create_clinic_ai_settings(clinic):
    settings, _ = ClinicAISettings.objects.get_or_create(clinic=clinic)
    return settings


def get_clinic_for_slug(clinic_slug):
    if not clinic_slug:
        return None
    return Clinic.objects.filter(slug=clinic_slug, is_active=True).first()


def _ai_payload_for_clinic(clinic):
    ai_settings = get_or_create_clinic_ai_settings(clinic)
    return {
        "is_ai_enabled": ai_settings.is_ai_enabled,
        "instructions": ai_settings.instructions or DEFAULT_MESSENGER_AI_PROMPT,
        "fallback_message": ai_settings.fallback_message or DEFAULT_AI_FALLBACK_MESSAGE,
    }
```

Add widget context helper:

```python
def build_widget_ai_context(clinic_slug):
    clinic = get_clinic_for_slug(clinic_slug)
    if not clinic:
        return {"found": False}
    services = clinic.services.filter(is_active=True, is_archived=False).order_by("name")
    faqs = clinic.faqs.filter(is_active=True).order_by("question")
    clinic_now = timezone.now().astimezone(ZoneInfo(clinic.timezone))
    return {
        "found": True,
        "channel": "widget",
        "current_time": {"timezone": clinic.timezone, "now": clinic_now.isoformat(), "today": clinic_now.date().isoformat()},
        "clinic": {"id": clinic.id, "slug": clinic.slug, "name": clinic.name, "address": clinic.address, "phone": clinic.phone, "email": clinic.email, "timezone": clinic.timezone},
        "ai": _ai_payload_for_clinic(clinic),
        "services": [_service_payload(service) for service in services],
        "faqs": [{"question": faq.question, "answer": faq.answer} for faq in faqs],
    }
```

Extract shared availability/booking internals from existing Messenger functions so both channel wrappers call the same validation code:

```python
def _check_availability_for_clinic(clinic, service_id, preferred_starts_at=None, preferred_date=None):
    service = clinic.services.filter(pk=service_id, is_active=True, is_archived=False).first()
    if not service:
        return {"found": True, "available": False, "error": "Service not found.", "alternatives": []}
    # Move the existing date parsing, generate_slots, selected_slot, and alternatives logic here unchanged.


def _book_confirmed_appointment_for_clinic(clinic, source, service_id, starts_at, full_name, phone, confirmed, email="", reason=""):
    if confirmed is not True:
        return {"created": False, "error": "Appointment creation requires explicit user confirmation."}
    appointment, error = _process_guest_booking(clinic, {"service": service_id, "starts_at": starts_at, "full_name": full_name, "phone": phone, "email": email, "reason": reason}, source)
    if error:
        return {"created": False, "error": error}
    local_start = appointment.starts_at.astimezone(ZoneInfo(clinic.timezone))
    return {"created": True, "appointment": {"id": appointment.id, "reference_code": appointment.reference_code, "service": appointment.service.name, "status": appointment.status, "starts_at": appointment.starts_at.isoformat(), "local_starts_at": local_start.isoformat(), "patient_name": appointment.patient.full_name, "patient_phone": appointment.patient.phone}}
```

Add widget wrappers using those internals:

```python
def match_widget_services(clinic_slug, query):
    clinic = get_clinic_for_slug(clinic_slug)
    if not clinic:
        return {"found": False, "matches": []}
    query_text = (query or "").strip().lower()
    services = clinic.services.filter(is_active=True, is_archived=False).order_by("name")
    matches = [service for service in services if not query_text or query_text in service.name.lower() or query_text in service.description.lower()]
    return {"found": True, "matches": [_service_payload(service) for service in matches]}


def check_widget_availability(clinic_slug, service_id, preferred_starts_at=None, preferred_date=None):
    clinic = get_clinic_for_slug(clinic_slug)
    if not clinic:
        return {"found": False, "available": False, "alternatives": []}
    return _check_availability_for_clinic(clinic, service_id, preferred_starts_at, preferred_date)


def book_widget_confirmed_appointment(clinic_slug, service_id, starts_at, full_name, phone, confirmed, email="", reason=""):
    clinic = get_clinic_for_slug(clinic_slug)
    if not clinic:
        return {"created": False, "error": "Clinic not found."}
    return _book_confirmed_appointment_for_clinic(clinic, Appointment.SOURCE_CHAT_WIDGET, service_id, starts_at, full_name, phone, confirmed, email, reason)
```

- [ ] **Step 4: Add endpoint wrappers and URLs**

In `messenger/views.py`, import the widget helpers and add:

```python
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
    return _ai_tool_response(request, lambda data: check_widget_availability(data.get("clinic_slug", ""), data.get("service_id"), data.get("preferred_starts_at"), data.get("preferred_date")))


@csrf_exempt
@require_http_methods(["POST"])
def widget_ai_book(request):
    return _ai_tool_response(request, lambda data: book_widget_confirmed_appointment(data.get("clinic_slug", ""), data.get("service_id"), data.get("starts_at"), data.get("full_name", ""), data.get("phone", ""), _normalize_confirmed(data.get("confirmed", False)), data.get("email", ""), data.get("reason", "")))
```

In `messenger/urls.py`, add:

```python
path("ai/widget/context/", views.widget_ai_context, name="widget_ai_context"),
path("ai/widget/services/", views.widget_ai_services, name="widget_ai_services"),
path("ai/widget/availability/", views.widget_ai_availability, name="widget_ai_availability"),
path("ai/widget/book/", views.widget_ai_book, name="widget_ai_book"),
```

- [ ] **Step 5: Verify**

Run: `.\env\Scripts\python -m pytest messenger/tests.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add messenger/ai_tools.py messenger/views.py messenger/urls.py messenger/tests.py
git commit -m "feat: add clinic-scoped ai tools"
```

---

### Task 4: Add Widget n8n Client And AI Chat Routing

**Files:**
- Create: `widget/ai_client.py`
- Modify: `widget/views.py`
- Modify: `templates/widget/widget.html`
- Modify: `config/settings.py`
- Modify: `.env.example`
- Test: `widget/tests.py`

- [ ] **Step 1: Write failing widget tests**

Append methods to `WidgetTests` in `widget/tests.py` and add imports for `override_settings`, `patch`, and `ClinicAISettings`:

```python
from django.test import override_settings
from unittest.mock import patch
from clinics.models import ClinicAISettings
```

```python
    @override_settings(ASSISTANT_N8N_WEBHOOK_URL="https://n8n.example/webhook/widget", N8N_WEBHOOK_SECRET="secret")
    @patch("widget.ai_client.requests.post")
    def test_chat_step_text_input_calls_n8n_when_ai_enabled(self, mock_post):
        ClinicAISettings.objects.create(clinic=self.clinic, is_ai_enabled=True, instructions="Shared instructions.", fallback_message="Fallback response.")
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"reply": "I can help you book."}

        response = self.client.post(reverse("widget:chat_step", args=[self.clinic.slug]), {"action": "text_input", "value": "Can I book tomorrow?"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "I can help you book.")
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["channel"], "widget")
        self.assertEqual(payload["clinic_slug"], self.clinic.slug)
        self.assertEqual(payload["message"], "Can I book tomorrow?")

    @override_settings(ASSISTANT_N8N_WEBHOOK_URL="https://n8n.example/webhook/widget", N8N_WEBHOOK_SECRET="secret")
    @patch("widget.ai_client.requests.post")
    def test_chat_step_returns_fallback_without_n8n_when_ai_disabled(self, mock_post):
        ClinicAISettings.objects.create(clinic=self.clinic, is_ai_enabled=False, instructions="Shared instructions.", fallback_message="AI is off. Please use the booking form.")

        response = self.client.post(reverse("widget:chat_step", args=[self.clinic.slug]), {"action": "text_input", "value": "Hello"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "AI is off. Please use the booking form.")
        mock_post.assert_not_called()

    @override_settings(ASSISTANT_N8N_WEBHOOK_URL="", N8N_WEBHOOK_SECRET="secret")
    def test_chat_step_returns_default_fallback_when_webhook_missing(self):
        ClinicAISettings.objects.create(clinic=self.clinic, is_ai_enabled=True, fallback_message="")

        response = self.client.post(reverse("widget:chat_step", args=[self.clinic.slug]), {"action": "text_input", "value": "Hello"})

        self.assertEqual(response.status_code, 200)
        self.assertIn("assistant is unavailable", response.json()["message"])
```

- [ ] **Step 2: Run tests to verify failure**

Run: `.\env\Scripts\python -m pytest widget/tests.py::WidgetTests::test_chat_step_text_input_calls_n8n_when_ai_enabled widget/tests.py::WidgetTests::test_chat_step_returns_fallback_without_n8n_when_ai_disabled widget/tests.py::WidgetTests::test_chat_step_returns_default_fallback_when_webhook_missing -v`

Expected: FAIL because `widget.ai_client` and AI routing do not exist.

- [ ] **Step 3: Add settings**

In `config/settings.py`, after `N8N_WEBHOOK_SECRET`, add:

```python
ASSISTANT_N8N_WEBHOOK_URL = os.getenv("ASSISTANT_N8N_WEBHOOK_URL", "")
ASSISTANT_N8N_TIMEOUT_SECONDS = int(os.getenv("ASSISTANT_N8N_TIMEOUT_SECONDS", "12"))
```

In `.env.example`, append:

```dotenv

# Shared n8n integration for Messenger tools and website Assistant
N8N_WEBHOOK_SECRET=
ASSISTANT_N8N_WEBHOOK_URL=
ASSISTANT_N8N_TIMEOUT_SECONDS=12
```

- [ ] **Step 4: Create `widget/ai_client.py`**

```python
import requests
from django.conf import settings

from messenger.ai_tools import DEFAULT_AI_FALLBACK_MESSAGE


class AssistantUnavailable(Exception):
    pass


def fallback_message_for(ai_settings):
    return ai_settings.fallback_message or DEFAULT_AI_FALLBACK_MESSAGE


def call_assistant_webhook(clinic, message, history, session_id):
    webhook_url = getattr(settings, "ASSISTANT_N8N_WEBHOOK_URL", "")
    if not webhook_url:
        raise AssistantUnavailable("Assistant n8n webhook URL is not configured.")
    headers = {}
    secret = getattr(settings, "N8N_WEBHOOK_SECRET", "")
    if secret:
        headers["X-N8N-Webhook-Secret"] = secret
    response = requests.post(
        webhook_url,
        json={"channel": "widget", "clinic_id": clinic.id, "clinic_slug": clinic.slug, "message": message, "history": history[-10:], "session_id": session_id},
        headers=headers,
        timeout=getattr(settings, "ASSISTANT_N8N_TIMEOUT_SECONDS", 12),
    )
    response.raise_for_status()
    data = response.json()
    reply = (data.get("reply") or data.get("message") or "").strip()
    if not reply:
        raise AssistantUnavailable("Assistant n8n webhook returned an empty reply.")
    return reply
```

- [ ] **Step 5: Route widget free text to AI**

In `widget/views.py`, add imports:

```python
import requests
from clinics.models import Clinic, ClinicAISettings
from widget.ai_client import AssistantUnavailable, call_assistant_webhook, fallback_message_for
```

Add helpers before `chat_step`:

```python
def _widget_chat_history(request, clinic):
    return request.session.get(f"widget_chat_history_{clinic.id}", [])


def _save_widget_chat_history(request, clinic, history):
    request.session[f"widget_chat_history_{clinic.id}"] = history[-10:]
```

Inside `chat_step`, after `action`, `value`, and `state` are read, add:

```python
    if action == "text_input" and value and state == "greeting":
        ai_settings, _ = ClinicAISettings.objects.get_or_create(clinic=clinic)
        if not ai_settings.is_ai_enabled:
            message = fallback_message_for(ai_settings)
            return JsonResponse({"state": state, "message": message, "options": [{"label": "Book an appointment", "value": "start_booking"}], "next_action": "select_option"})
        history = _widget_chat_history(request, clinic)
        if not request.session.session_key:
            request.session.create()
        try:
            reply = call_assistant_webhook(clinic, value, history, request.session.session_key)
        except (AssistantUnavailable, requests.RequestException, ValueError):
            reply = fallback_message_for(ai_settings)
        history.extend([{"role": "user", "content": value}, {"role": "assistant", "content": reply}])
        _save_widget_chat_history(request, clinic, history)
        return JsonResponse({"state": state, "message": reply, "options": [{"label": "Book an appointment", "value": "start_booking"}], "next_action": "select_option"})
```

- [ ] **Step 6: Ensure CSRF token is always present**

In `templates/widget/widget.html`, add this hidden token near the top of `<main>`:

```html
  <input type="hidden" name="csrfmiddlewaretoken" value="{{ csrf_token }}">
```

- [ ] **Step 7: Verify widget tests**

Run: `.\env\Scripts\python -m pytest widget/tests.py -v`

Expected: PASS and existing guided booking tests still pass.

- [ ] **Step 8: Commit**

```bash
git add config/settings.py .env.example widget/ai_client.py widget/views.py templates/widget/widget.html widget/tests.py
git commit -m "feat: route widget assistant through n8n"
```

---

### Task 5: Create The Widget Assistant n8n Workflow

**Files/Systems:**
- Create in n8n project: `Widget Assistant AI` workflow
- Optional repo export: `n8n_widget_assistant_workflow.json`

- [ ] **Step 1: Inspect existing n8n workflow**

Use n8n workflow search/details tooling or existing workflow export files to identify the current Messenger model node, credentials, and Django tool-call pattern.

Expected: know the working Messenger provider/model node and reusable HTTP Request node settings.

- [ ] **Step 2: Create workflow**

Create a workflow named `Widget Assistant AI` with this input/output contract:

```json
{
  "input": {
    "channel": "widget",
    "clinic_slug": "demo-clinic",
    "clinic_id": 1,
    "message": "Can I book tomorrow?",
    "history": [],
    "session_id": "django-session-key"
  },
  "output": {
    "reply": "Yes, I can help with that. Which service would you like to book?"
  }
}
```

Workflow nodes:

- Webhook trigger accepting POST from Django.
- HTTP Request to `/messenger/ai/widget/context/` with `clinic_slug`.
- AI/model node using the same credential/model style as the working Messenger workflow.
- HTTP tool calls as needed to `/messenger/ai/widget/services/`, `/messenger/ai/widget/availability/`, and `/messenger/ai/widget/book/`.
- Respond to Webhook node returning `{ "reply": "..." }`.

Each Django tool HTTP Request must include:

```http
X-N8N-Webhook-Secret: {{$env.N8N_WEBHOOK_SECRET}}
Content-Type: application/json
```

- [ ] **Step 3: Configure prompt rules**

Use shared instructions from Django context plus these wrapper rules:

```text
You are replying inside the website booking widget. Keep replies concise and friendly.
Use clinic context JSON and shared AI instructions from Django as the source of truth.
For booking, collect service, date/time, full name, and phone in conversation.
Before claiming availability, call the availability tool.
Before booking, summarize service, local date/time, full name, and phone, then ask for explicit confirmation.
Only call the booking tool after explicit confirmation.
Return only the patient-facing reply text in the webhook response field named reply.
```

- [ ] **Step 4: Validate workflow manually**

Trigger the workflow with:

```json
{
  "channel": "widget",
  "clinic_slug": "demo-clinic",
  "clinic_id": 1,
  "message": "What services do you offer?",
  "history": [],
  "session_id": "manual-test"
}
```

Expected response:

```json
{
  "reply": "..."
}
```

- [ ] **Step 5: Configure Django environment**

Set `ASSISTANT_N8N_WEBHOOK_URL` to the production webhook URL for the new n8n workflow and ensure `N8N_WEBHOOK_SECRET` matches between Django and n8n.

- [ ] **Step 6: Commit optional export**

```bash
git add n8n_widget_assistant_workflow.json
git commit -m "chore: add widget assistant n8n workflow export"
```

---

### Task 6: End-To-End Verification

**Files:**
- Modify only files that fail verification from previous tasks.

- [ ] **Step 1: Run migrations and Django check**

Run: `.\env\Scripts\python manage.py makemigrations --check --dry-run`

Expected: no model changes detected.

Run: `.\env\Scripts\python manage.py migrate`

Expected: all migrations applied.

Run: `.\env\Scripts\python manage.py check`

Expected: `System check identified no issues`.

- [ ] **Step 2: Run targeted tests**

Run: `.\env\Scripts\python -m pytest messenger/tests.py widget/tests.py dashboard/tests.py -v`

Expected: PASS.

- [ ] **Step 3: Run full test suite**

Run: `.\env\Scripts\python -m pytest -v`

Expected: PASS.

- [ ] **Step 4: Manual browser verification**

Start server:

```bash
.\env\Scripts\python manage.py runserver
```

Verify:

- Owner can open Messenger settings and edit the shared prompt without a Messenger connection.
- Unchecking `Enable AI replies` makes both Messenger AI tools and widget chat return fallback.
- Widget `Chat with Assistant` sends free text and displays the n8n reply.
- Widget guided `Book an Appointment` still books through existing flow.
- Public widget HTML does not contain `N8N_WEBHOOK_SECRET`, model credentials, or provider API keys.

- [ ] **Step 5: Inspect git changes**

Run: `git status --short`

Expected: only intended source, migration, tests, docs, and optional workflow export are modified.

Run: `git diff --stat`

Expected: no unrelated `db.sqlite3`, deployment scripts, or local n8n debug files staged.

- [ ] **Step 6: Final cleanup commit**

```bash
git add clinics messenger widget dashboard config .env.example docs/superpowers
git commit -m "test: verify widget assistant ai integration"
```

---

## Self-Review Notes

- Spec coverage: tasks cover shared clinic settings, disabled fallback behavior, widget-to-Django-to-n8n flow, n8n settings, widget-scoped AI tools, tenant scoping, tests, and non-goals.
- Scope: this remains one vertical implementation because each task supports the single user-facing feature: AI-powered widget Assistant sharing Messenger config.
- Risk control: browser never receives n8n secrets or model credentials; all booking remains server/tool mediated and requires explicit confirmation.
