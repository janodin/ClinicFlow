# Guarded Delete Functionality Design

## Goal

Add delete functionality for services, appointments, and patients without destroying clinic history or weakening tenant boundaries.

The feature should give staff a clear way to remove mistaken or unused records while preserving real appointment history, exports, patient visit history, and booking integrity.

## Current State

Services already support `Archive` and `Restore` through POST-only, clinic-scoped dashboard actions. Public booking, widget booking, staff appointment forms, Messenger, and AI service selection already exclude archived services.

Appointments already support `Cancel`, which marks the appointment cancelled, stores an optional cancellation reason, and frees the slot because cancelled appointments are excluded from overlap checks. Appointment notes belong to appointments with cascade deletion.

Patients can be created, edited, searched, viewed, and merged. Merge moves appointments from the duplicate patient to the primary patient, then deletes the duplicate.

`Appointment.service` and `Appointment.patient` both use `on_delete=PROTECT`, so services and patients with appointment history cannot be hard-deleted safely.

## Options Reviewed

### Recommended: Guarded Hard Delete

Allow hard delete only where it is safe, and block deletion when appointment history depends on the record.

Trade-offs:

- Keeps the current schema and avoids broad migrations.
- Preserves clinic history and patient-facing appointment references.
- Requires clear blocking messages for records with history.
- Still lets users remove unused services, mistaken appointments, and no-history patients.

### Alternative: Soft Delete For Everything

Add deleted-state fields and hide deleted records from normal views.

Trade-offs:

- Preserves audit history for all records.
- Requires migrations and careful updates to dashboard, search, export, widget, Messenger, duplicate detection, patient matching, and scheduling querysets.
- Higher implementation risk for V1.

### Not Recommended: Cascading Permanent Delete

Allow deletion to remove dependent appointment history.

Trade-offs:

- Simple to explain but unsafe for clinic operations.
- Would destroy exports, patient histories, internal notes, appointment references, and audit trails.
- Conflicts with the current `PROTECT` relationships.

## Approved Direction

Use guarded hard delete while preserving existing archive and cancel behavior.

Approved rules:

- Services keep `Archive` as the normal remove action.
- Services can be permanently deleted only when archived and when they have zero appointments.
- Appointments keep `Cancel` as the normal operational remove action.
- Appointments can be permanently deleted for mistaken or test records after confirmation.
- Patients can be permanently deleted only when they have zero appointments.
- Patients with appointment history cannot be deleted; users should merge duplicates instead.

## Service Delete Design

Add `dashboard:delete_service` as a POST-only action scoped through `clinic.services`.

Behavior:

- If the service belongs to another clinic, return 404.
- If the user cannot manage daily operations, return 403.
- If the service is not archived, block deletion and tell the user to archive it first.
- If the service has appointments, block deletion and keep it archived for appointment history.
- If the service is archived and has no appointments, delete it permanently.

UI:

- Keep `Archive` on active service cards.
- Keep `Restore` on archived service cards.
- Add `Delete` only on archived service cards.
- Use a confirmation modal in the service card partial with `cf-btn-danger`, CSRF, and POST.
- HTMX should refresh `#services-list-container` and show a toast.

## Appointment Delete Design

Add `dashboard:delete_appointment` as a POST-only action scoped through `clinic.appointments`.

Behavior:

- If the appointment belongs to another clinic, return 404.
- If the user cannot manage daily operations, return 403.
- Delete the appointment permanently after confirmation.
- Appointment notes cascade as existing model behavior.
- Cancellation remains the preferred action for real appointments.

UI:

- Add `Delete permanently` in the appointment detail modal as a separate delete mode, visually separated from `Cancel appointment`.
- Do not replace the existing cancel flow.
- Do not add a direct appointment row delete button in this pass; users delete appointments from the detail modal opened by View.
- From the appointment list detail modal, successful HTMX delete should refresh `#appointments-table`, close the modal, and show a toast.
- From the calendar modal, successful delete should trigger `calendar-refetch`, close the modal, and show a toast.
- From patient visit history, successful delete should refresh `#patient-detail-content`, close the modal, and show a toast.

## Patient Delete Design

Add `dashboard:delete_patient` as a POST-only action scoped through `clinic.patients`.

Behavior:

- If the patient belongs to another clinic, return 404.
- If the user cannot manage daily operations, return 403.
- If the patient has appointments, block deletion and explain that appointment history must be preserved.
- If the patient has no appointments, delete the patient permanently.
- Future guest booking with the same phone may create a new patient record.

UI:

- Add `Delete` to patient rows and patient detail actions with confirmation.
- On patient list success, refresh `#patient-list` and show a toast so pagination stays accurate.
- On patient detail success, redirect to the patient list with a success message.
- On blocked delete, keep the user on the current screen and show an error message.

## Security And Tenant Boundaries

All delete views must:

- Use `@login_required`.
- Use `@require_POST`.
- Rely on CSRF-protected forms or HTMX CSRF headers.
- Resolve the active clinic with `_clinic_or_redirect(request)`.
- Look up objects only through clinic-scoped managers: `clinic.services`, `clinic.appointments`, or `clinic.patients`.
- Check `user_can_manage_daily_ops(get_active_membership(request.user))` before deleting.
- Never trust client-submitted clinic, service, appointment, patient, status, source, or ownership values.
- Return 404 for cross-clinic objects.
- Return 403 for users without delete permission.

## Testing Strategy

Add or update tests for:

- Delete endpoints require POST.
- Unauthenticated users cannot delete.
- Cross-clinic records return 404.
- Users without daily-ops permission cannot delete.
- Archived service with no appointments can be deleted.
- Active service deletion is blocked until archived.
- Service with appointments cannot be deleted.
- Appointment delete removes the appointment and cascades notes.
- Appointment delete from calendar emits `calendar-refetch` and close-modal triggers.
- Patient with no appointments can be deleted.
- Patient with appointments cannot be deleted.
- Patient merge still moves appointments then deletes the duplicate.
- HTMX responses retarget or refresh the correct containers and emit success/error toasts.
- Template/design-system tests cover confirmation modals, danger button styling, CSRF forms, and no unsafe GET delete links.

Run at minimum after implementation:

- `python -m pytest services/tests.py patients/tests.py dashboard/tests.py -q`
- `python -m pytest tests/test_design_system.py -q`
- `python manage.py check`

## Migration Plan

No model migration is required for guarded hard delete.

Do not change `Appointment.service` or `Appointment.patient` from `PROTECT`. These relationships are the guardrail that protects clinic history.

## Non-Goals

- Do not cascade-delete services or patients with appointment history.
- Do not change appointment cancellation semantics.
- Do not add soft-delete fields in this pass.
- Do not add patient portal, medical records, prescriptions, payments, inventory, marketplace booking, or new frontend stack.
- Do not expose delete actions through public widget or webhook endpoints.
