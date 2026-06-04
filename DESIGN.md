---
version: alpha
name: Neon-Aqua-Clinical
description: A cool clinical SaaS design language inspired by illuminated cyan setup imagery. The system pairs white and ice-cyan surfaces with deep teal ink, electric aqua CTAs, subtle glow mesh accents, compact pill controls, dense operational tables, and Inter typography with light display weights and tabular numerics.

colors:
  primary: "#06b6d4"
  primary-deep: "#0891b2"
  primary-press: "#0e7490"
  primary-soft: "#ecfeff"
  primary-bg-subdued-hover: "#cffafe"
  brand-dark-900: "#052f3a"
  ink: "#083344"
  ink-secondary: "#164e63"
  ink-mute: "#527486"
  ink-mute-2: "#6b8fa0"
  on-primary: "#ffffff"
  canvas: "#ffffff"
  canvas-soft: "#f0fdff"
  canvas-cream: "#e0fbff"
  hairline: "#d5f3f8"
  hairline-input: "#8ed8e8"
  ruby: "#ea2261"
  magenta: "#22d3ee"
  lemon: "#0f766e"
  shadow-blue: "#083344"

typography:
  display-xxl:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: 56px
    fontWeight: 300
    lineHeight: 1.03
    letterSpacing: -1.4px
    fontFeature: ss01
  display-xl:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: 48px
    fontWeight: 300
    lineHeight: 1.15
    letterSpacing: -0.96px
    fontFeature: ss01
  display-lg:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: 32px
    fontWeight: 300
    lineHeight: 1.1
    letterSpacing: -0.64px
    fontFeature: ss01
  display-md:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: 26px
    fontWeight: 300
    lineHeight: 1.12
    letterSpacing: -0.26px
    fontFeature: ss01
  heading-lg:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: 22px
    fontWeight: 300
    lineHeight: 1.1
    letterSpacing: -0.22px
    fontFeature: ss01
  heading-md:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: 20px
    fontWeight: 300
    lineHeight: 1.4
    letterSpacing: -0.2px
    fontFeature: ss01
  heading-sm:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: 18px
    fontWeight: 300
    lineHeight: 1.4
    letterSpacing: 0
    fontFeature: ss01
  body-lg:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: 16px
    fontWeight: 300
    lineHeight: 1.4
    letterSpacing: 0
    fontFeature: ss01
  body-md:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: 15px
    fontWeight: 300
    lineHeight: 1.4
    letterSpacing: 0
    fontFeature: ss01
  body-tabular:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: 14px
    fontWeight: 300
    lineHeight: 1.4
    letterSpacing: -0.42px
    fontFeature: tnum
  button-md:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.0
    letterSpacing: 0
    fontFeature: ss01
  button-sm:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.0
    letterSpacing: 0
    fontFeature: ss01
  caption:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: -0.39px
    fontFeature: tnum
  micro:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: 11px
    fontWeight: 300
    lineHeight: 1.4
    letterSpacing: 0
    fontFeature: ss01
  micro-cap:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: 10px
    fontWeight: 400
    lineHeight: 1.15
    letterSpacing: 0.1px
    fontFeature: ss01

rounded:
  xs: 4px
  sm: 6px
  md: 8px
  lg: 12px
  xl: 16px
  pill: 9999px

spacing:
  xxs: 2px
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  xxl: 32px
  huge: 64px

components:
  button-primary-pill:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.button-md}"
    rounded: "{rounded.pill}"
    padding: 8px 16px
  button-primary-pill-pressed:
    backgroundColor: "{colors.primary-press}"
    textColor: "{colors.on-primary}"
    typography: "{typography.button-md}"
    rounded: "{rounded.pill}"
    padding: 8px 16px
  button-secondary:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.primary}"
    typography: "{typography.button-md}"
    rounded: "{rounded.pill}"
    padding: 8px 16px
  button-on-dark:
    backgroundColor: "{colors.brand-dark-900}"
    textColor: "{colors.on-primary}"
    typography: "{typography.button-md}"
    rounded: "{rounded.pill}"
    padding: 8px 16px
  text-input:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.body-md}"
    rounded: "{rounded.sm}"
    padding: 8px 12px
  text-input-focused:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.body-md}"
    rounded: "{rounded.sm}"
    padding: 8px 12px
  card-feature-light:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.body-md}"
    rounded: "{rounded.lg}"
    padding: 32px
  card-dashboard:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.body-tabular}"
    rounded: "{rounded.lg}"
    padding: 24px
  pill-tag-soft:
    backgroundColor: "{colors.primary-bg-subdued-hover}"
    textColor: "{colors.primary-press}"
    typography: "{typography.micro-cap}"
    rounded: "{rounded.pill}"
    padding: 4px 8px
---

## Overview

KliniAssist uses the **Neon Aqua Clinical** system. It should feel cool, clean, and modern: white and ice-cyan surfaces, deep teal text, electric aqua calls to action, and subtle cyan glow accents inspired by illuminated desk/setup imagery. The result should be bright and distinctive without turning operational clinic screens into a gaming interface.

The design is implemented through Django templates, Tailwind utility classes, and the canonical `cf-*` CSS layer in `static/css/kliniassist.css`. Prefer existing component classes before adding new utilities.

## Key Characteristics

- Electric aqua is the primary action color. Use `{colors.primary}` for filled buttons, active states, focus states, selected slots, and high-emphasis links.
- Deep teal provides structure. Use `{colors.ink}` for default text and `{colors.brand-dark-900}` for the dashboard sidebar shell.
- Ice-cyan surfaces create the glow. Use `{colors.canvas-soft}`, `{colors.primary-soft}`, and `{colors.primary-bg-subdued-hover}` for panels, selected states, empty states, and public/widget accents.
- Glow is selective. Use cyan radial gradients on auth, booking, widget, and confirmation surfaces where contrast stays readable.
- Dashboard screens stay operational. Keep them dense, table-first, appointment-first, and optimized for staff workflows.

