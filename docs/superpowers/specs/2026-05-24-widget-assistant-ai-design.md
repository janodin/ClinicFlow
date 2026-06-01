# Widget Assistant AI Design

## Goal

Make the public widget's "Chat with Assistant" use AI through n8n, similar to the working Messenger AI flow, while sharing one AI prompt/configuration between Messenger and the widget Assistant.

## Approved Direction

Use a shared global n8n webhook for widget Assistant messages. Django remains the public entry point for the widget, performs clinic scoping and fallback handling, and sends AI requests to n8n server-to-server.

Create a shared clinic-level AI settings model so Messenger and widget Assistant both use the same AI enable switch, instructions, and fallback message.

## Shared AI Settings

Add a `ClinicAISettings` model linked directly to `Clinic` with these fields:

- `clinic`: one-to-one relationship to `Clinic`.
- `is_ai_enabled`: shared switch for Messenger and widget Assistant.
- `instructions`: shared prompt/instructions for both channels.
- `fallback_message`: shared fallback response when AI is disabled or unavailable.

Existing `MessengerAISettings` values should be migrated or copied into `ClinicAISettings` so current Messenger AI Prompt behavior is preserved. After this change, Messenger reads from `ClinicAISettings` instead of channel-specific AI settings.

The existing Messenger AI Prompt UI can remain the editing surface for now, but labels should make clear that these settings are shared by Messenger and the website Assistant.

## Disabled AI Behavior

When `is_ai_enabled` is unchecked:

- Messenger returns the configured `fallback_message`.
- Widget Assistant returns the same `fallback_message`.
- Django does not call n8n or any model provider.

If `fallback_message` is blank, use a safe default: "Sorry, the assistant is unavailable right now. You can still book an appointment using the booking form."

## Widget Data Flow

1. Patient opens the public widget and clicks "Chat with Assistant".
2. Widget posts the patient's message to Django through the existing widget chat endpoint or a new widget AI chat endpoint.
3. Django resolves the active clinic by `clinic_slug` and loads `ClinicAISettings`.
4. If AI is disabled, Django returns the fallback message immediately.
5. If AI is enabled, Django sends a server-to-server request to a shared global n8n webhook.
6. The n8n payload includes `channel=widget`, `clinic_slug`, `clinic_id`, current message, recent widget chat history, and a session identifier.
7. n8n calls Django AI tool endpoints for clinic context, services, availability, and booking.
8. n8n returns a concise assistant reply to Django.
9. Django returns that reply to the widget and stores recent conversation history in the Django session.
10. If n8n fails or times out, Django returns the shared fallback message and can still offer existing guided booking options.

## n8n Integration

Add configuration settings:

- `ASSISTANT_N8N_WEBHOOK_URL`: shared global webhook URL for website Assistant messages.
- `N8N_WEBHOOK_SECRET`: reused shared secret for Django-to-n8n and n8n-to-Django calls.
- `ASSISTANT_N8N_TIMEOUT_SECONDS`: short timeout for widget responsiveness.

The n8n workflow should be a separate workflow in the existing n8n project. It should use the same model-provider style already used for Messenger and call Django tools instead of trusting model-generated booking details.

## AI Tool Endpoints

Add or extend AI tool endpoints so widget workflows can operate by clinic identity instead of Facebook page identity.

Needed capabilities:

- Build clinic AI context by `clinic_slug` or `clinic_id`.
- Match services for a clinic.
- Check availability for a clinic service/date/time.
- Book an appointment only after explicit user confirmation.

These should reuse the same safe booking logic already used by Messenger and widget booking:

- Active clinic scoping.
- Active, non-archived services only.
- `generate_slots` for availability.
- `_process_guest_booking` for patient matching, slot validation, appointment creation, approval mode, and double-booking protection.

## Widget UI Behavior

Keep the current widget UI and conversation panel. The change should be behavioral, not a redesign.

Expected behavior:

- Existing quick options can remain for guided fallbacks.
- Free-text messages go to AI when enabled.
- Assistant replies render in the existing chat bubbles.
- Booking confirmation must still be explicit before an appointment is created.
- If AI is disabled or unavailable, show the shared fallback message and keep the regular booking form accessible.

## Security And Tenant Scoping

- Public widget requests must only resolve active clinics by slug.
- n8n tool endpoints must require `X-N8N-Webhook-Secret` and fail closed when the secret is missing or wrong.
- No API keys, model credentials, or n8n secrets should be exposed to widget templates or browser JavaScript.
- Widget payloads should send only the current message, recent history, and clinic/session identifiers needed by n8n.
- All service, FAQ, availability, and booking tool calls must be scoped to the resolved clinic.

## Error Handling

- AI disabled: return shared fallback message immediately.
- Missing shared AI settings: create a default `ClinicAISettings` record lazily with AI enabled, default instructions, and blank fallback; do not require a Messenger connection before the widget Assistant can work.
- n8n webhook URL missing: return fallback message.
- n8n timeout/error/invalid JSON: return fallback message and keep booking options available.
- Tool validation errors: return structured errors to n8n so the assistant can ask the patient for corrected information.

## Testing

Add tests for:

- Widget Assistant returns fallback without calling n8n when shared AI is disabled.
- Messenger also uses the shared fallback when shared AI is disabled.
- Widget Assistant calls n8n with clinic-scoped payload when AI is enabled.
- Widget Assistant does not expose secrets in public HTML or JSON responses.
- Widget AI context/services/availability/book endpoints are tenant-scoped.
- Booking through widget AI still uses slot validation and prevents double-booking.
- Existing guided widget booking still works.
- Existing Messenger AI tests still pass after migrating to shared settings.

## Non-Goals

- Do not add patient login or a patient portal.
- Do not expose model provider API keys in the browser.
- Do not create a full workflow builder in Django.
- Do not replace the existing booking form or widget design.
- Do not let AI create appointments without explicit confirmation.
