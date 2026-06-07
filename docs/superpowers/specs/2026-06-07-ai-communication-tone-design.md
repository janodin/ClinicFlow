# AI Communication Tone Design

## Goal

Add structured AI communication tone controls for KliniAssist's shared Assistant so clinics can choose how patient-facing AI replies should sound without weakening booking, tenant, privacy, or safety rules.

The feature applies to the existing shared AI runtime used by the website Assistant and Facebook Messenger AI mode.

## Current State

KliniAssist already stores shared assistant behavior in `ClinicAISettings`:

- `is_ai_enabled` controls website Assistant AI availability.
- `messenger_response_mode` controls whether Messenger uses quick replies or AI mode.
- `instructions` stores the clinic's shared assistant prompt/instructions.
- `fallback_message` stores the safe fallback copy.

Both `build_ai_context()` and `build_widget_ai_context()` return the shared settings under `ai`. The combined n8n Messenger and Widget AI bridge injects `ai.instructions` into one shared AI Agent prompt and versions memory with `ai.settings_updated_at`.

This means tone can be added cleanly as shared Assistant configuration instead of a Messenger-only setting.

## Approved Direction

Use a preset tone selector plus optional custom tone notes.

Do not make tone another unrestricted full prompt. The existing `instructions` field remains the place for broader clinic policies and assistant behavior. Tone should be structured, short, and style-only.

## Product Model

Add two fields to `ClinicAISettings`:

- `communication_tone`: a choice field with a safe default.
- `custom_tone_instructions`: optional style-only text, limited to 500 characters.

Recommended tone presets:

- `professional`: clear, respectful, clinic-standard wording.
- `warm`: friendly and reassuring without being casual.
- `empathetic`: gentle, patient, and supportive for anxious patients.
- `concise`: brief, direct, and efficient.
- `friendly`: approachable and conversational while remaining professional.

Default must be `professional` to preserve the current clinic-safe tone.

The runtime payload should expose the values under `ai` as:

- `communication_tone`
- `communication_tone_label`
- `custom_tone_instructions`

## Dashboard UX

Add a dedicated **Communication Tone** block inside `Dashboard -> Assistant -> Shared Assistant Settings`.

Recommended order:

1. Enable AI replies.
2. Messenger response mode.
3. Communication tone preset.
4. Custom tone notes.
5. Prompt / Instructions.
6. Fallback message.

The UI should explain:

`Tone affects wording only. Services, prices, availability, booking rules, and safety checks still come from KliniAssist.`

The existing `Prompt / Instructions` copy should make clear it is for broader assistant behavior and clinic policies, not the primary tone control.

## Runtime Flow

1. A settings user opens the Assistant settings page.
2. Django loads or creates `ClinicAISettings` for the active clinic.
3. The user selects a tone preset and optionally enters short custom tone notes.
4. Django saves the settings for the active clinic only.
5. Messenger AI context and widget AI context include tone fields under `ai`.
6. n8n reads tone fields from the shared AI context.
7. The shared AI Agent receives a dedicated communication tone section in the system prompt.
8. Existing tool, booking, privacy, and safety rules remain authoritative.

## n8n Prompt Treatment

The shared AI Agent system prompt should include tone as a separate section, for example:

```text
Communication tone:
- Preset: Warm
- Custom clinic tone notes: Keep replies reassuring and simple.

Tone affects wording only. It must not override clinic data, tool results, availability, booking confirmation, privacy, medical safety, or channel rules.
```

The tone section must not replace the existing clinic instructions or safety rules. Place it near the clinic instruction section, but keep final hard tool and safety guidance explicit after all clinic-configured text.

## Prompt Precedence

Effective precedence should be:

1. n8n system and channel safety rules.
2. Django tool results and clinic-scoped data.
3. Clinic prompt/instructions.
4. Communication tone preset and custom tone notes.

Tone can influence phrasing, warmth, brevity, empathy, and formality. It cannot:

- Create appointments without explicit confirmation.
- Invent services, prices, business hours, FAQs, or appointment slots.
- Bypass slot validation, patient matching, or double-booking checks.
- Provide medical advice, diagnosis, prescriptions, or emergency triage beyond safe referral language.
- Expose secrets, tokens, credentials, internal IDs, or webhook details.
- Override tenant scoping or clinic ownership checks.

## Channel Behavior

Website Assistant:

- Uses tone only when `ClinicAISettings.is_ai_enabled` is true.
- Continues to return fallback copy when AI is disabled or unavailable.

Messenger:

- Uses tone only when `ClinicAISettings.messenger_response_mode` is `ai`.
- Does not apply tone in quick-reply mode because that path bypasses the shared AI Agent.

Both channels still share the same tone settings in V1. Do not add channel-specific tone overrides unless a future requirement explicitly asks for them.

## Data And Migration Notes

This change requires a Django model migration for `ClinicAISettings`.

The migration should add defaults for existing clinics so current behavior remains stable:

- `communication_tone = professional`
- `custom_tone_instructions = ""`

No patient data, appointment data, or Messenger connection data should be migrated.

## Security And Tenant Safety

All dashboard saves must keep existing authentication, active clinic resolution, and `user_can_manage_settings()` permission checks.

The browser must not submit clinic IDs, connection IDs, page IDs, or tenant ownership values to control where tone settings are saved. The view should save through the server-resolved active clinic's `ClinicAISettings` instance.

Tone fields must not be exposed to public templates except through the existing n8n context endpoint protected by `X-N8N-Webhook-Secret`.

Custom tone notes should be stored as text, escaped by Django templates, and treated as untrusted prompt input by the n8n safety rules.

## Error Handling

- If tone fields are missing on old records, Django must use safe defaults through model defaults and form initial values.
- If the preset value is invalid, form validation must reject it and the runtime payload helper must fail closed to `professional`.
- If custom tone notes are blank, n8n must use only the preset tone.
- If AI is disabled or unavailable, the existing fallback behavior remains unchanged.

## Testing Strategy

Add or update tests for:

- `ClinicAISettings` defaults include `professional` tone and blank custom notes.
- Assistant settings page renders the communication tone fields.
- Settings users can save tone for the active clinic.
- Staff without settings permission cannot save tone.
- Tone saves are clinic-scoped and cannot modify another clinic.
- `build_ai_context()` returns the tone fields for Messenger AI context.
- `build_widget_ai_context()` returns the tone fields for website Assistant context.
- n8n source prompt includes the communication tone section.
- n8n prompt states tone cannot override clinic data, tool results, booking confirmation, or safety rules.
- n8n memory versioning still changes when AI settings are updated.

Minimum verification after implementation:

- `./env/Scripts/python -m pytest messenger/tests.py -k "ai_context or clinic_ai_settings" -q`
- `./env/Scripts/python -m pytest dashboard/tests.py -k "assistant" -q`
- `./env/Scripts/python -m pytest tests/test_n8n_combined_bridge_source.py -q`
- `./env/Scripts/python manage.py makemigrations --check --dry-run`
- `./env/Scripts/python manage.py check`

## Non-Goals

- Do not add a new AI provider integration.
- Do not add patient portal, medical records, prescriptions, inventory, online payments, or marketplace booking.
- Do not add real AI moderation infrastructure in V1.
- Do not expose n8n, model-provider, Meta, webhook, or page token secrets to templates, logs, tests, or browser JavaScript.
- Do not move booking validation, slot generation, or tenant scoping into n8n.
- Do not add channel-specific tone settings unless explicitly requested later.
