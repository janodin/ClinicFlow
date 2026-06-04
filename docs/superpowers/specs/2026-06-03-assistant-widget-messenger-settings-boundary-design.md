# Assistant Widget And Messenger Settings Boundary Design

## Goal

Clarify where shared assistant, booking widget, and Messenger settings belong so clinic admins understand what affects the website widget, what affects Facebook Messenger, and what affects both channels.

The change should preserve the existing shared runtime architecture: Django remains the source of truth for clinic data and booking validation, while n8n runs the shared AI assistant flow for Messenger and the website widget.

## Current State

The data model and runtime are mostly shared already, but the dashboard information architecture is mixed:

- `ClinicAISettings` is clinic-level shared assistant config used by both Messenger and widget AI context.
- `ClinicFAQ` entries are clinic-level shared knowledge used by both the public widget and Messenger context.
- The shared AI prompt is edited on the Messenger settings page, even though it affects both Messenger and the website Assistant.
- FAQs are edited on the Assistant/Widget settings page, even though they affect both Messenger and the website Assistant.
- `widget_behavior_instructions` appears in widget settings but is not currently used by the widget runtime or shared n8n AI context.
- Legacy `MessengerAISettings` still exists after settings were migrated into `ClinicAISettings`.

This causes a product ownership mismatch: shared assistant behavior is split across pages named for specific channels.

## Approved Direction

Use setting ownership based on what the setting represents, not which runtime consumes it.

- Shared assistant knowledge and behavior belong to a neutral Assistant settings area.
- Website widget presentation and embed behavior belong to Booking Widget settings.
- Facebook Page credentials and webhook setup belong to Messenger settings.
- n8n/model/provider credentials remain outside the clinic dashboard.

Do not duplicate shared settings forms across multiple pages. There should be one canonical edit surface for each shared setting.

## Setting Ownership

| Setting | Canonical owner | Notes |
| --- | --- | --- |
| AI enabled switch | Assistant settings | Affects both Messenger and website Assistant. |
| AI prompt/instructions | Assistant settings | Stored in `ClinicAISettings.instructions`; channel-specific rules remain in n8n/system prompts. |
| AI fallback message | Assistant settings | Stored in `ClinicAISettings.fallback_message`; used by both channels when AI is disabled/unavailable. |
| FAQs | Assistant settings | Stored in `ClinicFAQ`; surfaced in widget UI and Messenger/widget AI context. |
| Widget accent color | Booking Widget settings | Website widget only. |
| Widget welcome message | Booking Widget settings | Website widget home/chat greeting only unless explicitly reused later. |
| Widget reason field toggle | Booking Widget settings | Website widget booking form only. |
| Widget embed/share code | Booking Widget settings | Website widget only. |
| Facebook App ID, App Secret, Page ID, Page Access Token | Messenger settings | Messenger channel connection only. |
| Messenger webhook setup and disconnect | Messenger settings | Messenger channel operations only. |
| n8n model/provider credentials | n8n/admin configuration | Must not be exposed in clinic dashboard templates or browser JavaScript. |

## Dashboard Information Architecture

Recommended dashboard structure:

1. Use the existing `dashboard:assistant_settings` route as a neutral `Assistant` page.
2. Keep website-only widget appearance, preview, and embed settings as a `Website Booking Widget` section on that page.
3. Keep the existing `Messenger` settings page for Facebook Page connection and Messenger setup only.

The `Assistant` page should contain:

- Shared AI settings card: enabled switch, prompt/instructions, fallback message, restore default prompt.
- FAQ responses card: create, edit, toggle, and delete FAQs.
- Clear copy: "Used by both the website Assistant and Facebook Messenger."

The `Website Booking Widget` section should contain:

- Accent color.
- Widget welcome message.
- Reason field toggle.
- Live preview.
- Public URL and embed snippets.

The Messenger page should contain:

- Facebook Page connection status.
- App/Page credential form with existing masked-secret reveal behavior.
- Setup instructions and n8n webhook copy.
- Disconnect action.
- A small cross-link card to Assistant settings for shared AI prompt and FAQs.

