# Required Appointment Email Design

## Goal

Require a valid patient email address whenever an appointment is created or edited. This applies to public widget booking, embedded widget booking, staff dashboard appointment creation, and staff dashboard appointment editing.

## Scope

- Public booking form in the widget and embed.
- Server-side widget booking validation.
- Messenger and widget AI booking helpers that reuse the shared public booking processor.
- Staff appointment form used by dashboard add/edit and calendar modal edit flows.
- Tests for blank email rejection and existing test data updates.

## Non-Goals

- Do not change `Patient.email` at the database schema level.
- Do not require email for patient records outside appointment workflows.
- Do not change patient matching behavior; phone-based matching remains unchanged.
- Do not overwrite existing patient data beyond the current booking flow behavior.

## Behavior

Blank email submissions must be rejected before appointment creation or update. Invalid email submissions continue to use Django email validation and existing widget validation messages. Existing patients without email may remain in the database, but staff must provide an email when creating or editing appointments for them.

## Implementation Approach

Use form and view-level validation instead of a migration. Make `StaffAppointmentForm.patient_email` required. Update widget booking validation so email is required before `validate_email()` runs. Update the widget direct booking input so the client reflects the server requirement.

## Testing

- Add a widget booking regression test that rejects blank email with no patient or appointment created.
- Add a staff appointment form regression test that rejects blank `patient_email`.
- Update existing staff form tests to include valid email where they are testing unrelated slot or service behavior.
