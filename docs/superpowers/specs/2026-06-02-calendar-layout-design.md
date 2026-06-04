# Calendar Layout Design

## Goal

Update the dashboard calendar page so its layout matches the provided reference: compact navigation controls on the left, centered month title, view controls on the right, and a large grid-first calendar. Keep the existing ClinicFlow color system and appointment behavior unchanged.

## Approved Direction

Use **Option A: Screenshot Header + Visible Filters**.

- Previous, next, and today controls sit on the left of the calendar header.
- The active FullCalendar title sits centered in the same header row.
- Month, week, and day controls sit on the right.
- Service/status filters and Add appointment stay visible in a compact row above and outside the calendar card.
- The calendar grid gets more visual priority, with screenshot-like spacing, borders, weekday headers, and event density.

## Scope

Primary implementation files:

- `templates/dashboard/calendar.html`
- `static/css/clinicflow.css`
- Calendar/design-system tests that assert the current toolbar structure or visual hooks

The change is presentation-only. It must preserve:

- FullCalendar event fetching from `dashboard:calendar_events`
- Drag/drop rescheduling through `dashboard:calendar_reschedule`
- HTMX appointment detail modal loading
- Calendar refetch behavior after modal edits, cancellations, reschedules, and status updates
- Service and status filter behavior
- Existing appointment status colors and ClinicFlow design tokens
- Existing route names, DOM IDs used by tests/JavaScript, and HTMX targets

## Layout Details

The current page header can remain, but the card content should become more calendar-dominant.

Inside the calendar card:

1. Add a compact tools row above and outside the calendar card.
2. Keep Service, Status, and Add appointment in that top tools row.
3. Add a dedicated calendar header row as the first row inside the calendar card.
4. Move navigation buttons into the left header cluster.
5. Add a visible center title that is kept in sync with FullCalendar's current date/view.
6. Move view buttons into the right header cluster.
7. Keep the status legend available without letting it dominate the top of the calendar.
8. Let the calendar area expand to fill the card below the controls.

On narrow screens, controls should wrap cleanly instead of overflowing. The title should remain readable, and the calendar should still be usable without requiring a separate frontend framework.

## FullCalendar Styling

Use CSS overrides scoped to the calendar page or `#calendar` so the grid resembles the reference while retaining the current theme:

- Subtle card background and border around the grid.
- Clear weekday header row with uppercase labels.
- Thin, consistent day-cell borders.
- Muted adjacent-month days.
- Compact, rounded events that keep status colors and clickable/drag-ready behavior.
- Readable event text with no color changes beyond current status mappings.

## Data Flow And Behavior

No server-side data flow changes are required.

The JavaScript should continue initializing FullCalendar in `templates/dashboard/calendar.html`. It may add a small helper that updates the centered title after render, navigation, and view changes. Existing event source, event click, event drop, filter listeners, and `calendar-refetch` listener must stay intact.

## Testing

Update or add focused tests for:

- Calendar template has the new title element and header clusters.
- Existing required IDs remain: `calendar`, `calendar-prev`, `calendar-next`, `calendar-today`, `filter-service`, and `filter-status`.
- Existing view switch buttons remain with `data-calendar-view` values for month, week, and day.
- Existing accessibility hooks remain for the appointment modal and loading state.
- Existing calendar event/reschedule tests continue passing.

## Non-Goals

- Do not change the color palette.
- Do not add a patient portal, booking marketplace, payments, or any new appointment feature.
- Do not replace FullCalendar.
- Do not introduce React, Next.js, or a separate frontend.
- Do not change appointment scoping, validation, permissions, or scheduling rules.