## Data Model Direction

Keep `ClinicAISettings` as the canonical shared AI settings model.

Keep `ClinicFAQ` as the canonical shared FAQ model.

Keep `MessengerConnection` as the canonical Messenger channel connection model.

Do not create separate widget-specific or Messenger-specific copies of the shared AI prompt or FAQ data unless a future requirement explicitly needs per-channel overrides.

## Legacy And Cleanup Direction

`MessengerAISettings` is now a legacy artifact because current dashboard saving and AI context loading use `ClinicAISettings`.

Recommended cleanup path:

- First, stop exposing or relying on `MessengerAISettings` in active dashboard/admin workflows if no production dependency remains.
- Keep the historical migration that copied Messenger settings into `ClinicAISettings`.
- Remove the legacy model only in a deliberate model-cleanup change with migrations and targeted regression tests.

`widget_behavior_instructions` should not stay as a visible setting unless it is made real. The preferred short-term choice is to remove it from the dashboard form/UI while keeping the database field until a separate cleanup migration is planned. If widget-only behavior instructions are needed later, they should be wired into the widget AI payload/context with clear copy that they affect only the website widget.

## Runtime Boundaries

Django remains authoritative for:

- Active clinic resolution and tenant scoping.
- Active services, prices, and availability.
- FAQs and shared AI settings.
- Patient phone matching.
- Slot regeneration and double-booking prevention.
- Appointment creation only after explicit confirmation.

n8n remains responsible for:

- Shared AI Agent execution.
- Channel normalization.
- Channel-specific output formatting for Messenger versus widget JSON.
- Shared model/memory/tool orchestration.

The browser must never receive model credentials, n8n credentials, shared webhook secrets, Facebook app secrets, or page access tokens.

## Permission And Tenant Safety

All dashboard settings changes must keep the existing authenticated, clinic-scoped, settings-permission checks.

Shared assistant settings must always be saved for the active clinic from server-side clinic resolution. The browser must not submit a clinic ID, connection ID, or tenant identifier that controls ownership.

FAQ actions must continue to scope lookups through `clinic.faqs`.

Messenger credential actions must continue to scope connection lookup through the active clinic's `messenger_connection`.

## Error Handling And UX Copy

If AI settings are missing, create or load default `ClinicAISettings` for the active clinic as current code does.

If Messenger is not connected, the shared Assistant page should still allow shared AI prompt and FAQ editing because the website Assistant can work without Messenger.

If widget embed settings are edited, the UI should not imply these settings affect Messenger unless the runtime actually uses them.

If Messenger users need to change prompt/FAQs, Messenger settings should link them to Assistant settings instead of duplicating the form.

## Testing Strategy

Add or update tests for:

- Assistant settings page shows and saves shared `ClinicAISettings` for the active clinic.
- Assistant settings save is blocked for staff without settings permission.
- Shared settings save is scoped to the active clinic and cannot modify another clinic.
- FAQs page copy or labels make clear FAQs are shared across website Assistant and Messenger.
- Messenger settings links to the `Assistant` page and no longer renders the shared AI prompt form.
- Widget settings no longer expose unused `widget_behavior_instructions`.
- Existing widget AI tests still prove widget fallback and n8n calls use `ClinicAISettings`.
- Existing Messenger AI context tests still prove Messenger context uses `ClinicAISettings` and clinic-scoped FAQs.
- Existing Messenger credential masking/reveal tests remain unchanged.

## Non-Goals

- Do not add patient login, a patient portal, medical records, prescriptions, inventory, online payments, or marketplace booking.
- Do not replace Django templates, Tailwind CSS, HTMX, Alpine.js, or the current widget UI stack.
- Do not add channel-specific AI prompts unless a future requirement explicitly asks for per-channel overrides.
- Do not expose n8n, model-provider, Facebook, or webhook secrets to templates, logs, or browser JavaScript.
- Do not change booking validation, slot generation, patient matching, appointment approval mode, or double-booking prevention.
