# Messenger AI Agent Design

## Goal

Replace the current Messenger booking state machine with a natural-language Facebook Messenger chatbot powered by an n8n AI Agent. Patients should type normal messages to the clinic Facebook Page, ask clinic questions, and book appointments without quick-reply buttons or a built-in click-to-start chat flow.

## Scope

Included:

- Natural-language clinic information replies through Facebook Messenger.
- Natural-language appointment booking through Facebook Messenger.
- Appointment creation only after explicit text confirmation from the user.
- Clinic-specific AI instructions stored in Django.
- n8n workflow design that keeps the model provider configurable so the model can be added later.
- Django tool endpoints that keep clinic scoping, availability, patient matching, and double-booking validation inside the existing app.

Excluded:

- Patient portal, medical records, prescriptions, inventory, payments, marketplace booking, or non-Messenger chat widgets.
- Document upload or retrieval-augmented knowledge ingestion in this phase.
- Direct booking without user confirmation.
- Messenger quick replies or postback-based booking for the new AI flow.

## Current State

Facebook currently sends page messages into n8n, and n8n forwards `page_id`, `psid`, `text`, and `postback` to Django at `/messenger/n8n-webhook/`. Django then calls `messenger.bot_engine.handle_message()`, which uses `MessengerSession.state` to drive a rigid booking flow with quick replies for service, date, time, patient info, and confirmation.

This design changes the n8n path so n8n owns the natural-language conversation and Django exposes safe tool endpoints. The existing Django booking internals remain the authority for appointment validation and creation.

## Recommended Architecture

Use an n8n AI Agent workflow with Django as a trusted tool API.

Responsibilities:

- Facebook Messenger: receives user messages from the clinic Facebook Page.
- n8n: receives the Facebook webhook, runs the AI Agent, keeps conversational context keyed by `page_id + psid`, calls Django tools, and sends text replies back to Facebook.
- Django: resolves the clinic, returns clinic context, checks services and slots, suggests nearest alternatives, and creates appointments after confirmation.
- AI model provider: configurable in n8n and added later by connecting the chosen model node/credential.

## Message Flow

1. A user sends a normal text message to the clinic Facebook Page.
2. Facebook posts the webhook payload to n8n.
3. n8n extracts `page_id`, `psid`, message text, and metadata.
4. n8n resolves clinic context through Django using `page_id`.
5. n8n AI Agent receives the user message, conversation memory, clinic context, and tool descriptions.
6. The agent answers directly when enough information exists.
7. For booking-related messages, the agent gathers missing details in normal text.
8. The agent calls Django to check availability and nearest alternatives.
9. When all details are ready, the agent summarizes the appointment and asks the user to confirm.
10. After the user confirms in text, the agent calls Django to create the appointment.
11. n8n sends the final text reply to Facebook through Graph API.

## Conversation Behavior

The chatbot should not show buttons for booking. It should respond like a normal clinic assistant.

Examples:

- User: `What time are you open?`
- Agent: Answers from clinic context and custom instructions.

- User: `Can I book cleaning tomorrow afternoon?`
- Agent: Identifies the service, resolves date/time intent, checks slots, asks for missing name and phone, then asks for confirmation.

- User: `Book me for consultation at 10am Friday. My name is Ana Cruz, 09171234567.`
- Agent: Checks the service and requested time. If available, asks for explicit confirmation. If unavailable, suggests nearby alternatives.

The agent must create an appointment only after confirmation such as `yes`, `confirm`, `that works`, or equivalent intent.

## Clinic Knowledge

The agent may use:

- Clinic name, address, phone, email, and timezone.
- Active services, descriptions, durations, prices, and display prices.
- Active FAQs.
- Availability returned by Django tools.
- Custom clinic AI instructions from a new Messenger-specific settings model.

The agent must not invent clinic policies, prices, services, diagnoses, or medical advice. If information is missing, it should say it does not have that information and offer the clinic contact details when available.

## Django Data Model

Add a Messenger-specific AI settings model, separate from the core `Clinic` model.

Proposed model:

- `MessengerAISettings`
- One-to-one relationship with `MessengerConnection`
- `is_ai_enabled`: controls whether the AI workflow should respond for this connection.
- `instructions`: clinic-specific instructions for tone, policies, accepted questions, and special booking guidance.
- `fallback_message`: optional message used when AI is disabled or cannot answer.
- Timestamps through the existing `TimeStampedModel` pattern.

