# Default Fallback Message Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Assistant fallback messages the same default-value and restore-button behavior as the shared AI prompt.

**Architecture:** Add one shared fallback default constant beside the existing Messenger AI prompt default. Use that constant as the `ClinicAISettings.fallback_message` model default, runtime fallback source, Assistant settings context value, and UI restore source. Generate a Django migration that changes only the field default and does not overwrite existing rows.

**Tech Stack:** Django models/forms/templates, Django migrations, pytest, Tailwind/Alpine in existing templates.

---

## Scope Check

This is one focused subsystem: shared Assistant fallback defaults. It touches the shared AI settings model, channel fallback helpers, Assistant settings UI, and targeted tests only.

Repository instructions override the skill's normal frequent-commit guidance. Do not commit these changes unless the user explicitly asks for a commit.

## File Structure

- Modify: `messenger/defaults.py` - owns shared AI text constants used by both channels.
- Modify: `clinics/models.py` - applies the shared fallback constant as the `ClinicAISettings.fallback_message` default.
- Create: `clinics/migrations/0012_alter_clinicaisettings_fallback_message.py` - generated migration for the field default change.
- Modify: `widget/ai_client.py` - uses the shared fallback constant for website Assistant fallback resolution.
- Modify: `messenger/ai_tools.py` - uses the shared fallback constant for Messenger and widget AI context payloads.
- Modify: `dashboard/views.py` - passes the default fallback message to the Assistant settings template.
- Modify: `templates/dashboard/assistant_settings.html` - adds the hidden default fallback value and restore button.
- Modify: `dashboard/tests.py` - locks the Assistant settings UI and default-row behavior.
- Modify: `messenger/tests.py` - locks `ClinicAISettings` default fallback and Messenger context fallback behavior.
- Modify: `widget/tests.py` - locks website Assistant blank-value runtime fallback behavior.

### Task 1: Write Dashboard And Model Default Tests

**Files:**
- Modify: `dashboard/tests.py:684-729`

- [ ] **Step 1: Update the Assistant settings page test to expect default fallback UI**

In `dashboard/tests.py`, update `test_assistant_settings_page_shows_shared_ai_prompt_form` so the imports and assertions include `DEFAULT_AI_FALLBACK_MESSAGE` and the restore button:

```python
@pytest.mark.django_db
def test_assistant_settings_page_shows_shared_ai_prompt_form(clinic_setup, client):
    from clinics.models import ClinicAISettings
    from messenger.defaults import DEFAULT_AI_FALLBACK_MESSAGE, DEFAULT_MESSENGER_AI_PROMPT

    clinic, service, user = clinic_setup
    ClinicAISettings.objects.create(
        clinic=clinic,
        is_ai_enabled=False,
        instructions="Use a warm clinic tone.",
        fallback_message="Please call the clinic.",
    )
    client.force_login(user)

    response = client.get(reverse("dashboard:assistant_settings"))

    assert response.status_code == 200
    assert b">Assistant</h1>" in response.content
    assert b"Patient Assistant" not in response.content
    assert b"Shared Assistant Settings" in response.content
    assert b"Used by both the website Assistant and Facebook Messenger" in response.content
    assert b"Prompt / Instructions" in response.content
    assert b'name="is_ai_enabled"' in response.content
    assert b'name="instructions"' in response.content
    assert b'name="fallback_message"' in response.content
    assert b"Restore default prompt" in response.content
    assert b"Restore default fallback" in response.content
    assert DEFAULT_MESSENGER_AI_PROMPT.splitlines()[0].encode() in response.content
    assert DEFAULT_AI_FALLBACK_MESSAGE.encode() in response.content
    assert b"Use a warm clinic tone." in response.content
    assert b"Please call the clinic." in response.content
    assert b"Website Booking Widget" in response.content
    assert b"widget_behavior_instructions" not in response.content
```

- [ ] **Step 2: Update the default settings creation test**

In `dashboard/tests.py`, update `test_assistant_settings_page_creates_default_shared_ai_settings` so it proves new settings rows store the default fallback message:

```python
@pytest.mark.django_db
def test_assistant_settings_page_creates_default_shared_ai_settings(clinic_setup, client):
    from clinics.models import ClinicAISettings
    from messenger.defaults import DEFAULT_AI_FALLBACK_MESSAGE, DEFAULT_MESSENGER_AI_PROMPT

    clinic, service, user = clinic_setup
    client.force_login(user)

    response = client.get(reverse("dashboard:assistant_settings"))

    assert response.status_code == 200
    assert b"Shared Assistant Settings" in response.content
    assert DEFAULT_MESSENGER_AI_PROMPT.splitlines()[0].encode() in response.content
    assert DEFAULT_AI_FALLBACK_MESSAGE.encode() in response.content
    settings = ClinicAISettings.objects.get(clinic=clinic)
    assert settings.fallback_message == DEFAULT_AI_FALLBACK_MESSAGE
```

- [ ] **Step 3: Run dashboard tests and verify they fail for the missing behavior**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest dashboard/tests.py -k "assistant_settings_page_shows_shared_ai_prompt_form or assistant_settings_page_creates_default_shared_ai_settings" -q }
```

Expected: FAIL because `DEFAULT_AI_FALLBACK_MESSAGE` is not exported from `messenger.defaults`, the restore button is not rendered, and the model default is still blank.

### Task 2: Write Runtime Fallback Tests

**Files:**
- Modify: `messenger/tests.py:1154-1218`
- Modify: `widget/tests.py:605-618`

- [ ] **Step 1: Update `ClinicAISettings` default assertions**

In `messenger/tests.py`, update `test_clinic_ai_settings_defaults_and_unique_clinic`:

```python
@pytest.mark.django_db
def test_clinic_ai_settings_defaults_and_unique_clinic():
    from clinics.models import ClinicAISettings
    from messenger.defaults import DEFAULT_AI_FALLBACK_MESSAGE, DEFAULT_MESSENGER_AI_PROMPT

    clinic, connection = _create_messenger_clinic("owner_clinic_ai_defaults", "PAGE-CLINIC-AI")
    settings = ClinicAISettings.objects.create(clinic=clinic)

    assert settings.clinic == clinic
    assert settings.is_ai_enabled is True
    assert settings.messenger_response_mode == ClinicAISettings.MESSENGER_MODE_QUICK_REPLIES
    assert settings.safe_messenger_response_mode == ClinicAISettings.MESSENGER_MODE_QUICK_REPLIES
    assert settings.instructions == DEFAULT_MESSENGER_AI_PROMPT
    assert settings.fallback_message == DEFAULT_AI_FALLBACK_MESSAGE
    assert str(settings) == f"ClinicAISettings({clinic.name})"

    with pytest.raises(IntegrityError):
        ClinicAISettings.objects.create(clinic=clinic)
```

- [ ] **Step 2: Update Messenger context default assertions**

In `messenger/tests.py`, update `test_build_ai_context_uses_default_prompt_when_settings_missing`:

```python
@pytest.mark.django_db
def test_build_ai_context_uses_default_prompt_when_settings_missing():
    from messenger.ai_tools import build_ai_context
    from messenger.defaults import DEFAULT_AI_FALLBACK_MESSAGE, DEFAULT_MESSENGER_AI_PROMPT

    _clinic, _connection = _create_messenger_clinic("owner_ai_default_context", "PAGEAI_DEFAULT")

    result = build_ai_context("PAGEAI_DEFAULT")

    assert result["found"] is True
    assert result["ai"]["instructions"] == DEFAULT_MESSENGER_AI_PROMPT
    assert result["ai"]["fallback_message"] == DEFAULT_AI_FALLBACK_MESSAGE
```

- [ ] **Step 3: Update website widget blank fallback assertion**

In `widget/tests.py`, update `test_chat_step_returns_default_fallback_when_webhook_missing`:

```python
@override_settings(ASSISTANT_N8N_WEBHOOK_URL="", N8N_WEBHOOK_SECRET="secret")
def test_chat_step_returns_default_fallback_when_webhook_missing(self):
    from messenger.defaults import DEFAULT_AI_FALLBACK_MESSAGE

    ClinicAISettings.objects.create(clinic=self.clinic, is_ai_enabled=True, fallback_message="")

    response = self.client.post(
        reverse("widget:chat_step", args=[self.clinic.slug]),
        {"action": "text_input", "value": "Hello"},
    )

    self.assertEqual(response.status_code, 200)
    data = response.json()
    self.assertEqual(data["state"], "ai")
    self.assertIn(DEFAULT_AI_FALLBACK_MESSAGE, data["message"])
    self.assertEqual(data["options"], [])
