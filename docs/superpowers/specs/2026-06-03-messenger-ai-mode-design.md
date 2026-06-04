# Messenger AI Mode Design

## Goal

Add a clinic-configurable Messenger response mode so clinics can choose whether Facebook Messenger uses the existing quick-reply booking flow or the n8n AI booking flow.

The default mode is quick replies so Messenger does not consume AI tokens unless a clinic/admin explicitly turns on Messenger AI mode. This supports future pricing or subscription packaging without changing booking validation or tenant-scoping rules.

## Current State

ClinicFlow already has two Messenger-capable paths:

- The deterministic Django Messenger bot in `messenger.bot_engine.handle_message()`, which uses quick replies for booking, FAQs, clinic info, and cancel flows.
- The n8n AI bridge and Django AI tool endpoints, which use `ClinicAISettings`, active services, active FAQs, and safe booking tools for natural-language booking.

The dashboard already separates shared assistant behavior from Messenger connection setup:

- `Assistant` owns shared AI prompt, shared fallback message, FAQs, and website widget settings.
- `Messenger Settings` owns Facebook Page connection, credentials, webhook setup, and disconnect actions.

The new feature should preserve that boundary while adding a Messenger-only channel mode.

## Approved Direction

Use a clinic-level Messenger mode stored with the clinic's shared AI settings.

Add a field such as `ClinicAISettings.messenger_response_mode` with two values:

- `quick_replies`
- `ai`

Default value: `quick_replies`.

This lets clinics pre-configure Messenger mode before connecting a Facebook Page, keeps Messenger AI independent from the website Assistant AI switch, and gives the product a clear future pricing lever.

## Setting Ownership

| Setting | Scope | Purpose |
| --- | --- | --- |
| `ClinicAISettings.is_ai_enabled` | Website Assistant/shared AI availability | Keeps current Assistant behavior and should not control Messenger mode. |
| `ClinicAISettings.messenger_response_mode` | Facebook Messenger only | Chooses quick replies or AI mode for Messenger. |
| `ClinicAISettings.instructions` | Shared AI prompt | Used by AI mode for Messenger and by website Assistant AI. |
| `ClinicAISettings.fallback_message` | Shared fallback | Used when AI mode is enabled but unavailable. |

Messenger AI mode is intentionally independent from `is_ai_enabled`. If Messenger mode is `ai`, Messenger should use the AI bridge even when the website Assistant AI switch is off.

## Dashboard UX

The control belongs on the `Assistant` page because it controls assistant behavior, while `Messenger Settings` remains focused on Facebook connection setup.

Add a new card or subsection near `Shared Assistant Settings` titled `Messenger Response Mode`.

Options:

| Option | Copy | Behavior |
| --- | --- | --- |
| `Quick replies` | `Use guided buttons for Messenger booking. No AI tokens are consumed.` | Uses the existing deterministic quick-reply flow. |
| `AI mode` | `Use AI for Messenger conversations and booking. No quick-reply buttons are shown.` | Uses the n8n AI bridge. |

Helper copy:

- `This affects Facebook Messenger only. Website Assistant AI is controlled separately.`
- `Quick replies are recommended for clinics that do not include Messenger AI in their plan.`
- If Messenger is not connected: `You can choose a Messenger mode now. It will apply after Facebook Messenger is connected.`

The `Messenger Settings` page should not duplicate the control. It may show a read-only note or link such as `Messenger response mode is managed from Assistant settings.`

## Runtime Behavior

| Messenger mode | Behavior |
| --- | --- |
| `quick_replies` | Use `messenger.bot_engine.handle_message()` and return/send the same quick replies currently used for Messenger booking. |
| `ai` | Route Messenger messages through the existing n8n AI bridge and send plain Messenger text replies. No quick replies should be shown. |
| `ai` but AI unavailable | Send fallback text only. Do not fall back to quick replies. |

The quick-reply path must keep the exact current flow:

- Welcome message.
- `Book an appointment`, `View FAQs`, and `Clinic info` quick replies.
- Service, date, time, patient info, and confirmation steps.
- Existing FAQ selection.
- Existing `CANCEL` handling.

## Data Flow

When Assistant settings are saved:

1. Django resolves the active clinic from the authenticated dashboard session.
2. Django loads or creates `ClinicAISettings` for that clinic.
3. Django saves `messenger_response_mode` from the form.
4. The browser does not submit or control clinic ID, connection ID, or tenant ownership.

When n8n receives a Messenger message:

