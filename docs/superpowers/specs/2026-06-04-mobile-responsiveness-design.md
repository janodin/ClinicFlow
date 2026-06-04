# Mobile Responsiveness Design

## Context

KliniAssist is a Django, Tailwind CSS, HTMX, Alpine.js, and FullCalendar clinic appointment SaaS. The UI uses the Neon Aqua Clinical system from `DESIGN.md`, with reusable `cf-*` styles in `static/css/kliniassist.css`.

Five read-only audits reviewed mobile responsiveness across:

- Dashboard shell and shared dashboard pages
- Calendar, appointments, scheduling, and availability pages
- Patients, patient detail, duplicate merge, and services pages
- Auth, onboarding, and privacy pages
- Guest booking widget and widget embed surfaces

The approved approach is a structured page-family pass: first apply safe global mobile improvements, then targeted fixes for each page family. The work targets phones and small tablets below `1024px`.

## Goals

- Preserve the current Django template stack and Neon Aqua Clinical visual direction.
- Prevent clipped or unreachable content on mobile and small tablet widths.
- Improve touch target size for common mobile actions.
- Keep dense operational dashboard screens table-first where appropriate, but make overflow intentional and usable.
- Stabilize FullCalendar behavior across mobile viewport changes and orientation changes.
- Make widget booking safe inside narrow embedded contexts and mobile keyboards.
- Preserve existing public URLs, form field names, HTMX targets, Alpine hooks, FullCalendar hooks, and guest booking safeguards.

## Non-Goals

- No redesign of the product visual system.
- No React, Next.js, separate frontend, or new UI framework.
- No patient portal, medical records, payments, marketplace booking, or real AI automation.
- No broad refactor of dashboard data flow or booking behavior.
- No replacement of dense staff workflows with marketing-style layouts.

## Approach

### Global Mobile Baseline

Add mobile rules and small template adjustments that improve every page without changing desktop behavior:

- Increase mobile touch targets for `.cf-btn`, `.cf-btn-xs`, row actions, icon buttons, inputs, selects, textareas, and checkbox hit areas.
- Add wrapping and min-width safeguards for long names, slugs, URLs, reference codes, search result labels, and table/card text columns.
- Improve mobile modal behavior with safe scrolling, full-width actions where appropriate, and consistent focus handling for patient/service modals.
- Add visible scroll affordances for intentionally wide operational tables rather than silently clipping content.

### Dashboard Shell And Shared Pages

Fix shell-level issues that affect all dashboard pages:

- Ensure mobile sidebar overlay stacks above the bottom navigation.
- Add a compact `More` destination to the mobile bottom navigation for setup/settings pages that are not primary appointment operations.
- Keep the left sidebar desktop pattern intact.
- Prevent home and settings cards from overflowing when patient, service, clinic, slug, or Facebook page names are long.

### Calendar And Appointments

Make appointment-first workflows usable on phones and small tablets:

- Replace fragile FullCalendar mobile parent-height assumptions with explicit mobile sizing.
- Recompute calendar view, `dayMaxEvents`, and size on media query/orientation changes.
- Hide week/month view buttons on phones below `640px`; keep them available on small tablets where there is enough width.
- Make appointment filters less tall on mobile by keeping search visible and grouping status, date, doctor, service, and source controls behind an advanced filters disclosure.
- Improve appointment row action reachability in wide tables by making the action column sticky on mobile scroll containers.
- Keep HTMX appointment detail and appointment form targets unchanged.

### Patients And Services

Preserve management workflows while fixing mobile usability:

- Increase row/card action tap targets for patient, duplicate merge, and service actions.
- Add wrapping and `min-w-0` safeguards to patient detail headers, search results, visit history, service names, and service descriptions.
- Reuse consistent modal focus behavior for patient add/edit and service add/edit flows.
- Keep desktop patient and service tables/cards unchanged except for mobile-safe behavior.

### Auth, Onboarding, And Public Pages

Make public setup flows usable with mobile browser chrome and keyboards:

- Use dynamic viewport units and start alignment on mobile for login, signup, and onboarding.
- Add safe-area bottom padding for long onboarding forms.
- Improve checkbox hit areas for consent and business-hours open toggles.
- Use stronger contrast for small text links and primary button text where current aqua-on-white or white-on-aqua contrast is weak.
- Keep auth forms and onboarding field names unchanged.
- Move the privacy policy shell into the shared design system while preserving policy text content.

### Widget And Booking Surfaces

Protect the guest booking flow in narrow iframes and mobile keyboard contexts:

- Fix widget shell width so parent padding cannot cause horizontal clipping.
- Add header wrapping/truncation safeguards for long clinic names.
- Add safe-area and scroll padding for lower form fields and confirm buttons.
- Make slot grids adapt at very narrow widths.
- Add safe wrapping for booking reference codes and error messages.
- Add mobile-friendly autocomplete and input types without changing field names or HTMX behavior.
- Improve launcher/iframe dimensions for mobile safe areas while preserving `postMessage` minimize behavior.

## Testing And Verification

- Run targeted template/design tests affected by changed `cf-*` classes and templates.
- Run `python manage.py check`.
- Use Playwright or browser viewport checks for representative pages at phone and small tablet widths.
- Verify key flows manually where browser automation is practical: dashboard shell, calendar, appointments list/detail, patients, services, login/signup/onboarding, and widget booking.
- Confirm no model changes are introduced; if a model change becomes necessary, run `makemigrations`, `migrate`, and `check` per project rules.

## Risks And Constraints

- Existing uncommitted changes are present in the worktree, including `static/css/kliniassist.css` and design tests. Changes must be made carefully without reverting unrelated work.
- Wide operational tables are intentional for clinic staff workflows. The design should make table overflow usable, not blindly convert every table into cards.
- Widget changes must preserve guest booking safeguards, field names, HTMX targets, and embedded launcher behavior.
- Calendar changes must preserve FullCalendar hooks and event loading behavior.