Tying settings to `MessengerConnection` keeps the feature scoped to Facebook Messenger and allows future channel-specific settings without cluttering `Clinic`.

## Django Tool Endpoints

Expose n8n-facing endpoints protected by the existing shared n8n secret header or a stronger token if introduced later.

Proposed endpoints:

- `POST /messenger/ai/context/`
- `POST /messenger/ai/services/`
- `POST /messenger/ai/availability/`
- `POST /messenger/ai/book/`

`context` resolves `page_id` and returns safe clinic context, active FAQs, active services, and custom AI instructions.

`services` helps the agent match a user phrase to active clinic services. Django should return likely matches and ask the agent to clarify if ambiguous.

`availability` accepts clinic/page identity, service, preferred date/time, and timezone-aware intent data. It returns whether the requested time is available and, if not, nearest alternatives.

`book` accepts confirmed booking details and creates the appointment through existing booking logic. It must validate the slot again at creation time.

## Booking Rules

Django remains the source of truth for booking rules.

Required details before confirmation:

- Service.
- Date and time.
- Patient full name.
- Patient phone number.

Before appointment creation, the agent must summarize:

- Clinic.
- Service.
- Date and local time.
- Patient full name.
- Patient phone number.

Appointment creation requires explicit confirmation from the user after the summary.

If the requested slot is unavailable, Django should return nearest alternatives for the same service. The agent should present them naturally, for example: `10:00 AM is unavailable. I can offer 9:30 AM or 11:00 AM instead. Which works best?`

The final booking call must still use the existing guest booking path where possible, preserving patient phone matching, appointment validation, and double-booking prevention.

## n8n Workflow Design

The new workflow should replace the current pattern where n8n simply calls Django `n8n_webhook()` and sends Django-generated quick replies.

Proposed nodes:

- Facebook webhook trigger.
- Payload normalization node.
- Django context HTTP request node.
- AI Agent node.
- Configurable chat model node, to be added later.
- Conversation memory keyed by `page_id + psid`.
- Django HTTP tool nodes for context, services, availability, and booking.
- Facebook Graph API send-message node.

The workflow should send plain Messenger text messages. It should not send quick replies or postback payloads for the booking flow.

## Error Handling

- If `page_id` does not match an active `MessengerConnection`, n8n should stop without replying or use a generic fallback if configured.
- If AI is disabled for the connection, n8n should send `fallback_message` when present.
- If the AI model is not configured yet, the workflow should not create appointments. It should fail safely or route to a fallback response.
- If Django tool calls fail, the agent should apologize and suggest contacting the clinic directly.
- If appointment creation fails because the slot became unavailable, Django should return alternatives and the agent should ask the user to choose another time.

## Testing Strategy

Django tests:

- `MessengerAISettings` is scoped to one Messenger connection.
- Context endpoint returns only the clinic tied to the provided Facebook page.
- Availability endpoint respects active services and clinic timezone.
- Booking endpoint requires explicit confirmation state/data and validates slots again.
- Booking endpoint preserves patient phone matching and double-booking prevention.
- Cross-clinic access is rejected or returns no data.

n8n/manual tests:

- Clinic info question receives a natural text answer.
- Service question receives correct service information.
- Booking request with missing details prompts for those details.
- Booking request with unavailable time suggests nearest alternatives.
- Appointment is not created before confirmation.
- Appointment is created after confirmation.
- Facebook replies are sent as normal text messages, not quick replies.

## Migration Strategy

Keep the legacy direct Messenger webhook only if still needed for backward compatibility, but route the n8n workflow away from `bot_engine.handle_message()`. The old state-machine booking flow can be removed after the AI workflow is working and tests confirm no active code path uses it.

The existing `MessengerSession` model can either be retained for legacy compatibility or repurposed later for lightweight conversation metadata, but n8n memory should be the primary conversation memory for the AI agent workflow.

## Open Implementation Notes

- The AI provider is intentionally not selected in this design. The n8n workflow should leave the model node configurable so a model can be added later.
- The implementation should avoid committing local n8n credentials, webhook secrets, or exported workflows containing secrets.
- Production secrets should live in environment variables or n8n credentials, not hardcoded JSON files.
