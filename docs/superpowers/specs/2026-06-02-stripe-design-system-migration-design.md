# Stripe Design System Migration Design

## Goal

Make ClinicFlow's UI fully based on the `getdesign` Stripe design system while preserving the existing Django template, HTMX, Alpine.js, FullCalendar, and `cf-*` class architecture.

The migration replaces the current Stone-Sage visual language with the Stripe-inspired system: white and cool off-white surfaces, deep navy ink, sparse indigo CTAs, pill buttons, thin display typography, compact radii, subtle blue shadows, tabular numerics, and gradient-mesh accents on public-facing or brand-forward surfaces.

## Source Of Truth

Root `DESIGN.md` becomes the active Stripe design reference by running:

```powershell
npx getdesign@latest add stripe --force
```

The current ClinicFlow `DESIGN.md` is intentionally replaced because the requested outcome is for all design to be based on Stripe. Future UI work must read and follow the root `DESIGN.md`.

## Architecture

This is a token-first migration, not a component-framework migration.

ClinicFlow does not currently have `package.json`, Tailwind config, PostCSS config, or a frontend build pipeline. It uses Django templates, CDN Tailwind, and `static/css/clinicflow.css`. The Stripe design system installed by `getdesign` is a markdown reference, not generated UI components. Therefore, the implementation adapts the existing CSS and templates instead of introducing React, Next.js, shadcn, npm component packages, or a separate frontend.

The existing `cf-*` CSS layer remains the canonical implementation layer for reusable UI. This keeps dashboard partials, HTMX swaps, forms, modals, tables, toasts, and widget screens stable while changing their visual language.

## Token Mapping

`static/css/clinicflow.css` is remapped from Stone-Sage to Stripe-inspired tokens:

| Existing Role | Stripe-Based Value |
| --- | --- |
| Brand / primary | `#533afd` |
| Brand hover / deep | `#4434d4` |
| Brand pressed / dark | `#2e2b8c` |
| Ink | `#0d253d` |
| Secondary ink | `#273951` |
| Muted ink | `#64748d` |
| Page canvas | `#ffffff` |
| Soft canvas | `#f6f9fc` |
| Warm interlude | `#f5e9d4` |
| Hairline | `#e3e8ee` |
| Input hairline | `#a8c3de` |
| Dark dashboard surface | `#1c1e54` |

Existing semantic appointment states remain understandable and accessible. Status colors use Stripe-compatible tints, but appointment meaning must stay clear: pending/booked, confirmed, completed, cancelled, and no-show cannot become ambiguous.

## Typography

Use Inter as the practical open-source substitute for Stripe's proprietary Sohne typeface.

The global body uses Inter with `font-feature-settings: "ss01"`. Display and page titles use weight 300 with negative letter spacing. KPI values, prices, appointment times, counts, durations, and table numeric columns use tabular numerics with `font-feature-settings: "tnum"`.

The current Cormorant/Manrope/IBM Plex Mono import is removed or replaced by the Inter import.

## Component System

The reusable `cf-*` classes are re-skinned to Stripe patterns:

- `cf-btn`, `cf-btn-primary`, and key CTAs become compact pill buttons with indigo fill.
- Secondary buttons become white pill buttons with indigo text and border.
- Cards use white or cool off-white surfaces, 12px radius, subtle blue shadow, and hairline borders.
- Inputs use 6px radius, white background, cool input hairline, and indigo focus state.
- Tables keep dense operational structure but switch to Stripe ink, hairlines, tabular numeric cells, and quieter row hover states.
- Badges become small pills with restrained Stripe-compatible tints.
- Modals, menus, dropdowns, and toasts retain behavior but use Stripe surfaces, shadows, and typography.
- Calendar events use the same status vocabulary while visually aligning with Stripe colors and smaller radii.

## Template Migration Scope

The implementation updates the primary visual surfaces, not only the root CSS:

- `templates/base.html` font and global asset assumptions.
- `templates/dashboard/base.html` sidebar, topbar, mobile nav, search, menu, and toast shell.
- Dashboard pages and partials for home, appointments, calendar, patients, services, settings-related pages, and reusable rows/forms/modals.
- Widget and public booking templates, including slot buttons, booking success/error states, and the floating widget shell.

Raw Stone-Sage or legacy teal/sage utilities are removed from all templates touched by this migration. Tailwind utilities remain allowed for layout, spacing, grids, and responsive behavior.

## Public And Brand Surfaces

Stripe's gradient mesh is used selectively where it helps the product feel Stripe-based:

- Public booking/widget header and confirmation surfaces.
- Auth or onboarding surfaces included in the implementation pass.
- Empty states or feature-like dashboard panels where visual branding is useful.

Operational dashboard screens must not become marketing pages. The dashboard retains table-first density and appointment-first workflows while using Stripe tokens and component geometry.

## Data Flow And Behavior

This migration is presentation-only.

It must not change appointment creation, guest booking, patient phone matching, slot generation, double-booking prevention, tenant scoping, permissions, dashboard routes, HTMX targets, form actions, or widget chat behavior.

HTMX and Alpine.js behavior continues to work with the same DOM IDs, targets, event listeners, and modal state unless a template change explicitly requires an equivalent renamed hook.

## Error Handling And Accessibility

The migration must preserve or improve accessibility:

- Focus states must be visible and indigo-based.
- Text contrast must meet WCAG AA on light, dark, and gradient surfaces.
- Disabled inputs and buttons must remain readable.
- Error states must remain visually distinct from primary indigo CTAs.
- Toasts, modal focus behavior, and HTMX loading states must remain accessible.

## Testing And Verification

Verification includes:

- `python manage.py check`
- Relevant Django/pytest tests covering design-system expectations and template behavior.
- Existing dashboard/widget tests that exercise HTMX partials and booking flows.
- Manual or screenshot-based review of dashboard, appointments, calendar, patients, services, widget booking, widget slot selection, and success/error states.

Design-system tests that currently assert Stone-Sage tokens must be updated to assert Stripe tokens and patterns instead.

## Non-Goals

- Do not introduce React, Next.js, Supabase, Drizzle, or a separate frontend.
- Do not add online payments or Stripe payment functionality. This is a visual design-system migration only.
- Do not rewrite product flows or appointment logic.
- Do not add a new npm build pipeline unless it becomes strictly necessary for the Stripe design reference. The current evidence shows it is not necessary.
