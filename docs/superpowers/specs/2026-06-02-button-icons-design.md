# Button Icons Design

## Goal

Add icons to all visible app buttons and button-styled links so actions are easier to scan while preserving the existing KliniAssist Neon Aqua Clinical design system.

## Scope

Apply semantic Lucide icons to `cf-btn` controls across dashboard, auth, booking, and widget templates. Icon-only controls such as `cf-icon-btn` stay unchanged. Existing labels, URLs, form behavior, HTMX targets, Alpine hooks, DOM IDs, and button types must be preserved.

## Design Direction

Use a left-aligned Lucide icon before the text label for text buttons. Standard icon size is `h-4 w-4`; compact inline utility buttons may use `h-3 w-3` when already established. Buttons keep the existing `cf-btn` spacing, pill geometry, color states, and touch targets from `static/css/clinicflow.css`.

## Icon Mapping

Use action-specific icons rather than decorative icons:

- Create/add appointment, patient, service, FAQ, or unavailable date: `plus-circle`, `calendar-plus`, or `user-plus` depending on object type.
- Save, update, restore, confirm, or merge: `save`, `check`, `check-circle-2`, or `git-merge` depending on context.
- View, preview, open, or details: `eye`, `external-link`, or `arrow-right`.
- Edit or configure: `pencil` or `settings`.
- Back, close, cancel, or clear: `arrow-left`, `x`, or `x-circle`.
- Delete, archive, disconnect, or destructive confirmation: `trash-2`, `archive`, `unlink`, or `ban`.
- Copy and duplicate checks: `copy` and `scan-search`.

## Accessibility

Icons are supplemental. Text labels remain the accessible name for labeled buttons. Existing `aria-label` attributes on icon-only controls remain unchanged. Icon color inherits the button color so contrast stays aligned with existing button states.

## Testing

Run Django template/system checks after edits. Because this is template-focused, also verify that pages using dynamic Lucide rendering still initialize icons after HTMX swaps where existing code already does so.
