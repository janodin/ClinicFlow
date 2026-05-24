---
version: alpha
name: ClinicFlow
description: Appointment-first clinic management SaaS design system for Django templates, Tailwind CSS, HTMX, Alpine.js, FullCalendar, and embeddable guest booking.
colors:
  background: "#EEF5F8"
  background-strong: "#F4F9FB"
  surface: "#FFFFFF"
  surface-muted: "#E8F1F5"
  surface-tint: "#E4F3EC"
  line: "#D5E3EB"
  line-soft: "#E2EEF4"
  ink: "#18232C"
  muted: "#5F6870"
  faint: "#8A8378"
  primary: "#0F6B55"
  primary-strong: "#0A4036"
  primary-soft: "#E4F3EC"
  blue: "#276A8F"
  danger: "#B94444"
  amber: "#9B6B21"
  focus: "#CFE5DD"
  widget-default-accent: "#0891B2"
  status-pending-bg: "#FFF3D9"
  status-pending-text: "#8A5A10"
  status-confirmed-bg: "#E2F2FF"
  status-confirmed-text: "#245D82"
  status-completed-bg: "#E7F3EE"
  status-completed-text: "#0F6B55"
  status-cancelled-bg: "#FBE5E2"
  status-cancelled-text: "#A73F3F"
  status-no-show-bg: "#ECE8E1"
  status-no-show-text: "#5F6870"
  dark-background: "#0F1720"
  dark-background-strong: "#0A1017"
  dark-surface: "#151D27"
  dark-surface-muted: "#1C2631"
  dark-line: "#2A3644"
  dark-ink: "#F8F3EC"
  dark-muted: "#C5BEB4"
  dark-primary: "#76D2AA"
  dark-primary-strong: "#A8EBCC"
typography:
  page-title:
    fontFamily: Cormorant Garamond
    fontSize: 40px
    fontWeight: 700
    lineHeight: 0.98
    letterSpacing: 0
  section-title:
    fontFamily: Manrope
    fontSize: 20px
    fontWeight: 850
    lineHeight: 1.2
    letterSpacing: 0
  body:
    fontFamily: Manrope
    fontSize: 16px
    fontWeight: 500
    lineHeight: 1.55
    letterSpacing: 0
  body-sm:
    fontFamily: Manrope
    fontSize: 14px
    fontWeight: 500
    lineHeight: 1.55
    letterSpacing: 0
  label:
    fontFamily: Manrope
    fontSize: 12px
    fontWeight: 800
    lineHeight: 1.2
    letterSpacing: 0.04em
  label-caps:
    fontFamily: Manrope
    fontSize: 12px
    fontWeight: 850
    lineHeight: 1
    letterSpacing: 0.08em
  kpi-value:
    fontFamily: IBM Plex Mono
    fontSize: 36px
    fontWeight: 600
    lineHeight: 1
    letterSpacing: 0
  mono:
    fontFamily: IBM Plex Mono
    fontSize: 14px
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: 0
rounded:
  sm: 9px
  md: 14px
  lg: 18px
  full: 9999px
spacing:
  xs: 4px
  sm: 8px
  md: 12px
  base: 16px
  lg: 20px
  xl: 24px
  page-x-mobile: 24px
  page-x-desktop: 48px
  sidebar-width: 272px
  widget-width: 420px
  widget-height: 650px
  table-mobile-min-width: 720px
components:
  button-primary:
    backgroundColor: "{colors.primary-strong}"
    textColor: "{colors.surface}"
    rounded: "{rounded.md}"
    padding: "10px 16px"
    height: "41px"
    typography: "{typography.body-sm}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.muted}"
    borderColor: "{colors.line}"
    rounded: "{rounded.md}"
    padding: "10px 16px"
    height: "41px"
    typography: "{typography.body-sm}"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    borderColor: "{colors.line}"
    rounded: "{rounded.lg}"
    padding: "{spacing.lg}"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    borderColor: "{colors.line}"
    rounded: "{rounded.md}"
    padding: "12px 15px"
    height: "44px"
  table:
    backgroundColor: "{colors.surface}"
    borderColor: "{colors.line}"
    rounded: "{rounded.lg}"
    typography: "{typography.body-sm}"
  badge:
    rounded: "{rounded.full}"
    padding: "5px 11px"
    typography: "{typography.label}"
  modal:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "{spacing.xl}"
  widget-shell:
    backgroundColor: "{colors.surface}"
    borderColor: "{colors.line}"
    rounded: "{rounded.lg}"
    width: "{spacing.widget-width}"
    height: "{spacing.widget-height}"
