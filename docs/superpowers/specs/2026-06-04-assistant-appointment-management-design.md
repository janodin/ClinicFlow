# Assistant Appointment Management Design

## Goal

Add safe cancel and reschedule support to the shared AI assistant used by Facebook Messenger AI mode and the website widget `Chat with Assistant`.

Patients should be able to manage future appointments without logging in, as long as they can verify the appointment by reference code and matching phone number. The assistant must not mutate appointments until the patient explicitly confirms the summarized action.

## Current State

ClinicFlow already has appointment booking safeguards in Django:

- Public and AI booking use `_process_guest_booking()` in `widget.views`, which validates guest identity, locks the clinic row, verifies active services, regenerates available slots, matches patients by normalized phone, and prevents double booking.
- Staff dashboard cancellation and rescheduling already exist in `dashboard.views`, using clinic-scoped appointment lookups and slot validation.
- `Appointment` already stores `reference_code`, `status`, `source`, `messenger_psid`, `cancellation_reason`, `starts_at`, and `ends_at`.
- `scheduling.utils.validate_slot()` already checks unavailable dates, open hours, breaks, and appointment overlaps with optional `exclude_appointment` support.
- The shared n8n AI bridge already routes Messenger AI and widget chat through one shared agent with service, availability, and confirmed-booking tools.

Current gaps:

- AI tools can book appointments but cannot verify, cancel, or reschedule existing appointments.
- Messenger quick-reply mode has a basic PSID-scoped `CANCEL` command, but no reschedule flow.
- Widget chat has no durable patient identity equivalent to Messenger PSID, so cross-channel appointment management needs a different verification method.

## Approved Direction

Use new shared Django AI tool endpoints for verified appointment management.

The feature applies to:

- Facebook Messenger when the clinic is in Messenger AI mode.
- Website widget `Chat with Assistant` when website Assistant AI is enabled.

The feature does not expand deterministic Messenger quick-reply mode. The existing quick-reply `CANCEL` behavior remains unchanged.

Appointment verification requires:

- Appointment reference code.
- Matching patient phone number after normalization.
- Clinic resolved server-side from `page_id` for Messenger or `clinic_slug` for widget.

Eligible appointments:

- Same resolved clinic only.
- Future appointments only, where `starts_at > timezone.now()` at the moment the tool runs.
- `pending` or `confirmed` status only.
- Any appointment source is allowed after verification.

Rescheduling is same-service only. The assistant can move the appointment date/time, but cannot change service, duration, price, patient, source, reference code, or status.

## Architecture

Add appointment-management functions to `messenger.ai_tools` and expose them through `messenger.views` as n8n-protected AI tool endpoints.

Core units:

- `messenger.ai_tools`: appointment lookup, cancel, and reschedule helpers.
- `messenger.views`: POST endpoints protected by `X-N8N-Webhook-Secret` through the existing `_ai_tool_response()` wrapper.
- `messenger.urls`: AI tool routes that mirror the existing Messenger/widget endpoint split.
- `n8n_combined_messenger_widget_ai_bridge.ts`: shared HTTP request tools and prompt rules for verified appointment management.
- Tests in `messenger/tests.py` and n8n source tests to lock down security, validation, and workflow prompt/tool behavior.

No model changes are planned.

Planned endpoint shape:

- Messenger lookup: `POST /messenger/ai/appointment/lookup/`
- Messenger cancel: `POST /messenger/ai/appointment/cancel/`
- Messenger reschedule: `POST /messenger/ai/appointment/reschedule/`
- Widget lookup: `POST /messenger/ai/widget/appointment/lookup/`
- Widget cancel: `POST /messenger/ai/widget/appointment/cancel/`
- Widget reschedule: `POST /messenger/ai/widget/appointment/reschedule/`

This keeps the same API style as the existing context, services, availability, and booking tools while keeping tenant resolution server-side.

## Tool Contracts

### `find_verified_appointment`

Purpose: verify and summarize an appointment before any mutation.

Inputs:

- `page_id` for Messenger or `clinic_slug` for widget, injected by n8n from normalized channel context.
- `reference_code` from the patient.
- `phone` from the patient.

Output:

- `found: true` with appointment summary when verification succeeds.
- `found: false` with a safe error when the clinic, reference, phone, status, or date is not eligible.

The summary should include only patient-safe fields:

- `reference_code`
- `service_id` as a server-derived field for same-service availability checks only
- `service`
- `status`
- `starts_at`
- `local_starts_at`
- `patient_name`
- `patient_phone_last4`
- `local_date_label`
- `local_time_label`

This tool must not mutate data.

### `cancel_verified_appointment`

Purpose: cancel a verified appointment after explicit patient confirmation.

Inputs:

- `page_id` for Messenger or `clinic_slug` for widget.
- `reference_code`.
- `phone`.
- `confirmed`.
- Optional `reason`.

Rules:

- `confirmed` must normalize to exact boolean `true` in the Django view layer.
- Re-run verification server-side before mutating.
- Require the appointment to still be future `pending` or `confirmed`.
- Require `appointment.can_transition_to(Appointment.STATUS_CANCELLED)`.
- Set `status=cancelled` and store a concise cancellation reason if provided.
- Return a safe summary of the cancelled appointment.

### `reschedule_verified_appointment`

Purpose: move a verified appointment to a new same-service slot after explicit patient confirmation.

Inputs:

- `page_id` for Messenger or `clinic_slug` for widget.
- `reference_code`.
- `phone`.
- `starts_at` for the requested new time as ISO 8601.
- `confirmed`.

Rules:

- `confirmed` must normalize to exact boolean `true` in the Django view layer.
- Re-run verification server-side before mutating.
- Require the appointment to still be future `pending` or `confirmed`.
- Preserve the existing service and compute `ends_at` from `appointment.service.effective_duration()`.
- Reject past times.
- Lock the clinic row inside `transaction.atomic()`.
- Call `validate_slot(clinic, new_starts_at, new_ends_at, exclude_appointment=appointment)`.
- Save only `starts_at` and `ends_at` unless Django also updates timestamp fields.
- Return a safe summary of the rescheduled appointment.

## Assistant Conversation Flow

For cancellation:

1. Patient asks to cancel.
2. Assistant collects reference code and phone number.
3. Assistant calls `find_verified_appointment`.
4. Assistant summarizes the matched appointment and asks for explicit confirmation.
5. Patient confirms.
6. Assistant calls `cancel_verified_appointment` with `confirmed=true`.
7. Assistant reports the cancellation result and reference code.

For rescheduling:

1. Patient asks to reschedule.
2. Assistant collects reference code, phone number, and preferred new date/time.
3. Assistant calls `find_verified_appointment`.
4. Assistant calls existing availability tooling with the server-derived `service_id` from lookup when it needs to evaluate or offer candidate slots.
5. Assistant summarizes the matched appointment and new requested time, then asks for explicit confirmation.
6. Patient confirms.
7. Assistant calls `reschedule_verified_appointment` with `confirmed=true`.
8. Assistant reports the rescheduled time and reference code.

The assistant must not infer that earlier intent is confirmation. The patient must explicitly confirm after the assistant presents the final action summary.

## n8n Design

Extend the shared AI core rather than creating channel-specific workflows.

New shared tools should follow the existing channel-aware pattern:

- Messenger calls Django with `page_id` injected from the normalized Messenger item.
- Widget calls Django with `clinic_slug` injected from the normalized widget item.
- The AI may provide reference code, phone, requested new time, reason, and confirmation only.
- For reschedule availability checks, the AI may use the `service_id` returned by `find_verified_appointment`; it must not use a user-supplied service ID.
- The AI must not provide clinic ID, appointment ID, patient ID, service ID for mutation, status, source, ownership, or tenant identifiers.

Prompt updates should require the assistant to:

- Use verified appointment tools for cancel/reschedule.
- Ask for reference code and phone number before lookup.
- Use `find_verified_appointment` before any cancel or reschedule mutation.
- Summarize the found appointment and requested action.
- Ask for explicit confirmation before canceling or rescheduling.
- Use `cancel_verified_appointment` or `reschedule_verified_appointment` only after explicit confirmation.
- Keep replies concise and channel-appropriate.
- Suggest contacting the clinic directly when verification fails or the requested change is not allowed.

## Security And Tenant Safety

- Resolve clinic identity server-side from `page_id` or `clinic_slug`.
- Never trust AI-supplied clinic, appointment, patient, service, status, source, or ownership identifiers.
- Do not accept appointment ID for patient-facing AI cancel/reschedule tools.
- Match appointments through `clinic.appointments` with `reference_code` and patient normalized phone.
- Return generic lookup failure messages so wrong reference/phone combinations do not expose appointment existence.
- Do not expose secrets, page tokens, n8n credentials, webhook secrets, model credentials, or private clinic data in responses or logs.
- Keep all tool endpoints protected by `X-N8N-Webhook-Secret`.
- Keep widget public access scoped through active, onboarding-complete `clinic_slug`.
- Keep Messenger access scoped through active `MessengerConnection.page_id`.

## Error Handling

- Missing or invalid clinic context returns a safe not-found or mutation-failed response.
- Missing reference code or phone returns a clear request for the missing field.
- Reference and phone mismatch returns a generic appointment-not-found response.
- Past appointments cannot be cancelled or rescheduled.
- `cancelled`, `completed`, and `no_show` appointments cannot be cancelled or rescheduled through the assistant.
- Cancel and reschedule return a confirmation-required error unless `confirmed=true` is supplied after view normalization.
- Invalid datetime input returns an invalid date/time error.
- Rescheduling to the past returns a past-time error.
- Rescheduling outside hours, during breaks, on unavailable dates, or into overlapping appointments returns the relevant `validate_slot()` error.
- Tool failures should cause the assistant to apologize and recommend contacting the clinic directly.

## Testing Strategy

Add Django tests for:

- Appointment lookup succeeds for same-clinic reference code and normalized phone.
- Lookup rejects wrong phone without exposing cross-clinic data.
- Lookup rejects cross-clinic reference attempts.
- Lookup rejects past, cancelled, completed, and no-show appointments.
- Cancel requires explicit confirmation.
- Cancel changes future pending/confirmed appointments to cancelled and stores reason.
- Cancel re-checks verification server-side.
- Reschedule requires explicit confirmation.
- Reschedule preserves patient, service, source, reference code, and status.
- Reschedule rejects invalid datetime, past datetime, closed days, unavailable dates, breaks, outside-hours slots, and overlaps.
- Reschedule uses clinic row locking and `validate_slot(..., exclude_appointment=appointment)` behavior.
- Tool endpoints require `X-N8N-Webhook-Secret`.
- Widget tools respect website AI disabled behavior where applicable.
- Messenger tools work independently from website AI enabled/disabled state when Messenger mode is AI.

Add n8n source tests for:

- Shared agent includes appointment lookup, cancel, and reschedule tools.
- Tool payloads inject `page_id` or `clinic_slug` from normalized context, not AI output.
- Prompt requires reference + phone verification before lookup.
- Prompt requires explicit confirmation before cancel/reschedule mutation.
- Prompt forbids AI-supplied tenant and ownership identifiers.

Run at minimum during implementation:

- `python -m pytest messenger/tests.py`
- `python -m pytest widget/tests.py`
- `python -m pytest tests/test_n8n_combined_bridge_source.py`
- `python manage.py check`

## Non-Goals

- Do not add patient accounts, patient portals, medical records, prescriptions, inventory, online payments, marketplace booking, or real autonomous clinical advice.
- Do not change deterministic Messenger quick-reply mode beyond preserving existing behavior.
- Do not change the separate guided widget booking flow.
- Do not allow service changes during reschedule.
- Do not expose appointment management by appointment ID.
- Do not let AI mutate appointment status or time without Django verification and explicit confirmation.
- Do not add new database fields or migrations unless implementation uncovers a concrete need.
