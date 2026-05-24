# Messenger AI Prompt Settings Design

## Goal

Expose the Messenger AI prompt on the ClinicFlow Messenger settings page so clinic users can enter or edit the instructions used by Minimax or another model inside the n8n Messenger AI workflow.

## Scope

Included:

- Add Messenger-specific AI controls to the existing dashboard Messenger settings page.
- Let authorized clinic users manage AI enabled state, prompt instructions, and fallback response text.
- Reuse the existing `MessengerAISettings` model and existing `/messenger/ai/context/` response shape.
- Keep the n8n workflow model-provider agnostic; the configured model consumes the prompt from Django context.

Excluded:

- No new AI provider integration inside Django.
- No model-specific prompt editor for Minimax only.
- No patient portal, medical records, payments, prescriptions, inventory, or marketplace behavior.
- No change to booking validation, slot generation, patient matching, or double-booking prevention.

## Current State

The codebase already has `MessengerAISettings` with `is_ai_enabled`, `instructions`, and `fallback_message`. The n8n-facing AI context endpoint already returns these values under `ai.is_ai_enabled`, `ai.instructions`, and `ai.fallback_message`.

The dashboard Messenger settings page currently exposes only Facebook Page connection fields: Page ID and Page Access Token. Clinic users cannot edit the Messenger AI prompt from the UI yet.

## Recommended Approach

Add a separate **Messenger AI Prompt** card to `dashboard/templates/dashboard/messenger_settings.html`, below the Facebook Page Connection card and above the n8n Webhook card.

The card should contain:

- `Enable AI replies`: checkbox mapped to `MessengerAISettings.is_ai_enabled`.
- `Prompt / Instructions`: textarea mapped to `MessengerAISettings.instructions`.
- `Fallback message`: textarea mapped to `MessengerAISettings.fallback_message`.

This keeps credentials separate from AI behavior while keeping all Messenger-specific setup on the Messenger settings page.

## User Experience

When a Messenger connection exists, authorized settings users can edit and save the AI settings from the Messenger page.

When no Messenger connection exists yet, the AI prompt card should explain that Facebook Page settings must be saved first. The AI settings should not create a disconnected `MessengerAISettings` record because the model is scoped to `MessengerConnection`.

Suggested helper copy:

- For the prompt field: `Tell the Messenger AI how to speak, what clinic policies to follow, and what it should avoid. Services, prices, and availability still come from ClinicFlow.`
- For fallback message: `Shown when AI replies are disabled or the AI cannot safely respond.`

## Data Flow

1. Clinic admin opens Dashboard -> Messenger Settings.
2. The view loads the clinic's `MessengerConnection`.
3. If a connection exists, the view loads or creates `MessengerAISettings` for that connection.
4. User edits AI enabled state, prompt instructions, and fallback message.
5. The dashboard saves the settings for the current clinic's Messenger connection only.
6. n8n calls `/messenger/ai/context/` with `page_id`.
7. Django resolves the active Messenger connection and returns the saved AI settings in the context payload.
8. The n8n AI Agent passes the prompt to Minimax or whichever model is configured in the workflow.

## Permissions And Tenant Safety

Only existing dashboard users who can manage settings for the current clinic should edit Messenger AI settings. The view must continue using the current clinic resolution and `user_can_manage_settings()` permission check.

The form must never accept a connection ID from the browser. It should derive the connection from the current clinic so one clinic cannot edit another clinic's prompt.

## Prompt Boundaries

The editable prompt can influence tone, clinic policies, and conversational behavior, but it does not override Django safety rules.

Django remains authoritative for:

- Clinic scoping.
- Active services and prices.
- Availability and slot validation.
- Patient phone matching.
- Appointment creation after explicit confirmation.
- Double-booking prevention.

If the prompt asks the model to invent medical advice, bypass confirmation, or book unavailable slots, the n8n workflow and Django tool endpoints should still prevent unsafe outcomes.

## Error Handling

- If AI settings save fails, show form validation errors on the Messenger page.
- If no connection exists, show a disabled/informational AI prompt card instead of saving AI settings.
- If AI is disabled, the context endpoint continues returning `is_ai_enabled: false` and the configured fallback message.
- If fallback message is blank, n8n may use its generic safe fallback response.

## Testing Strategy

Add or update tests to verify:

- Settings users can save Messenger AI prompt settings for their clinic.
- Non-settings users cannot save Messenger AI prompt settings.
- Saving AI settings creates or updates `MessengerAISettings` tied to the current clinic's `MessengerConnection`.
- The form does not allow cross-clinic prompt edits.
- `/messenger/ai/context/` returns the saved prompt, enabled state, and fallback message.

## Implementation Notes

- Reuse `MessengerAISettings`; no model migration should be necessary.
- Add a `MessengerAISettingsForm` in `messenger/forms.py`.
- Update `dashboard.views.messenger_settings` to handle separate posted forms, likely using a hidden `_form` value such as `connection_settings` and `ai_settings`.
- Keep the UI aligned with `DESIGN.md`: clean teal/white SaaS card layout, rounded cards, compact labels, and existing `cf-*`/`ui-*` classes.
- Do not store n8n credentials, model credentials, or provider secrets in the prompt field.
