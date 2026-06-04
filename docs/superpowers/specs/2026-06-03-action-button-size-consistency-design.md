# Action Button Size Consistency Design

## Goal

Make all dashboard row/action clusters visually match the compact action buttons used in the Appointments table.

## Scope

Apply the Appointments action-button size reference to all row/action clusters that represent item-level actions, including:

- Appointments table row actions.
- Patients table row actions and HTMX patient row partials.
- Patient detail appointment-history row actions.
- Services card action clusters.
- FAQ row action cluster.
- Duplicate-patient merge item actions.
- Unavailable-date row actions in both settings and standalone unavailable-date views.

Page-level CTAs, modal footer buttons, calendar controls, pagination, widget buttons, and form submit controls stay unchanged because they are not item-level action clusters.

## Design

Use a shared `cf-row-actions` wrapper as the canonical action-cluster hook. Buttons inside this wrapper should use the same compact scale as the Appointments row actions: `cf-btn-xs`, tight pill padding, small text, and `h-3 w-3 shrink-0` icons.

The existing action color semantics remain unchanged:

- View actions use the muted Appointments view treatment.
- Edit actions keep the secondary/aqua treatment and hover behavior.
- Archive/reschedule actions keep the muted treatment and hover behavior.
- Delete/cancel/deactivate actions keep danger styling.
- Activate/restore actions keep primary styling.

## Implementation Notes

Move the Appointments-specific compact sizing rule from `.cf-appointment-row-actions` to the shared `.cf-row-actions` selector, then add `cf-row-actions` to every row/action cluster in scope. Convert their buttons from `cf-btn-sm` or custom padding overrides to `cf-btn-xs`, and reduce action icons to `h-3 w-3 shrink-0` with `aria-hidden="true"` where appropriate.

## Testing

Update design-system tests to assert that scoped row/action templates use `cf-row-actions`, `cf-btn-xs`, and compact icons. Keep existing tests for button icon presence and action color semantics passing.