1. n8n resolves clinic context through Django using `page_id`.
2. Django returns `ai.messenger_response_mode` in the Messenger AI context payload.
3. If mode is `ai`, n8n continues through the shared AI Agent.
4. If mode is `quick_replies`, n8n calls Django's existing `/messenger/n8n-webhook/` quick-reply endpoint and sends returned quick replies through Facebook Graph API.
5. If mode is `ai` but context/model output is unavailable, n8n sends fallback text only.

The n8n AI-enabled condition must become channel-aware:

- Messenger should enter the AI Agent when `channel = messenger` and `context.ai.messenger_response_mode = ai`.
- Widget should continue using `context.ai.is_ai_enabled` for website Assistant behavior.
- Messenger must not be blocked by `context.ai.is_ai_enabled`, because the Messenger mode is independent from the website Assistant AI switch.

The fallback text for AI mode failures should come from `context.ai.fallback_message` or the existing generic safe fallback. It should be sent as plain text without quick replies.

The `/messenger/n8n-webhook/` quick-reply endpoint should also respect the mode defensively. If the active clinic's mode is `quick_replies`, it should run `handle_message()` as it does today. If the mode is `ai`, it should not emit quick replies.

If the legacy direct Facebook webhook path remains active, it should respect the same setting:

- `quick_replies`: keep existing direct quick-reply behavior.
- `ai`: do not run the quick-reply bot from the legacy direct webhook. Stop safely because the AI path is handled by n8n.

## Data Model Direction

Add `messenger_response_mode` to `ClinicAISettings` rather than `MessengerConnection`.

Reasons:

- Clinics can configure the mode before Messenger is connected.
- The mode belongs to clinic assistant behavior, not Facebook credentials.
- It avoids creating a disconnected `MessengerConnection` just to store mode preferences.
- It keeps one canonical settings row for shared AI behavior and Messenger channel mode.

Use defensive runtime handling so an invalid or blank stored mode is treated as `quick_replies`.

## Subscription Direction

Do not add plan gating in the first implementation.

The field should still be suitable for future subscription enforcement. A later billing feature can prevent saving `ai` mode when the clinic is not entitled, or display the option as locked.

## Error Handling

- New clinics or clinics without a `ClinicAISettings` row should get one with `messenger_response_mode = quick_replies`.
- Clinics without a connected Messenger page can still select a mode in advance.
- AI mode with missing context/model/provider should send the configured fallback message as plain text only.
- If fallback message is blank, use the existing generic safe AI fallback.
- Invalid posted modes should fail form validation and keep the previous stored value.
- Invalid stored modes should fail closed to quick replies at runtime.

## Security And Tenant Safety

- Dashboard saves must require login, active clinic resolution, and settings permission.
- Mode saves must be scoped to the active clinic's `ClinicAISettings` row.
- The form must not accept clinic ID, connection ID, page ID, patient ID, service ownership, or subscription state from the browser.
- Messenger context lookup must continue resolving clinic ownership from `page_id` server-side.
- AI tool endpoints must continue injecting tenant identity from resolved `page_id` or widget `clinic_slug`, never from model-generated values.
- Booking validation, patient phone matching, slot regeneration, double-booking prevention, appointment status behavior, and explicit confirmation requirements remain unchanged.
- No n8n credentials, model credentials, Facebook app secrets, page tokens, or webhook secrets should be exposed in templates, logs, tests, screenshots, or committed workflow exports.

## Testing Strategy

Add or update tests for:

- `ClinicAISettings.messenger_response_mode` defaults to `quick_replies`.
- Assistant settings page renders the Messenger response mode control and explanatory copy.
- Settings users can save Messenger mode for the active clinic.
- Users without settings permission cannot save Messenger mode.
- Saving Messenger mode cannot edit another clinic because the clinic is resolved server-side.
- Messenger AI context returns the selected `messenger_response_mode`.
- Quick-reply mode still returns the current Django quick-reply actions through `/messenger/n8n-webhook/`.
- Existing Messenger booking, FAQ, clinic info, and cancel tests still pass.
- AI mode does not emit quick replies in the n8n design path.
- Assistant/Messenger templates keep readable Neon Aqua Clinical copy and existing `cf-*` component patterns.

## Non-Goals

- Do not add subscription gating in this phase.
- Do not add patient portals, medical records, prescriptions, inventory, online payments, or marketplace booking.
- Do not replace Django templates, Tailwind CSS, HTMX, Alpine.js, or the current n8n integration.
- Do not duplicate shared prompt, fallback, or FAQ settings on the Messenger settings page.
- Do not change booking approval mode, slot generation, patient matching, appointment creation safety, or double-booking prevention.
- Do not make Messenger fall back to quick replies when AI mode is enabled but unavailable.