## Colors

### Brand & Accent

- **Aqua** (`{colors.primary}` - `#06b6d4`): Primary CTA, selected state, widget default accent, active navigation, focus borders.
- **Aqua Deep** (`{colors.primary-deep}` - `#0891b2`): Hover state, info text, chart/event border where a stronger edge is needed.
- **Aqua Press** (`{colors.primary-press}` - `#0e7490`): Pressed state, strong labels on aqua-soft backgrounds.
- **Aqua Soft** (`{colors.primary-soft}` - `#ecfeff`): Selected row backgrounds, slot hover, confirmed appointments, soft icon wells.
- **Aqua Subdued** (`{colors.primary-bg-subdued-hover}` - `#cffafe`): Stronger soft hover background.
- **Deep Teal Shell** (`{colors.brand-dark-900}` - `#052f3a`): Sidebar and dark operational chrome.
- **Ruby** (`{colors.ruby}` - `#ea2261`): Destructive/error accent only.

### Surface

- **Canvas** (`{colors.canvas}` - `#ffffff`): Default card and page surface.
- **Canvas Soft** (`{colors.canvas-soft}` - `#f0fdff`): Main page wash and low-emphasis panels.
- **Glow Interlude** (`{colors.canvas-cream}` - `#e0fbff`): Aqua-tinted feature/confirmation band.
- **Hairline** (`{colors.hairline}` - `#d5f3f8`): Card, table, dropdown, and modal borders.
- **Input Hairline** (`{colors.hairline-input}` - `#8ed8e8`): Form fields and select controls.

### Text

- **Ink** (`{colors.ink}` - `#083344`): Default body text, headings, table content.
- **Ink Secondary** (`{colors.ink-secondary}` - `#164e63`): Secondary headings and strong helper content.
- **Muted** (`{colors.ink-mute}` - `#527486`): Captions, labels, helper text.
- **Faint** (`{colors.ink-mute-2}` - `#6b8fa0`): Low-emphasis metadata and placeholders.
- **On Primary** (`{colors.on-primary}` - `#ffffff`): Text on aqua/dark fills.

### Semantic Status

Status colors must remain semantically distinct:

- Pending/booked: warm amber/cream.
- Confirmed/info: aqua/ice-cyan.
- Completed: green/teal.
- Cancelled/error: ruby/red.
- No-show/inactive: neutral gray-blue.

## Typography

Use Inter from Google Fonts. Display and page-title roles use weight 300 with tight negative tracking. Operational data uses tabular numerics for times, durations, counts, prices, and KPI values.

## Layout

- Preserve the left dashboard sidebar and topbar.
- Preserve compact KPI cards, operational tables, rounded modals, dense forms, and dashboard-first information hierarchy.
- Public booking, widget, auth, and confirmation surfaces may use glow mesh accents.
- Do not introduce React, Next.js, or a separate frontend.

## Components

### Buttons

Primary buttons use `{colors.primary}` with white text, pill geometry, and compact `8px 16px` padding. Hover uses `{colors.primary-deep}`. Pressed state uses `{colors.primary-press}`.

Secondary buttons stay quiet: white background, aqua text/border, and aqua-soft hover. Destructive actions use the ruby danger tokens, not aqua.

### Cards & Tables

Cards use white surfaces, `#d5f3f8` borders, compact radius, and subtle teal shadows. Tables remain high-density and readable. Avoid heavy glow inside operational tables.

### Inputs & Forms

Inputs use white backgrounds, teal ink, aqua input borders, and aqua focus rings. Disabled states must remain readable and cannot rely on opacity alone.

### Sidebar & Navigation

The dashboard sidebar uses deep teal shell color with white text. Active navigation uses subtle translucent fill and an aqua inset accent.

### Widget

The default widget accent is `{colors.primary}` (`#06b6d4`). Clinics may still customize `widget_accent_color`; unsafe values must fall back to the default aqua.

### Glow Mesh

Glow mesh backgrounds layer white, ice-cyan, electric aqua, and deep teal radial gradients. Use them sparingly behind public or confirmation surfaces, never behind dense data tables.

## Do's And Don'ts

### Do

- Use `DESIGN.md` and `static/css/kliniassist.css` as the color source of truth.
- Keep all text, controls, dropdowns, modals, badges, and disabled states WCAG AA readable.
- Keep appointment statuses visually distinct.
- Prefer `cf-*` classes and CSS custom properties over raw Tailwind color classes.
- Use aqua glow as atmosphere, not as decoration on every element.

### Don't

- Do not use old indigo/purple theme tokens for new UI.
- Do not collapse all statuses into aqua.
- Do not turn operational dashboard pages into marketing pages.
- Do not add patient portal, medical records, prescriptions, inventory, payments, marketplace booking, or real AI automation as part of visual work.
- Do not introduce a separate frontend stack.

## Responsive Behavior

- Dashboard tables may scroll horizontally on small screens.
- Forms and buttons maintain at least 40px touch targets.
- Widget layout remains constrained to the floating widget dimensions.
- Glow mesh should remain subtle on mobile so content contrast is not reduced.

## Iteration Guide

1. Start with CSS variables in `static/css/kliniassist.css`.
2. Prefer reusable `cf-*` classes.
3. Update tests when intentional design tokens change.
4. Run targeted design-system tests after theme edits.
5. Verify dashboard, widget, auth, and email surfaces remain readable.
