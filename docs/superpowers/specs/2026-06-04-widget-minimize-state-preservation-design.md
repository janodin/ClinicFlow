# Widget Minimize State Preservation Design

## Goal

When a patient minimizes the website booking widget and opens it again on the same host page, the widget should resume exactly where the patient left off instead of returning to the home choice screen.

This applies to both widget paths:

- `Book an Appointment`
- `Chat with Assistant`

The behavior is same-page only. A browser refresh, new tab, or new visit does not need to preserve in-progress widget state and can start from the normal widget home screen.

## Current State

The JavaScript embed in `widget.views.embed_js()` creates the widget iframe on the first launcher click, hides the iframe on `kliniassist-minimize`, and shows the same iframe again on the next launcher click.

That means the iframe can already preserve in-memory state while the host page stays loaded.

The reset happens inside `templates/widget/widget.html`: the `minimize()` method posts `{type: 'kliniassist-minimize'}` to the parent page, then sets `this.mode = 'home'`. This forces the widget back to the home screen even though the iframe itself was not destroyed.

## Approved Direction

Use minimal same-page state preservation.

The widget minimize action should only collapse the iframe through the existing parent `postMessage` flow. It should not reset Alpine state or clear in-progress form fields.

Approved choices:

- Preserve state only while the same host page remains open.
- Preserve typed but unsubmitted values, including full name, phone, email, reason, collect-info fields, and unsent chat text.
- Do not add `localStorage`, `sessionStorage`, database drafts, or cross-refresh persistence.

## Runtime Behavior

For the recommended JavaScript launcher embed:

1. Visitor clicks the launcher.
2. Parent script creates or shows the existing widget iframe.
3. Visitor starts a booking or chat.
4. Visitor clicks widget minimize.
5. Widget posts `{type: 'kliniassist-minimize'}` to the parent frame.
6. Parent script hides the iframe and shows the launcher.
7. Visitor clicks the launcher again.
8. Parent script shows the same iframe.
9. The widget remains on the same screen with the same in-memory state and typed field values.

Expected examples:

- If the patient is on booking step 2 after choosing a service, reopening returns to date and time selection.
- If the patient is on booking step 3 with partially typed full name or phone, reopening keeps the same step and typed values.
- If the patient is in chat collect-info, reopening keeps the conversation, chat state, and typed collect-info fields.
- If the patient has typed an unsent chat message, reopening keeps it.

## Scope Boundaries

This design intentionally avoids persistent drafts.

Refresh or navigation behavior is intentionally out of scope:

- Host page refresh: widget can start fresh.
- Iframe refresh: widget can start fresh.
- New browser tab or new visit: widget can start fresh.

Reset behavior should remain explicit:

- Successful booking keeps the current success behavior.
- `Book Another Appointment`, chat `Book another`, chat restart, and chat cancel should continue to reset or restart according to the current flow.
- Validation errors should continue to render inside the current flow and should not create partial appointments.

## Implementation Shape

The expected code change is small:

- Keep `window.parent.postMessage({type: 'kliniassist-minimize'}, '*')` in `minimize()`.
- Remove the `this.mode = 'home'` reset from `minimize()`.
- Do not add browser storage or server-side draft storage.

This uses the iframe's existing lifecycle as the state container. Since the parent script hides rather than destroys the iframe, Alpine component state and normal DOM input values remain available when the iframe is shown again.

## Security And Tenant Boundaries

The change does not alter tenant scoping or booking authority.

- Public clinic resolution remains based on the server-side `clinic_slug` route.
- Client-submitted service, slot, source, patient, and ownership values remain untrusted.
- Appointment creation still goes through existing server-side validation.
- Patient phone matching, slot regeneration, double-booking prevention, clinic row locking, and cancelled-slot behavior remain unchanged.
- No patient draft data is persisted to browser storage, server sessions, or the database by this change.

## Error Handling

No new error paths are introduced.

- If the parent page handles `kliniassist-minimize`, the iframe collapses and can be reopened with its current in-memory state.
- If the widget is opened directly outside an iframe, clicking minimize should not reset the UI. The postMessage branch already only runs when `window.parent !== window`.
- Existing HTMX booking errors and chat fallback behavior remain unchanged.

## Testing Strategy

Add or update targeted tests for the widget template contract:

- `minimize()` still posts `kliniassist-minimize` to the parent frame.
- `minimize()` no longer sets `this.mode = 'home'`.
- The widget still exposes the current behavior hooks used by booking, slots, HTMX, and chat.

Manual verification should cover:

- Booking step 2 minimize/reopen resumes on step 2.
- Booking step 3 minimize/reopen preserves typed name, phone, email, and reason.
- Chat mode minimize/reopen preserves conversation state and unsent typed chat input.
- Refreshing the host page starts fresh, which is expected for same-page-only preservation.

Run at minimum after implementation:

- `python -m pytest widget/tests.py`
- `python -m pytest tests/test_design_system.py -k widget`
- `python manage.py check`

## Non-Goals

- Do not persist drafts across refreshes or visits.
- Do not add `localStorage` or `sessionStorage`.
- Do not add server-side draft models or migrations.
- Do not change appointment creation, confirmation, slot validation, or patient matching.
- Do not remove the widget home choices.
- Do not change the launcher-first embed behavior.
- Do not introduce React, Next.js, or a separate frontend.