```

- [ ] **Step 4: Run runtime tests and verify they fail for the missing behavior**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest messenger/tests.py -k "clinic_ai_settings_defaults or build_ai_context_uses_default_prompt_when_settings_missing" -q }
```

Expected: FAIL because `DEFAULT_AI_FALLBACK_MESSAGE` is not exported from `messenger.defaults` and `ClinicAISettings.fallback_message` defaults to blank.

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest widget/tests.py::WidgetTests::test_chat_step_returns_default_fallback_when_webhook_missing -q }
```

Expected: FAIL because the test imports the missing shared constant.

### Task 3: Add Shared Constant And Runtime Usage

**Files:**
- Modify: `messenger/defaults.py:1-25`
- Modify: `clinics/models.py:8,126-127`
- Modify: `widget/ai_client.py:1-11`
- Modify: `messenger/ai_tools.py:12-15,34-45`

- [ ] **Step 1: Add shared fallback default constant**

In `messenger/defaults.py`, add this constant after the existing `DEFAULT_MESSENGER_AI_PROMPT` block:

```python
DEFAULT_AI_FALLBACK_MESSAGE = "Sorry, the assistant is unavailable right now. You can still book an appointment using the booking form."
```

- [ ] **Step 2: Use the shared default in `ClinicAISettings`**

In `clinics/models.py`, update the import and fallback field:

```python
from messenger.defaults import DEFAULT_AI_FALLBACK_MESSAGE, DEFAULT_MESSENGER_AI_PROMPT
```

```python
    instructions = models.TextField(blank=True, default=DEFAULT_MESSENGER_AI_PROMPT)
    fallback_message = models.TextField(blank=True, default=DEFAULT_AI_FALLBACK_MESSAGE)
```

- [ ] **Step 3: Use the shared default in the website widget AI client**

In `widget/ai_client.py`, replace the local constant with an import:

```python
import requests
from django.conf import settings

from messenger.defaults import DEFAULT_AI_FALLBACK_MESSAGE


class AssistantUnavailable(Exception):
    pass


def fallback_message_for(ai_settings):
    return ai_settings.fallback_message or DEFAULT_AI_FALLBACK_MESSAGE
```

Leave `call_assistant_webhook()` unchanged.

- [ ] **Step 4: Use the shared default in Messenger AI tools**

In `messenger/ai_tools.py`, update the defaults import and remove the local `DEFAULT_AI_FALLBACK_MESSAGE = ...` assignment:

```python
from .defaults import DEFAULT_AI_FALLBACK_MESSAGE, DEFAULT_MESSENGER_AI_PROMPT
```

Keep the existing payload fallback expressions unchanged:

```python
        "instructions": ai_settings.instructions or DEFAULT_MESSENGER_AI_PROMPT,
        "fallback_message": ai_settings.fallback_message or DEFAULT_AI_FALLBACK_MESSAGE,
```

```python
            "fallback_message": ai_settings.fallback_message or DEFAULT_AI_FALLBACK_MESSAGE,
```

- [ ] **Step 5: Run runtime tests and verify the backend behavior passes**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest messenger/tests.py -k "clinic_ai_settings_defaults or build_ai_context_uses_default_prompt_when_settings_missing" -q }
```

Expected: PASS.

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest widget/tests.py::WidgetTests::test_chat_step_returns_default_fallback_when_webhook_missing -q }
```

Expected: PASS.

### Task 4: Add Assistant Settings Restore Control

**Files:**
- Modify: `dashboard/views.py:24,1125-1136`
- Modify: `templates/dashboard/assistant_settings.html:23-98`

- [ ] **Step 1: Pass the default fallback message into the template context**

In `dashboard/views.py`, update the import:

```python
from messenger.defaults import DEFAULT_AI_FALLBACK_MESSAGE, DEFAULT_MESSENGER_AI_PROMPT
```

In `_assistant_settings_context()`, add the new context value:

```python
        "default_ai_prompt": DEFAULT_MESSENGER_AI_PROMPT,
        "default_ai_fallback_message": DEFAULT_AI_FALLBACK_MESSAGE,
```

- [ ] **Step 2: Add hidden fallback default source to the form**

In `templates/dashboard/assistant_settings.html`, add the hidden textarea immediately after `default-ai-prompt-value`:

```html
      <textarea id="default-ai-prompt-value" class="hidden" aria-hidden="true">{{ default_ai_prompt }}</textarea>
      <textarea id="default-ai-fallback-message-value" class="hidden" aria-hidden="true">{{ default_ai_fallback_message }}</textarea>
