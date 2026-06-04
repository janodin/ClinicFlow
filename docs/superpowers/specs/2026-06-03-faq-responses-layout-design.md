# FAQ Responses Layout Design

## Context

The FAQ Responses section in `templates/dashboard/assistant_settings.html` currently uses one flat card that contains the create form and a divided list of FAQ rows. The section works functionally, but the visual hierarchy is weak: the form and list blend together, rows feel unfinished, and row actions compete with the question and answer content.

The redesign must follow `DESIGN.md` and the Neon Aqua Clinical system: white and ice-cyan surfaces, deep teal text, electric aqua primary actions, compact rounded controls, dashboard density, and reusable `cf-*` CSS patterns.

## Goals

- Improve the full FAQ Responses section layout, not only button styling.
- Separate FAQ creation from FAQ management with a clearer two-column composition.
- Make existing FAQs feel like polished dashboard cards instead of a plain divided list.
- Keep Edit and Delete as icon-only controls, per user preference.
- Keep visibility readable with explicit `Visible` and `Hidden` status badges.
- Preserve current Django forms, HTMX inline edit behavior, delete confirmation modal, POST-only actions, CSRF, and clinic-scoped dashboard behavior.

## Non-Goals

- Do not add AI automation, new FAQ matching behavior, or patient portal features.
- Do not introduce React, a separate frontend, or non-Django rendering.
- Do not change FAQ model fields, URLs, form field names, or server-side ownership behavior.
- Do not hide visibility state behind an ambiguous icon-only control.

## Approved Layout

Use a split composer and list layout inside the existing Assistant Settings page.

- The outer section remains a dashboard `cf-card`, but gains a richer section header with a small aqua icon well, title, helper text, and summary pills.
- The left column is an aqua-soft composer panel for adding a new FAQ.
- The right column is a current responses panel that renders each FAQ as an individual card.
- On mobile and narrow dashboard widths, the layout stacks with the composer first and FAQ cards below.

## Header

The FAQ header should communicate what the section affects.

- Title: `FAQ Responses`.
- Eyebrow or helper label: patient-facing assistant copy.
- Description: short text explaining that these answers appear in the booking widget and help patients self-serve before booking.
- Summary treatment: one grouped white capsule containing two aqua-soft mini-pills: `{total} total` and `{visible} visible`.
- Both mini-pills use aqua-soft background, stronger teal text, compact pill geometry, and tabular numerics so the summary feels like a designed dashboard element instead of raw text.

The view should provide the counts explicitly so the template stays readable.

## Add Composer

The create form should move into a visually distinct composer panel.

- Use an aqua-soft background such as `var(--cf-bg-strong)` or `var(--cf-surface-tint)`.
- Use a thin `var(--cf-line)` border, compact radius, and subtle internal spacing.
- Keep the current `ClinicFAQForm` fields: question, answer, and is_active.
- Keep `Add FAQ` as a filled aqua pill button.
- Keep the checkbox readable as `Visible to patients`, while preserving the underlying form field and checkbox behavior.
- Keep field labels and errors accessible and consistent with existing `cf-label`, `cf-input`, `cf-textarea`, `cf-checkbox`, and `cf-error` patterns.

## FAQ Cards

Each FAQ row should become a card-like item while preserving the `faq_row.html` partial and HTMX replacement target.

- Use an `article` or card container with `id="faq-row-{{ faq.id }}"` so HTMX still replaces a single FAQ item.
- Use a white surface, `var(--cf-line)` border, compact radius, and subtle card shadow.
- Show a small question icon well or `Q` marker on the left of the question.
- Use deep teal for the question and muted teal for the answer.
- Preserve wrapping guards for long questions and answers with `min-w-0`, `break-words`, and `whitespace-pre-wrap` where needed.
- Keep inactive FAQs visibly distinct through the `Hidden` badge and a quiet neutral icon well, not by lowering text contrast below accessibility requirements.

## Row Actions

Edit and Delete must be icon-only controls.

- Edit uses the Lucide `pencil` icon.
- Delete uses the Lucide `trash-2` icon and ruby danger color.
- Each icon button must include `aria-label` and `title` so the visible label can be removed without losing accessibility.
- Icon controls should be quiet circular or pill controls with at least 32px compact desktop size and enough spacing for mobile use.
- Focus states must use the existing `cf-*` focus treatment.

Visibility should remain explicit.

- Show a `Visible` or `Hidden` badge near the card header.
- Keep a short text action such as `Show` or `Hide` in the row footer, or retain a text-labeled visibility toggle if that fits the existing action cluster best.
- Avoid eye-only visibility controls because they are ambiguous as both state and action.

## Inline Edit State

Inline editing should remain in the same FAQ card.

- The edit form keeps question and answer labels, current field IDs, and validation errors.
- Save remains a primary compact button.
- Cancel remains a quiet secondary or ghost action.
- The card should not jump into a completely different visual system while editing.

## Empty State

The empty state should stay simple but align with the new layout.

- Keep the existing icon-driven empty state concept.
- Place it in the right-side list area when no FAQs exist.
- Explain that adding common questions helps patients book faster.
- Do not add decorative glow that distracts from the dashboard workflow.

## CSS And Template Approach

Prefer reusable `cf-*` CSS classes in `static/css/clinicflow.css` for the new FAQ layout rather than repeating long raw utility strings.

Suggested class concepts:

- `cf-faq-shell` for the section content wrapper.
- `cf-faq-header` for the title, description, and counters.
- `cf-faq-layout` for the responsive split grid.
- `cf-faq-composer` for the left add form panel.
- `cf-faq-list` for the right response list.
- `cf-faq-card` for each FAQ item.
- `cf-faq-icon-action` for icon-only Edit/Delete controls.

Use class names only if they keep the implementation cleaner. Do not introduce unnecessary CSS if a small number of existing `cf-*` classes and Tailwind utilities is clearer.

## Testing

Update targeted design-system tests after implementation.

- Assert FAQ row controls still include accessible labels for edit and delete.
- Update tests that currently expect visible `Edit` and `Delete` text in `faq_row.html`.
- Assert icon-only action controls use the agreed classes and keep comfortable compact sizing.
- Assert mobile wrapping guards remain present for FAQ question and answer text.
- Assert the new split layout class or template structure exists in `assistant_settings.html`.

Run targeted verification with the project virtual environment after implementation.

- `python manage.py check`
- `pytest tests/test_design_system.py -k faq`

## Acceptance Criteria

- FAQ Responses uses the approved split composer and FAQ list layout.
- FAQ rows render as polished card items, not a plain divided list.
- Edit and Delete are icon-only and accessible.
- Visibility remains readable and not ambiguous.
- The layout is responsive and does not overflow on mobile.
- Existing create, edit, toggle, and delete behavior remains intact.
- Targeted tests pass.
