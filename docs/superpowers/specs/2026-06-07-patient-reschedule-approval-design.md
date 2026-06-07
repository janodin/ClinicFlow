# Patient Reschedule Approval Design

## Goal

Patients should be able to request a new appointment date/time through public channels, but the appointment must not move until the clinic approves the request.

This applies only to patient/public channels:

- Website widget and public appointment-management entry points.
- Website widget AI chat.
- Facebook Messenger AI mode.

Staff dashboard rescheduling remains immediate because owner/staff users already operate inside the authenticated clinic workflow.

## Current State

KliniAssist already has strong appointment safety patterns:

- `appointments.models.Appointment` enforces same-clinic patient/service ownership and rejects overlapping non-cancelled appointments.
- `scheduling.utils.generate_slots()` and `validate_slot()` enforce business hours, breaks, unavailable dates, service duration, and overlap checks.
- Public booking in `widget.views._process_guest_booking()` locks the clinic row, regenerates slots inside the transaction, matches guests by normalized phone, and creates either `confirmed` or `pending` appointments based on clinic approval mode.
- Messenger/widget AI appointment management verifies appointments by clinic context, reference code, and normalized phone before cancel or reschedule actions.
- Current AI rescheduling mutates `Appointment.starts_at` and `Appointment.ends_at` immediately after patient confirmation.
- Staff dashboard modal and calendar drag/drop rescheduling mutate appointments immediately after authenticated clinic-scoped validation.

The new behavior changes patient-initiated rescheduling only. Existing staff reschedule routes should keep their current operational behavior.

## Approved Direction

Add a structured reschedule-request workflow backed by a new model. Patient requests create pending approval records and leave the original appointment unchanged. Clinic owner/staff approval re-validates the requested slot and only then updates the appointment time.

Policy decisions:

- Patient/public channels require clinic approval before the appointment time changes.
- Staff dashboard direct reschedule stays immediate.
- Pending requests do not hold or reserve slots.
- Owner and staff users can approve or decline requests.
- Same-service reschedule only; service, patient, source, status, payment state, and reference code stay unchanged.

## Data Model

Add `AppointmentRescheduleRequest` in `appointments.models`.

Fields:

- `clinic`: foreign key to `Clinic`, used for tenant scoping and dashboard queries.
- `appointment`: foreign key to `Appointment`, related name such as `reschedule_requests`.
- `requested_starts_at`: requested new start time.
- `requested_ends_at`: requested new end time, computed from the existing appointment service duration.
- `status`: `pending`, `approved`, `declined`, `expired`.
- `source`: public source such as `widget`, `chat_widget`, or `messenger`.
- `patient_note`: optional patient-provided reason/details.
- `staff_note`: optional clinic decision note.
- `resolved_by`: nullable user foreign key for the owner/staff user who approved or declined.
- `resolved_at`: nullable timestamp for the decision.
- inherited timestamps from `TimeStampedModel`.

Model validation rules:

- Request `clinic` must match `appointment.clinic`.
- Requested start must be before requested end.
- Requested start must be in the future.
- Request may only target future appointments in `pending` or `confirmed` status.
- Only one pending request may exist per appointment.

The one-pending-request rule can be implemented with a conditional unique constraint on `(appointment)` where `status='pending'`. If the database does not support that cleanly in the current Django/PostgreSQL setup, enforce it inside transaction-locked request creation and cover it with tests.

## Patient/Public Flow

Patients verify appointments with the existing safe identity pattern:

- Clinic is resolved server-side from `clinic_slug` for widget/public channels or `page_id` for Messenger.
- Patient provides appointment reference code.
- Patient provides phone number, matched through normalized phone.
- The system never accepts public appointment IDs, patient IDs, clinic IDs, service IDs, source, status, or ownership values for mutation.

Request flow:

