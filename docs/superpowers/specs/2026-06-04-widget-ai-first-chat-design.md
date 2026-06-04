# Widget AI-First Chat Design

## Goal

Make the widget `Chat with Assistant` experience work like Messenger AI mode: AI-first, free-text booking and clinic Q&A through the shared n8n AI agent and tool flow, with appointment creation allowed only after explicit patient confirmation.

The separate widget `Book an Appointment` guided flow remains available and unchanged for patients who prefer a deterministic button/form flow.

## Current State

The widget currently has two booking-capable paths:

- `Book an Appointment` in `templates/widget/widget.html`, a deterministic frontend booking flow that posts to Django widget endpoints.
- `Chat with Assistant`, a Django-backed chat state machine in `widget.views.chat_step()` with service/date/time/info/confirm states.

The widget chat already calls n8n for free-text `text_input` messages when `ClinicAISettings.is_ai_enabled` is true. However, deterministic Django chat states still own most booking interactions. That makes the widget chat different from Messenger AI mode, where the shared n8n AI agent handles natural-language booking using tools.

ClinicFlow already has the pieces needed for AI-first widget chat:

- `widget.ai_client.call_assistant_webhook()` sends widget messages to `ASSISTANT_N8N_WEBHOOK_URL`.
- `n8n_combined_messenger_widget_ai_bridge.ts` has a widget webhook path and shared AI agent.
- Widget AI tools already exist: `match_widget_services`, `check_widget_availability`, and `book_widget_confirmed_appointment`.
- Widget AI tool endpoints resolve clinics by `clinic_slug`, enforce AI availability where appropriate, and rely on server-side booking validation.

## Approved Direction

Use the existing shared n8n AI bridge as the main engine for widget chat when website Assistant AI is enabled.

Approved choices:

- Widget chat target behavior: AI-first chat.
- Booking authority: AI can create appointments after explicit patient confirmation.
- Widget home entry points: keep both `Book an Appointment` and `Chat with Assistant`.
- Implementation direction: shared n8n AI-first widget chat.

## Widget UX

The widget home keeps both entry points:

- `Book an Appointment`: existing deterministic guided booking flow.
- `Chat with Assistant`: AI-first chat for booking and questions.

The chat conversation should feel natural:

- The patient can ask clinic, service, FAQ, and booking questions.
- The patient can write requests such as `I need a blood test Monday morning` or `Can I book tomorrow at 9:30?`.
- The assistant asks for only missing required details: service, date/time, full name, phone, and optional email or reason if needed.
- Before creating an appointment, the assistant summarizes service, clinic, date/time, and patient identity, then asks for explicit confirmation.
- After booking, the assistant returns the reference code and offers natural next steps.

The existing FAQ tab may remain as a non-AI shortcut. The conversation tab should not enter the old Django guided chat state machine for AI-enabled clinics.

## Runtime Data Flow

For AI-enabled clinics:

1. The patient opens `Chat with Assistant`.
2. The widget requests `chat_step?action=init` for an initial greeting and local UI suggestion chips.
3. Patient messages are sent to Django via `chat_step` with CSRF protection.
4. Django resolves the public clinic from `clinic_slug` and loads `ClinicAISettings`.
5. Django sends the patient message, recent history, channel, clinic slug, and session ID to `ASSISTANT_N8N_WEBHOOK_URL` through `call_assistant_webhook()`.
6. n8n normalizes the widget request and loads widget clinic context through Django.
7. n8n routes widget messages through the shared AI agent when `context.ai.is_ai_enabled` is true.
8. The shared AI agent calls widget-safe tools as needed.
9. n8n returns `{ reply: "..." }` to Django.
10. Django appends the exchange to widget chat history and returns a compatible JSON response to the browser.

For AI-disabled clinics:

1. `Chat with Assistant` does not call n8n.
2. Django returns the configured fallback message or default safe fallback.
3. The response should direct the patient toward the separate guided `Book an Appointment` flow.

The separate `Book an Appointment` widget flow remains unchanged.

## API Response Contract

Keep the current widget frontend response shape so the template JavaScript can remain small:

