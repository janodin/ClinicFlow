# Calendar Responsive Month-First Design

## Context

The dashboard Calendar currently uses FullCalendar with a custom toolbar, filters, status legend, event modal, and responsive behavior that switches phones to `timeGridDay`. The requested direction is month-first on every screen, including phones and tablets.

## Goal

Make the Calendar page responsive, readable, and design-system aligned while keeping `dayGridMonth` as the initial and default view across all screen sizes.

## Approved Direction

Use a responsive month grid with safe horizontal scrolling on small screens. Preserve Day and Week as optional views, but do not automatically switch phones away from Month.

## Design

- Keep `dayGridMonth` as `initialView` for all screens.
- Remove automatic phone switching from Month to Day in `syncCalendarViewport`.
- Keep Month, Week, and Day controls available, but make the active view visually clear with `aria-pressed` and a selected button treatment.
- Keep operational density: compact controls, compact legend, and scannable event pills.
- Use horizontal scrolling on small screens rather than compressing the month grid until event text becomes unreadable.
- Move inline Calendar height and event cursor styling into `static/css/clinicflow.css`.
- Replace fragile fixed viewport height with `100dvh`-based CSS that allows safe scrolling when toolbar/header content wraps.
- Keep filters above the Calendar card and stack them cleanly on tablet/phone widths.
- Keep the legend compact but make status mapping clearer with a small status dot or similarly subtle status cue.
- Preserve all existing URLs, HTMX modal loading, Alpine modal state, filter IDs, and calendar endpoint behavior.

## UI And UX Fixes

- Add loading feedback for all event fetches using FullCalendar `loading(isLoading)` and the existing `#calendar-loading` live region.
- Add event-fetch error feedback so staff are not left with an empty/stale calendar silently.
- Disable drag/drop on coarse pointers to avoid accidental mobile reschedules.
- Prevent completed and cancelled events from appearing draggable where event status data is available.
- Add a scoped HTMX error fallback for the appointment detail modal so it does not stay stuck on the spinner after a failed detail request.
- Improve optional Week/Day view styling by adding scoped `#calendar .fc-timegrid-*` styles, even though Month remains the default.

## Design-System Requirements

- Use existing `cf-*` components and CSS variables before adding new classes.
- Keep dashboard Calendar operational, not marketing-like.
- Maintain WCAG-readable controls, badges, event text, loading messages, and modal fallback content.
- Keep appointment statuses visually distinct.
- Use Inter and tabular numerics for calendar dates/times where practical.
- Avoid heavy glow inside the Calendar grid.

## Test Strategy

- Update static design-system tests so month-first behavior is explicit:
  - `initialView: 'dayGridMonth'` or equivalent month-first assertion.
  - no phone auto-switch to `timeGridDay`.
  - `syncCalendarViewport` still updates height/density and calls `calendar.updateSize()`.
- Add CSS contract coverage for small-screen Calendar layout:
  - Calendar card safe `100dvh` sizing.
  - stacked header/filter behavior.
  - horizontal month-grid scrolling.
  - mobile title wrapping.
- Add contract coverage for active view buttons:
  - `aria-pressed` state exists.
  - JS syncs selected view state on `datesSet`.
- Add contract coverage for loading/error UX:
  - FullCalendar `loading` callback toggles `#calendar-loading`.
  - event fetch failure dispatches a toast or updates an accessible inline error.
- Add contract coverage for touch-safe drag/drop:
  - coarse pointers disable calendar editability or drag start.
  - completed/cancelled events are not treated as draggable.

## Out Of Scope

- No new calendar backend features.
- No patient portal, payments, medical records, prescriptions, inventory, marketplace booking, or AI automation.
- No React, Next.js, or separate frontend.
- No redesign of the dashboard shell outside Calendar-specific responsive needs.
