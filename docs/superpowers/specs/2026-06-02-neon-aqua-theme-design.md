# Neon Aqua Theme Design

## Goal

Repaint ClinicFlow from the previous indigo/navy theme to a screenshot-inspired neon aqua clinical theme. The app should feel bright, cool, and glow-accented while preserving readable clinic operations screens and appointment status meaning.

## Approved Direction

Use the **Neon Aqua Clinical** approach:

- Primary brand color: electric aqua/cyan.
- Main dark shell: deep teal/navy instead of purple navy.
- Soft surfaces: ice-cyan and cool white.
- Accent treatment: subtle cyan glow, not full gaming-style black neon.
- Preserve the current layout, component geometry, Django templates, Tailwind utility strategy, and `cf-*` reusable CSS layer.

## Scope

Update the theme comprehensively in:

- `DESIGN.md` design tokens and descriptive language.
- `static/css/clinicflow.css` CSS variables, gradients, sidebar, buttons, focus rings, compatibility color aliases, widget/chat accents, and shadows.
- Widget accent default and fallback in `clinics.models.Clinic`.
- Service default color in `services.models.Service`.
- Assistant/widget settings default preview color.
- Email template hardcoded colors.
- FullCalendar appointment confirmed/info colors in `dashboard.views.calendar_events`.
- Design-system tests that assert token values and forbidden legacy colors.

## Color System

Target tokens:

- Brand: `#06b6d4`.
- Brand hover/info: `#0891b2`.
- Brand strong: `#0e7490`.
- Brand soft: `#ecfeff`.
- Brand soft hover: `#cffafe`.
- Dashboard dark: `#052f3a`.
- Ink: `#083344`.
- Secondary ink: `#164e63`.
- Muted text: `#527486`.
- Surface strong: `#f0fdff`.
- Surface muted: `#e6faff`.
- Input line: `#8ed8e8`.
- Focus ring: `rgba(6, 182, 212, .24)`.

Semantic colors remain distinct:

- Pending/booked: amber/warm.
- Confirmed/info: aqua.
- Completed: green/teal.
- Cancelled/error: ruby/red.
- No-show: gray.

## Testing

Run targeted design-system tests after implementation. Because this is a visual/theme-only change with no model field definition change besides a default constant, no migration should be needed unless Django detects a field default migration.