```json
{
  "state": "ai",
  "message": "Assistant reply text",
  "options": [],
  "next_action": "text_input"
}
```

Initial chat may return local UI suggestion chips using the existing `options` shape, but those chips are helpers only. They are not AI quick replies and are not required for every assistant response. They should send natural text to the AI, not enter deterministic booking states.

For example, clicking a `Book an appointment` suggestion should send a message such as `I want to book an appointment` through the AI path.

AI responses in the first version should return plain text only. Structured appointment cards, rich slot cards, or persistent AI quick replies are not part of this design.

## n8n Design

Use the existing combined bridge rather than creating a new widget-only workflow.

The shared agent already has channel-aware tools:

- `match_services` calls widget or Messenger endpoints based on channel.
- `check_availability` calls widget or Messenger endpoints based on channel.
- `book_confirmed_appointment` calls widget or Messenger endpoints based on channel.

The shared agent prompt should continue to require:

- Use tools for services, availability, and booking.
- Ask for explicit confirmation before booking.
- Do not invent clinic data, services, slots, prices, or booking results.
- Do not provide medical diagnosis or treatment recommendations.
- Keep widget replies concise and friendly.

Implementation should strengthen n8n source tests to lock the widget channel behavior into the combined bridge.

## Safety And Tenant Scoping

The AI-first widget chat must preserve the existing tenant and booking safeguards:

- Resolve clinics through active public `clinic_slug` only.
- Never trust browser-submitted service, slot, status, source, patient, or ownership values without server-side validation.
- Use `match_widget_services`, `check_widget_availability`, and `book_widget_confirmed_appointment` for AI booking operations.
- Let `_process_guest_booking()` remain the final appointment creation gate.
- Preserve patient phone matching, slot regeneration, double-booking prevention, clinic row locking, and cancelled-slot behavior.
- Keep `Appointment.SOURCE_CHAT_WIDGET` for AI-created widget chat appointments.
- Require explicit `confirmed=true` only after the AI has summarized appointment details and the patient confirms.
- Return fallback text on n8n/model/tool failure. Do not create partial appointments.
- Do not expose n8n secrets, model credentials, page tokens, webhook secrets, or clinic-private data in templates, logs, or responses.

## Error Handling

- AI disabled: return configured fallback and do not call n8n.
- n8n URL missing: return safe fallback.
- n8n request failure: return safe fallback.
- n8n empty response: return safe fallback.
- Tool reports missing service, unavailable slot, invalid date, invalid patient info, or booking conflict: assistant explains the issue and asks for corrected information or offers alternatives.
- Public clinic unavailable, inactive, or onboarding-required: existing widget public access rules continue to return not found.

## Testing Strategy

Add or update tests for:

- AI-enabled `chat_step` text messages route through n8n and return `state: "ai"`.
- AI-enabled `chat_step?action=init` does not enter `select_service`, `select_date`, `select_time`, `collect_info`, or `confirm` states.
- A `Book an appointment` chat suggestion sends natural text through n8n rather than entering the old state machine.
- AI-disabled `chat_step` returns fallback and does not call n8n.
- Widget chat history is passed to n8n and capped.
- Widget AI tools continue to reject disabled AI where applicable.
- `book_widget_confirmed_appointment` creates `SOURCE_CHAT_WIDGET` only after explicit confirmation.
- Existing guided widget booking tests still pass.
- n8n source tests prove the widget path uses the shared AI agent, widget context, widget tools, and explicit confirmation rule.

Run at minimum:

- `python -m pytest widget/tests.py`
- `python -m pytest messenger/tests.py tests/test_n8n_combined_bridge_source.py`
- `python manage.py check`

## Non-Goals

- Do not remove the separate guided `Book an Appointment` widget flow.
- Do not add patient accounts, patient portals, medical records, prescriptions, inventory, online payments, or marketplace booking.
- Do not add a new widget response-mode toggle in this phase.
- Do not create a separate frontend framework or replace Django templates, Tailwind CSS, HTMX, Alpine.js, or n8n.
- Do not add rich structured AI appointment cards in the first implementation.
- Do not bypass existing server-side booking validation.
