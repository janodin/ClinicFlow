# Default Fallback Message Design

## Goal

Give the shared Assistant fallback message the same default-message treatment as the shared AI prompt.

New shared AI settings should start with a safe default fallback message, and clinic admins should be able to restore that default from the Assistant settings page.

## Current State

`ClinicAISettings.instructions` defaults to `DEFAULT_MESSENGER_AI_PROMPT` and the Assistant settings page exposes a `Restore default prompt` button backed by `default_ai_prompt`.

`ClinicAISettings.fallback_message` currently defaults to an empty string. Runtime code in the website widget and Messenger context substitutes a hard-coded safe fallback when the saved value is blank.

## Approved Direction

Add a shared default fallback message constant and use it consistently for new settings, runtime fallback resolution, and the Assistant settings restore control.

Approved choices:

- New `ClinicAISettings` rows should store the default fallback message by default.
- Existing custom fallback messages should stay unchanged.
- Runtime behavior should still return the same safe text when AI is disabled or unavailable.
- The Assistant settings page should add a `Restore default fallback` button beside the fallback message field.

## Data Model

Define one shared fallback default constant close to the existing AI prompt default so both channels can import it without duplicating text.

Update `ClinicAISettings.fallback_message` to default to that constant. This requires a Django migration that changes the field default only. It should not overwrite existing database values.

Legacy `MessengerAISettings.fallback_message` can remain blank by default because the shared `ClinicAISettings` model is the active owner of website and Messenger AI settings.

## Runtime Flow

Keep runtime fallback behavior explicit:

- Website widget fallback helper returns `ai_settings.fallback_message` or the shared default fallback constant.
- Messenger AI context returns `ai_settings.fallback_message` or the shared default fallback constant.
- Messenger AI fallback action sends `ai_settings.fallback_message` or the shared default fallback constant.

This preserves the current safe text for any existing settings row where `fallback_message` is blank.

## Assistant Settings UI

Pass `default_ai_fallback_message` into the Assistant settings context.

Add a hidden textarea containing the default fallback text, mirroring `default-ai-prompt-value`.

Add a `Restore default fallback` button in the fallback message field header. The button should copy the hidden default value into the fallback textarea and focus it. Keep the existing `cf-btn cf-btn-secondary cf-btn-sm` styling and Lucide restore icon.

## Testing Strategy

Update targeted tests to cover:

- Assistant settings page renders the default fallback text and `Restore default fallback` button.
- `ClinicAISettings.objects.create(clinic=clinic)` stores the shared default fallback message.
- Widget fallback still returns the default fallback text when an existing row has a blank fallback value.
- Messenger AI context still returns the default fallback text when an existing row has a blank fallback value.

Run at minimum after implementation:

- `python -m pytest dashboard/tests.py -k "assistant_settings_page_shows_shared_ai_prompt_form or assistant_settings_page_creates_default_shared_ai_settings" -q`
- `python -m pytest messenger/tests.py -k "clinic_ai_settings_defaults or build_ai_context" -q`
- `python -m pytest widget/tests.py::WidgetTests::test_chat_step_returns_default_fallback_when_webhook_missing -q`
- `python manage.py makemigrations --check --dry-run`
- `python manage.py check`

Because this changes a Django model default, also run `python manage.py makemigrations` during implementation and include the generated migration.

## Security And Tenant Boundaries

The change does not alter clinic scoping, assistant webhook trust, booking validation, Messenger webhook handling, or public widget access rules.

The fallback text is static, non-secret, and safe to render in the authenticated clinic settings page.

## Non-Goals

- Do not change the AI prompt content.
- Do not migrate or overwrite existing saved fallback messages.
- Do not change Messenger quick-reply behavior.
- Do not change appointment booking, slot validation, patient matching, or double-booking prevention.
- Do not add a patient portal, payments, medical records, or new frontend stack.