---

# ClinicFlow Design System

## Overview

ClinicFlow is a focused clinic operations product, not a marketplace, patient portal, or medical records system. The interface should feel calm, trustworthy, fast to scan, and clearly appointment-first. Staff users need dense operational screens for managing appointments, patients, services, schedules, and clinic settings. Patients book as guests through a focused public booking form or floating embeddable widget.

The visual direction is clean teal and white SaaS with a restrained clinical warmth. Use structured tables, compact KPI cards, clear status badges, rounded cards/modals, and a persistent left sidebar for authenticated workflows. Public booking should feel lighter and more guided, but it must share the same design vocabulary.

Primary implementation targets are Django templates, Tailwind utility classes, shared CSS variables in `static/css/clinicflow.css`, HTMX for server-rendered interactions, Alpine.js for small UI state, Lucide icons, and FullCalendar for the calendar screen. The primary staff IA is Dashboard, Calendar, Appointments, Patients, Services, Assistant/Widget, Settings, and Billing.

## Colors

The palette is rooted in soft clinical surfaces, deep green-teal actions, and muted slate text.

- **Primary (#0F6B55):** Main brand accent for active states, status highlights, links, progress, and key affordances.
- **Primary Strong (#0A4036):** Primary CTA background, sidebar logo tile, strong emphasis, and success toasts.
- **Primary Soft (#E4F3EC):** Selected navigation, active panels, low-pressure highlights, and icon containers.
- **Background (#EEF5F8) and Background Strong (#F4F9FB):** App-level gradient foundation. Keep dashboards light and quiet.
- **Surface (#FFFFFF):** Main card, table, input, modal, menu, search, and widget surface.
- **Ink (#18232C):** Main text and headings.
- **Muted (#5F6870):** Secondary body copy, metadata, table cells, and helper text.
- **Line (#D5E3EB):** Borders and table wrappers. Prefer subtle borders over heavy shadows.
- **Status Colors:** Pending uses amber, confirmed uses blue, completed uses teal-green, cancelled uses rose, and no-show uses muted grey.

Use clinic-specific accent colors only where the clinic owns the surface, especially the embeddable widget header, widget CTAs, and public booking confirmation reference card. Do not let per-clinic accent colors rewrite the dashboard system globally.

## Typography

Use **Manrope** as the primary interface family. It keeps dense clinic data readable while still feeling polished. Use **Cormorant Garamond** only for page-level titles via `.ui-page-title`; it gives major screens a recognizable editorial voice without making tables decorative. Use **IBM Plex Mono** for KPI values, reference codes, and compact technical identifiers.

Typography should remain operational and compact:

- Page titles: large, elegant, and limited to one per screen.
- Section titles: bold Manrope, usually 18-24px.
- Body text: 14-16px Manrope with enough line height for forms and table metadata.
- Labels: uppercase or near-uppercase, bold, muted, and compact.
- KPI values: mono, large, and numerically stable.

Do not scale typography with viewport width. Preserve `letter-spacing: 0` for normal text and reserve tracking for labels only.

## Layout

Authenticated dashboard screens use a fixed left sidebar of 272px on desktop, a topbar, and a responsive content area with generous but efficient padding. Mobile uses a hidden sidebar, topbar menu, and bottom navigation. Operational screens should be table-first, with filters and actions above the main data region.

Common layout patterns:

- `.cf-page` for vertical page rhythm with consistent gaps.
- `.cf-page-header` for title, metadata, and primary action alignment.
- `.cf-toolbar` for filters, segmented status controls, and compact form controls.
- `.cf-table-wrap` for the main operational table container.
- Responsive grids for KPI cards, services, and secondary panels.
- Public booking uses a two-column layout on desktop: clinic context on the left and the booking card on the right.
- Widget mode is a fixed, self-contained 420px by 650px chat/booking panel.
- Scheduling screens should express hierarchy clearly: clinic business hours, breaks, blocked times, unavailable dates, slot preview, and double-booking prevention.

Use horizontal overflow for dense tables on mobile instead of compressing columns into unreadable cards unless a screen is explicitly designed as a card workflow. Existing mobile tables use a 720px minimum width, while booking slot grids move from three columns to two columns below 640px.

## Elevation & Depth

Depth is soft and utilitarian. The current system uses subtle card shadows and borders:

- Card shadow: `0 18px 46px rgba(24, 35, 44, .08)`.
- Raised shadow: `0 28px 80px rgba(24, 35, 44, .16)`.
- Dark mode raises shadow opacity but still avoids harsh contrast.

Use borders and tonal surface shifts as the primary hierarchy tools. Reserve raised shadows for cards, menus, dropdowns, modals, toasts, and the floating widget. Do not create decorative glass panels, large marketing hero effects, or ornamental backgrounds beyond the existing soft page gradient.

## Shapes

The shape language is softly rounded and consistent:

- Small controls: about 9px.
- Buttons, inputs, nav links, tabs, and compact containers: about 14px.
- Cards, modals, table wrappers, widget shells, and large panels: about 18px.
- Avatars, pills, status badges, and presence dots: full radius.

Avoid mixing sharp corners with rounded ClinicFlow components. Use rounded cards/modals as product surfaces, but keep page sections unframed unless they are a real container or repeated item.

## Components

**Buttons:** Use `.cf-btn` as the base. Primary buttons use `primary-strong` with white text and are for the main action on a screen or modal. Secondary buttons are white/surface with border and muted text. Danger actions use the cancelled status palette. Include Lucide icons when the action benefits from immediate recognition.

**Inputs and Forms:** Inputs, selects, and textareas are full-width by default with rounded borders, surface background, and a teal focus ring. Labels are compact, bold, muted, and usually uppercase. Keep form layouts to one column on mobile and two columns where desktop density helps.

**Tables:** Tables are the default for operational resources. Use uppercase headers, soft row dividers, hover tinting, and action buttons aligned at the row end. Table containers should use `.cf-table-wrap`.

**Status Badges:** Use `.cf-badge` plus status classes. Keep status language short and consistent with appointment model states: Booked, Confirmed, Cancelled, Completed, No Show. Payment states should remain visually secondary to appointment status.

**Navigation:** Sidebar nav uses Lucide icons, muted text, and active teal-soft background with a left inset accent. Keep sections grouped under short uppercase labels like Practice and Settings. Mobile bottom nav mirrors the main operational screens.

**Cards and KPIs:** KPI cards are compact, numeric, and scannable. Use mono values, small uppercase labels, and simple icon boxes. Repeated cards, such as service cards, should expose the few operational details needed for decisions.

**Modals:** Use `.cf-modal-backdrop` and `.cf-modal`. Modal content should be direct and form-oriented, with a clear title, close affordance, and full-width primary submit where appropriate.

**Public Booking:** Use a guided wizard with progress bars, one decision per step, and clear Back/Continue actions. Reinforce guest booking and no-login behavior. Keep service, date, slot, patient details, review, and confirmation visually distinct.

**Widget:** The widget is compact and clinic-branded. It can offer booking and FAQ/chat-like assistance, but it should remain deterministic and booking-oriented in V1. Header and key CTAs may use `clinic.widget_accent_color`; internal content should still respect ClinicFlow spacing, badges, inputs, and cards.

**Calendar:** FullCalendar should be contained in a soft card. Use status color legend and service filters. Event detail opens in a modal loaded by HTMX.

**Patients:** Patient records are pragmatic V1 CRM records, not accounts. Represent identity around name, phone, optional email, and clinic-local history. Duplicate detection and merge flows should feel careful and reversible.

**Services:** Services are clinic-scoped operational resources. Service cards can include duration, price visibility, active/archived state, and optional service color.

**Empty States:** Empty states should be helpful and calm: icon box, one concise heading, one sentence of guidance, and a single next action.

## Do's and Don'ts

- Do preserve clinic tenant boundaries in UI language and data surfaces.
- Do keep authenticated screens dense, table-first, and optimized for repeated staff use.
- Do use the shared `cf-*` and `ui-*` classes before inventing new styling.
- Do use HTMX for dynamic server-rendered updates and Alpine.js only for small local state.
- Do keep guest booking passwordless and focused on appointment completion.
- Do keep patient phone matching, slot validation, and double-booking prevention visible in flow decisions where relevant.
- Do use Lucide icons for navigation, actions, empty states, and compact affordances.
- Do keep status colors consistent across dashboard, calendar, booking, and widget surfaces.
- Do make mobile layouts usable with stable controls, safe bottom spacing, and horizontal table overflow where needed.
- Don't introduce React, Next.js, Supabase, Drizzle, or a separate frontend for V1 screens.
- Don't add patient portal, medical records, prescriptions, inventory, online payments, marketplace booking, or real AI/Messenger automation unless explicitly requested.
- Don't make marketing-style landing pages for operational workflows.
- Don't use purple gradients, decorative blobs, stock-like imagery, or oversized hero compositions.
- Don't create nested cards or put UI cards inside other UI cards.
- Don't leave unused template fragments, imports, URLs, or tests behind when changing UI features.
