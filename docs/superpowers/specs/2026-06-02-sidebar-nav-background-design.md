# Sidebar Nav Background Design

## Goal

Refine the dashboard sidebar nav item hover and active states so they feel calmer and more operational while staying aligned with the Neon Aqua Clinical system.

## Approved Scope

- Keep the existing `.cf-sidebar` shell background unchanged.
- Keep sidebar nav text and icon colors unchanged.
- Change only the `.cf-nav-link:hover` and `.cf-nav-link-active` background treatments.
- Preserve the aqua active inset accent.
- Preserve the existing dashboard sidebar structure, templates, URLs, labels, and mobile behavior.

## Design

The hover state should use `background: rgba(5, 47, 58, .18);` instead of the current light aqua wash. This makes hover feel less flashy while still clearly interactive on the teal sidebar.

The active state should use `background: linear-gradient(90deg, rgba(5, 47, 58, .34), rgba(8, 145, 178, .18));` with the existing aqua inset accent. This keeps the active page easy to identify without increasing glow or changing nav text color.

## Implementation Notes

- Update `static/css/clinicflow.css` only for the sidebar nav hover and active background declarations.
- Update `tests/test_design_system.py` expectations that lock the sidebar treatment.
- Do not modify dashboard templates for this change.

## Verification

- Run the targeted design-system test that checks the sidebar treatment.
- Run `python manage.py check` after the CSS/test update.
