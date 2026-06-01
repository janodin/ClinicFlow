# Combined Messenger And Widget AI Bridge Design

## Goal

Simplify the active `ClinicFlow Messenger + Widget AI Bridge` n8n workflow so Messenger and website widget AI share one AI Agent, one model node, one memory node, and one set of booking tools. Clinic admins or operators should only need to configure the model once while Messenger and Widget keep their channel-specific input and reply behavior.

## Current State

The active n8n workflow already contains both channels, but it still duplicates most AI logic:

- Messenger path: Meta webhook, Messenger normalization, Messenger clinic context, Messenger AI Agent, Messenger model, Messenger memory, Messenger tools, Facebook reply.
- Widget path: widget webhook, widget normalization, widget clinic context, Widget AI Agent, widget model, widget memory, widget tools, widget JSON response.

Django already shares clinic AI settings through `ClinicAISettings`, and keeps safe booking operations inside existing tool endpoints.

## Approved Direction

Keep separate webhook triggers and final output handling, but merge the middle of the workflow into one shared AI core.

The workflow should keep:

- Meta webhook verification for Messenger setup.
- Meta Messenger POST webhook for Messenger messages.
- Widget Assistant POST webhook for website chat messages.
- Facebook Graph API reply output for Messenger.
- Respond-to-webhook JSON output for Widget.

The workflow should merge:

- Messenger AI Agent and Widget AI Agent into one shared AI Agent.
- Messenger model and Widget model into one shared chat model node.
- Messenger memory and Widget memory into one shared memory node.
- Channel-specific service, availability, and booking tools into shared channel-aware tools.

## Internal Payload

Both channel entry paths should normalize into one canonical item before the shared AI nodes:

```json
{
  "channel": "messenger|widget",
  "message": "user text",
  "session_key": "messenger:PAGE_ID:PSID or widget:CLINIC_SLUG:SESSION_ID",
  "page_id": "Messenger page ID when channel is messenger",
  "psid": "Messenger sender ID when channel is messenger",
  "clinic_slug": "Widget clinic slug when channel is widget"
}
```

The shared AI nodes must read only from this canonical item and the normalized clinic context. They should not reference old channel-specific node names such as `Normalize Messenger Event` or `Normalize Widget Request` once the flow enters the shared core.

## Context Lookup

Keep context lookup channel-specific for this change because Django currently exposes separate safe contracts:

- Messenger context uses `POST /messenger/ai/context/` with `page_id`.
- Widget context uses `POST /messenger/ai/widget/context/` with `clinic_slug`.

After the context response returns, normalize both responses into one shared context shape for the shared AI Agent. This avoids over-generalizing the Django API while still removing n8n AI duplication.

## Shared AI Agent

The shared AI Agent should receive:

- The normalized user message.
- Shared clinic context JSON from Django.
- Shared clinic AI instructions from `ClinicAISettings`.
- Channel-specific behavior rules.

Channel rules:

- Messenger replies must be plain Facebook Messenger text and stay within Messenger-safe length limits.
- Widget replies should be concise, friendly, and suitable for the existing booking widget chat panel.
- Both channels must use Django tools for service matching, availability, and booking.
- Both channels must ask for explicit confirmation before creating an appointment.
- The AI must not expose secrets, invent clinic data, give medical diagnosis, or create appointments without tool validation.

## Shared Memory

Use one memory node with a channel-prefixed key:

- Messenger: `messenger:{page_id}:{psid}`.
- Widget: `widget:{clinic_slug}:{session_id}`.

Widget memory must not fall back to only `clinic_slug`, because separate visitors to the same clinic could share conversation memory. If a widget request lacks a usable `session_id`, the workflow should either use a stateless unique fallback for that request or return the safe fallback response.

## Shared Tools

Use one set of shared AI tools:

- `match_services`
- `check_availability`
- `book_confirmed_appointment`

Each tool should choose the existing Django endpoint based on `channel`:

- Messenger calls `/messenger/ai/services/`, `/messenger/ai/availability/`, and `/messenger/ai/book/` with `page_id` injected from the normalized workflow item.
- Widget calls `/messenger/ai/widget/services/`, `/messenger/ai/widget/availability/`, and `/messenger/ai/widget/book/` with `clinic_slug` injected from the normalized workflow item.

The AI may provide only booking arguments such as service, requested date/time, patient name, phone, email, reason, and confirmation. The AI must not provide tenant identifiers. Tenant identifiers must come from the normalized workflow context.

## Output Routing

After the shared AI Agent returns text:

- Messenger routes to a Messenger formatter and sends the reply through Facebook Graph API with the page token from Django context.
- Widget routes to a widget formatter and returns `{ "reply": "..." }` through the webhook response node.

Both formatters should strip model reasoning tags, trim blank output, apply safe length limits, and use the clinic fallback message when the AI result is empty.

## Security And Tenant Scoping

- Keep all clinic resolution and booking validation in Django.
- Keep `X-N8N-Webhook-Secret` on all n8n-to-Django tool calls.
- Do not expose model credentials or n8n secrets to the browser.
- Tool nodes must inject `page_id` or `clinic_slug` from the normalized workflow item, not from AI-generated values.
- Existing Django booking logic must continue to enforce active clinic scoping, active services, slot validation, patient phone matching, explicit confirmation, and double-booking prevention.

## Error Handling

- Invalid Messenger payloads should stop without sending a reply.
- Invalid Widget payloads should return the safe widget fallback response.
- If clinic context is missing, use the generic safe fallback message. If clinic context exists but AI is disabled, use the configured clinic fallback message.
- If the model node is not configured, the workflow should fail safely and not create appointments.
- If a Django tool call fails, the assistant should apologize and suggest contacting the clinic directly.

## Testing And Verification

Manual n8n verification should cover:

- Messenger message reaches the shared AI Agent and receives a Facebook text reply.
- Widget message reaches the same shared AI Agent and returns widget JSON.
- Changing the shared model node changes the model for both channels.
- Messenger and Widget use separate memory keys.
- Messenger service, availability, and booking tools still send `page_id` from workflow context.
- Widget service, availability, and booking tools still send `clinic_slug` from workflow context.
- Appointment creation still requires explicit confirmation.

Django regression verification should include existing Messenger and Widget AI tests, especially tenant scoping, fallback behavior, n8n secret validation, and booking validation.

## Non-Goals

- Do not add a patient portal, medical records, prescriptions, inventory, online payments, or marketplace booking.
- Do not replace Django templates, Tailwind, HTMX, or the existing widget UI.
- Do not add a separate frontend.
- Do not change the public booking form behavior.
- Do not let AI create appointments without explicit confirmation.