1. Patient asks to reschedule and provides reference code, phone, and desired new date/time.
2. System verifies the appointment belongs to the resolved clinic and is a future `pending` or `confirmed` appointment.
3. System parses the requested time in the clinic timezone when no explicit timezone is supplied.
4. System computes `requested_ends_at` from the existing appointment service duration.
5. System rejects past requested times.
6. System validates that the requested slot is currently valid by calling `validate_slot(clinic, requested_starts_at, requested_ends_at, exclude_appointment=appointment)`.
7. System creates a pending `AppointmentRescheduleRequest` without changing `Appointment.starts_at` or `Appointment.ends_at`.
8. Patient response says the request was sent and must be confirmed by the clinic.

If a pending request already exists for the appointment, reject the new request and tell the patient that the clinic already has a pending reschedule request for that appointment.

## Clinic Dashboard Flow

Dashboard should surface pending requests in an appointment-first way:

- Add a compact pending-reschedule indicator on appointment rows/details where appropriate.
- Add a dashboard section or filtered list for pending reschedule requests.
- Keep actions dense and operational: appointment, patient, current time, requested time, source, submitted time, and Approve/Decline buttons.

Approval flow:

1. Authenticated owner/staff opens a pending request.
2. Approve action uses POST, CSRF protection, clinic-scoped lookup, and `user_can_manage_daily_ops()`.
3. Inside `transaction.atomic()`, lock the clinic row.
4. Re-fetch the pending request through the current clinic.
5. Re-check the appointment is still future and in `pending` or `confirmed` status.
6. Re-run `validate_slot(clinic, requested_starts_at, requested_ends_at, exclude_appointment=appointment)`.
7. If validation passes, update `appointment.starts_at` and `appointment.ends_at`.
8. Mark the request `approved`, set `resolved_by`, `resolved_at`, and optional `staff_note`.

Decline flow:

1. Authenticated owner/staff submits decline by POST.
2. System uses clinic-scoped pending request lookup.
3. System marks the request `declined`, sets `resolved_by`, `resolved_at`, and optional `staff_note`.
4. Appointment remains unchanged.

Because pending requests do not reserve slots, a requested slot can be taken before approval. If approval validation fails, do not mutate the appointment. Keep the request pending and show the clinic a conflict message so staff can decline it or coordinate another time with the patient.

## AI And N8n Changes

The current AI tool contract says `reschedule_verified_appointment` moves the appointment immediately. That must change for patient/public channels.

Preferred change:

- Add or rename to `request_reschedule_verified_appointment`.
- Return `requested: true` and a safe request summary when a pending request is created.
- Keep `find_verified_appointment` as the required lookup step.
- Keep cancellation behavior unchanged unless a separate cancellation-approval feature is requested.

Assistant prompt rules must change:

- Ask for reference code and phone before lookup.
- Use verified appointment lookup before requesting a reschedule.
- Use the server-derived service from lookup for availability checks only.
- Ask for explicit patient confirmation before submitting the request.
- Say “reschedule request sent” or equivalent, not “appointment rescheduled”.
- Explain that the clinic must approve the request.
- Do not use or expose appointment IDs, patient IDs, clinic IDs, service IDs for mutation, status, source, or ownership identifiers.

Existing n8n source tests should be updated so the assistant no longer promises immediate rescheduling.

## Public Browser Management Option

There is currently no browser-based public appointment management page. If added, it should live under `widget` or another public route scoped by clinic slug.

Recommended minimal path:

- `GET /widget/<clinic_slug>/manage/`: form asking for reference code and phone.
- `POST /widget/<clinic_slug>/manage/`: verify appointment and show safe appointment summary plus reschedule request form.
- `POST /widget/<clinic_slug>/manage/reschedule/`: create pending request after CSRF-protected verification.

This page should use generic lookup errors, no numeric appointment IDs, and minimal patient-safe appointment details.

If implementation scope needs to stay smaller, the first release can update only widget AI chat and Messenger AI, then add a public browser management page later.

## Security And Tenant Safety