```

- [ ] **Step 3: Add the restore button beside the fallback field label**

In `templates/dashboard/assistant_settings.html`, replace the fallback field label block with this structure:

```html
      <div class="cf-field">
        <div class="mb-1 flex flex-wrap items-center justify-between gap-2">
          <label class="cf-label" for="{{ ai_form.fallback_message.id_for_label }}">{{ ai_form.fallback_message.label }}</label>
          <button
            type="button"
            class="cf-btn cf-btn-secondary cf-btn-sm"
            @click="const field = document.getElementById('{{ ai_form.fallback_message.id_for_label }}'); const source = document.getElementById('default-ai-fallback-message-value'); if (field && source) { field.value = source.value; field.focus(); }"
          >
            <i data-lucide="rotate-ccw" class="h-4 w-4"></i> Restore default fallback
          </button>
        </div>
        {{ ai_form.fallback_message }}
        <p class="mt-1 text-xs text-[var(--cf-muted)]">Shown in both channels when AI replies are disabled or unavailable.</p>
        {% if ai_form.fallback_message.errors %}
          <p class="text-sm text-red-600 mt-1">{{ ai_form.fallback_message.errors.0 }}</p>
        {% endif %}
      </div>
```

- [ ] **Step 4: Run dashboard tests and verify the UI behavior passes**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest dashboard/tests.py -k "assistant_settings_page_shows_shared_ai_prompt_form or assistant_settings_page_creates_default_shared_ai_settings" -q }
```

Expected: PASS.

### Task 5: Generate Migration And Run Final Verification

**Files:**
- Create: `clinics/migrations/0012_alter_clinicaisettings_fallback_message.py`

- [ ] **Step 1: Generate the Django migration**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python manage.py makemigrations }
```

Expected: Django creates `clinics/migrations/0012_alter_clinicaisettings_fallback_message.py` with one `AlterField` operation for `ClinicAISettings.fallback_message`.

The migration operation should match this shape, with Django's generated header preserved:

```python
operations = [
    migrations.AlterField(
        model_name="clinicaisettings",
        name="fallback_message",
        field=models.TextField(blank=True, default="Sorry, the assistant is unavailable right now. You can still book an appointment using the booking form."),
    ),
]
```

- [ ] **Step 2: Confirm there are no missing migrations**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python manage.py makemigrations --check --dry-run }
```

Expected: exit code 0 and `No changes detected`.

- [ ] **Step 3: Run targeted regression tests**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest dashboard/tests.py -k "assistant_settings_page_shows_shared_ai_prompt_form or assistant_settings_page_creates_default_shared_ai_settings" -q }
```

Expected: PASS.

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest messenger/tests.py -k "clinic_ai_settings_defaults or build_ai_context_uses_default_prompt_when_settings_missing" -q }
```

Expected: PASS.

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest widget/tests.py::WidgetTests::test_chat_step_returns_default_fallback_when_webhook_missing -q }
```

Expected: PASS.

- [ ] **Step 4: Run Django system checks**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python manage.py check }
```

Expected: exit code 0 and `System check identified no issues`.

- [ ] **Step 5: Inspect the final diff**

Run:

```powershell
git diff -- docs/superpowers/specs/2026-06-04-default-fallback-message-design.md docs/superpowers/plans/2026-06-04-default-fallback-message-implementation-plan.md messenger/defaults.py clinics/models.py clinics/migrations/0012_alter_clinicaisettings_fallback_message.py widget/ai_client.py messenger/ai_tools.py dashboard/views.py templates/dashboard/assistant_settings.html dashboard/tests.py messenger/tests.py widget/tests.py
```

Expected: diff contains only the approved fallback default, restore button, migration, and targeted tests. No unrelated files, secrets, database files, generated artifacts, or broad refactors should be included.

Do not commit unless the user explicitly asks for a commit.

## Self-Review

- Spec coverage: The plan covers shared constant creation, model default, migration, runtime fallback usage, Assistant settings context, restore UI, targeted tests, and final verification.
- Placeholder scan: No incomplete markers, deferred sections, or vague implementation instructions remain.
- Type consistency: The constant name is consistently `DEFAULT_AI_FALLBACK_MESSAGE`; the context key is consistently `default_ai_fallback_message`; the hidden textarea ID is consistently `default-ai-fallback-message-value`.