- Resolve clinic context server-side from `clinic_slug` or `page_id`.
- Scope all dashboard request lookups through the active clinic.
- Never trust client-submitted clinic, appointment, patient, service, status, source, or ownership identifiers.
- Do not expose appointment IDs in patient/public reschedule flows.
- Use generic failure messages for wrong reference/phone combinations.
- Require authentication, active clinic membership, `user_can_manage_daily_ops()`, POST, and CSRF for approval/decline.
- Validate request ownership: request clinic, appointment clinic, appointment patient, and appointment service must remain same-clinic.
- Re-run slot validation at approval time because pending requests do not hold slots.
- Keep n8n tool endpoints protected by `X-N8N-Webhook-Secret`.
- Do not log webhook secrets, page tokens, request payload secrets, or private patient data.

## Error Handling

Patient/public request errors:

- Missing reference code or phone asks for the missing field.
- Wrong reference/phone returns a generic appointment-not-found message.
- Past appointment returns “Past appointments cannot be changed.”
- Cancelled, completed, or no-show appointment returns “This appointment cannot be changed.”
- Invalid date/time returns “Invalid date or time.”
- Requested past time returns “Cannot request a reschedule to the past.”
- Slot validation failures return concise availability errors.
- Existing pending request returns “This appointment already has a pending reschedule request.”

Clinic approval errors:

- Non-member or unauthorized role gets denied.
- Cross-clinic request lookup returns not found.
- Already resolved request cannot be approved or declined again.
- Ineligible appointment status blocks approval.
- Slot conflict at approval shows a clear conflict message and keeps the request pending.

## Notifications

Email templates exist, but appointment email sending is not currently wired as a core behavior. Messenger reminders exist only for Messenger-sourced appointments.

Recommended initial implementation:

- Show dashboard visibility for pending requests.
- Return clear patient-facing request confirmation through the channel where the request was submitted.
- Do not introduce broad email/SMS notification infrastructure in this feature unless separately requested.

Future notification hooks can send:

- Staff notification when a patient submits a reschedule request.
- Patient notification when the clinic approves or declines.
- Reminder flag resets if an approved request moves a Messenger appointment after reminders were already sent.

## Testing Strategy

Add model tests for:

- Request rejects cross-clinic appointment mismatch.
- Request rejects past requested time.
- Request rejects ineligible appointment statuses.
- Only one pending request per appointment is allowed.

Add patient/AI tool tests for:

- Request requires explicit patient confirmation.
- Request verifies reference code and normalized phone.
- Request creates pending record without changing appointment start/end.
- Request preserves appointment service, patient, source, status, payment state, and reference code.
- Request rejects overlaps, closed days, unavailable dates, breaks, outside-hours slots, and past times.
- Widget AI disabled behavior still applies to widget AI tools.
- Messenger AI tool remains scoped by page connection.

Add dashboard tests for:

- Owner/staff can approve a pending request.
- Other clinic user cannot view/approve/decline a request.
- Approval re-runs validation and updates appointment only when valid.
- Conflict at approval does not mutate appointment and keeps request pending.
- Decline leaves appointment unchanged and marks request declined.
- Already resolved request cannot be resolved again.

Add n8n source-contract tests for:

- Shared agent uses request-based reschedule tooling.
- Prompt says clinic approval is required.
- Prompt does not say the appointment was immediately rescheduled.
- Tool payloads inject `page_id` or `clinic_slug` from normalized context, not AI output.
- Prompt forbids AI-supplied tenant and ownership identifiers.

Run at minimum during implementation:

- `python -m pytest appointments/tests.py`
- `python -m pytest messenger/tests.py -k "appointment or reschedule"`
- `python -m pytest dashboard/tests.py -k "reschedule"`
- `python -m pytest widget/tests.py -k "booking or reschedule"`
- `python -m pytest tests/test_n8n_combined_bridge_source.py`
- `python manage.py makemigrations`
- `python manage.py migrate`
- `python manage.py check`

## Non-Goals

- Do not add patient accounts or a patient portal.
- Do not add medical records, prescriptions, inventory, online payments, or marketplace booking.
- Do not allow patients to change service during reschedule.
- Do not make staff dashboard rescheduling approval-based.
- Do not reserve slots for pending reschedule requests.
- Do not change cancellation behavior to require approval.
- Do not add broad notification infrastructure unless explicitly requested.
- Do not expose appointment management through numeric appointment IDs.
