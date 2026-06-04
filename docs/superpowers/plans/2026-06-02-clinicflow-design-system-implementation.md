# KliniAssist Design System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the approved Stone-Sage Clinical Ledger design system across KliniAssist while preserving appointment-first behavior, clinic scoping, guest booking, slot validation, and HTMX workflows.

**Architecture:** Implement from the shared foundation outward. First update `static/css/clinicflow.css`, then the authenticated app shell, shared partials, operational pages, public widget, auth/email screens, and finally add drift tests and cleanup. Implementation tasks should run sequentially because many phases touch shared CSS and templates.

**Tech Stack:** Django templates, Tailwind utility layout, `static/css/clinicflow.css`, HTMX, Alpine.js, FullCalendar, Lucide icons, pytest, Django test client.

---

## Operating Rules

- Read `DESIGN.md` before every task and treat it as the acceptance source.
- Do not dispatch parallel implementers. Use parallel agents only for read-only reviews or audits.
- Do not commit unless the user explicitly asks for commits. Use git diff/status for review checkpoints.
- Do not stage or modify unrelated files such as `db.sqlite3`, `.superpowers/`, or `deploy-vps.ps1`.
- Preserve guest booking, patient phone matching, appointment slot validation, double-booking prevention, and clinic scoping.
- Do not add patient portal, medical records, prescriptions, inventory, online payments, marketplace booking, or real AI automation.
- No model changes are expected. If a task unexpectedly requires model changes, stop and ask before proceeding.

## File Responsibility Map

- `DESIGN.md`: Approved design system source of truth. Already rewritten.
- `static/css/clinicflow.css`: Global tokens, base elements, reusable `cf-*` classes, temporary compatibility aliases.
- `templates/base.html`: Global static CSS/script loading and root document shell.
- `templates/dashboard/base.html`: Authenticated app shell, sidebar, topbar, search, toast container, mobile nav, HTMX behavior.
- `templates/dashboard/partials/*.html`: HTMX-swapped reusable operational UI for appointments, patients, services, FAQs, search, modals.
- `templates/dashboard/*.html`: Authenticated pages using the design system.
- `templates/widget/*.html`: Public guest booking and embeddable widget flow.
- `widget/views.py`: Widget booking, embed script, success/error context, source handling.
- `templates/accounts/*.html`: Auth screens.
- `templates/emails/*.html`: Inline-safe transactional email styling.
- `tests/test_design_system.py`: Drift and smoke tests for design-system adoption.

## Baseline Commands

Use these commands from the project root.

```powershell
.\env\Scripts\activate
python manage.py check
pytest -q
```

If any implementation task touches Django models, run this sequence before continuing:

```powershell
.\env\Scripts\activate
python manage.py makemigrations
python manage.py migrate
python manage.py check
pytest -q
```

---

### Task 1: CSS Foundation

**Files:**
- Modify: `static/css/clinicflow.css`
- Reference: `DESIGN.md`

**Goal:** Make the shared CSS foundation match Stone-Sage Clinical Ledger while preserving old aliases until templates are migrated.

- [ ] **Step 1: Inspect current token and alias state**

Run:

```powershell
.\env\Scripts\activate
rg "--cf-bg|--cf-brand|font-weight:\s*850|soft-card|ui-input|text-cyan|bg-cyan" static/css/clinicflow.css
```

Expected: output shows old teal tokens, `850` weights, and compatibility aliases that will be migrated or temporarily preserved.

- [ ] **Step 2: Replace root tokens with Stone-Sage variables**

Update `:root` in `static/css/clinicflow.css` to use the variables from `DESIGN.md` section `19. Implementation Rules`, including:

```css
:root {
  color-scheme: light;
  --cf-bg: #ebe7dd;
  --cf-bg-strong: #f8f6ef;
  --cf-surface: #ffffff;
  --cf-surface-warm: #fffcf6;
  --cf-surface-muted: #dedad0;
  --cf-surface-tint: #d8e3dc;
  --cf-line: #d7d2c6;
  --cf-line-soft: #e8e2d8;
  --cf-ink: #202521;
  --cf-muted: #625d55;
  --cf-faint: #746f66;
  --cf-brand: #365449;
  --cf-brand-strong: #243a33;
  --cf-brand-hover: #2e493f;
  --cf-brand-soft: #d8e3dc;
  --cf-info: #36586b;
  --cf-info-soft: #dbe7ee;
  --cf-warning: #6b4714;
  --cf-warning-soft: #f4dfad;
  --cf-danger: #7a2d28;
  --cf-danger-soft: #f2d6d1;
  --cf-focus: rgba(54, 84, 73, .24);
  --cf-blue: var(--cf-info);
  --cf-red: var(--cf-danger);
  --cf-amber: var(--cf-warning);
  --cf-shadow-card: 0 18px 46px rgba(32, 37, 33, .08);
  --cf-shadow-raised: 0 28px 80px rgba(32, 37, 33, .16);
  --cf-shadow-subtle: 0 8px 24px rgba(32, 37, 33, .06);
  --cf-radius-xs: 6px;
  --cf-radius-sm: 9px;
  --cf-radius: 14px;
  --cf-radius-md: 14px;
  --cf-radius-lg: 18px;
  --cf-radius-shell: 20px;
  --cf-sidebar-width: 272px;
  --cf-topbar-height: 64px;
  --cf-widget-width: 420px;
  --cf-widget-height: 650px;
  --cf-z-dropdown: 55;
  --cf-z-modal: 60;
  --cf-z-toast: 70;
  --cf-z-widget: 80;
}
```

- [ ] **Step 3: Normalize base page, typography, and font weights**

Update `body`, headings, labels, table headers, buttons, badges, and compatibility `.font-black` to use supported font weights. Replace all `font-weight: 850` with `800` and any unsupported `750` with `700` or `800` based on emphasis.

- [ ] **Step 4: Implement canonical controls**

Ensure CSS contains canonical definitions for:

```text
.cf-btn
.cf-btn-primary
.cf-btn-secondary
.cf-btn-ghost
.cf-btn-danger
.cf-btn-link
.cf-btn-sm
.cf-btn-lg
.cf-icon-btn
.cf-field
.cf-label
.cf-input
.cf-select
.cf-textarea
.cf-help
.cf-error
```

Use `DESIGN.md` sections `9. Component System`, `Buttons`, and `Forms and Fields` as exact specs.

- [ ] **Step 5: Implement dropdown readability rules**

Add explicit select and option rules:

```css
select option {
  background: #fff;
  color: var(--cf-ink);
}

select option:disabled {
  background: #fff;
  color: #6f695f;
}

select option:checked {
  background: var(--cf-brand-soft);
  color: var(--cf-brand-strong);
  font-weight: 700;
}
```

Also update `select[multiple]`, `.cf-menu-panel`, `.cf-search-panel`, `.cf-menu-row`, and `.cf-search-result` so hover, active, focus, selected, disabled, and danger rows are readable.

- [ ] **Step 6: Implement cards, tables, badges, modals, and toasts**

Ensure CSS defines:

```text
.cf-card
.cf-card-muted
.cf-kpi
.cf-table-wrap
.cf-table-header
.cf-table
.cf-row-actions
.cf-badge
.cf-status-pending
.cf-status-booked
.cf-status-confirmed
.cf-status-completed
.cf-status-cancelled
.cf-status-no-show
.cf-status-no_show
.cf-modal-backdrop
.cf-modal
.cf-modal-sm
.cf-modal-md
.cf-modal-lg
.cf-modal-xl
.cf-modal-header
.cf-modal-title
.cf-modal-description
.cf-modal-body
.cf-modal-footer
.cf-toast-container
.cf-toast
.cf-toast-success
.cf-toast-error
.cf-toast-warning
.cf-toast-info
.cf-toast-message
.cf-toast-close
```

- [ ] **Step 7: Preserve temporary aliases**

Keep `.ui-page-title`, `.ui-input`, `.ui-select`, `.ui-button`, `.soft-card`, and temporary Tailwind color overrides mapped to Stone-Sage values. Add a CSS comment that these are migration-only compatibility rules.

- [ ] **Step 8: Verify CSS foundation**

Run:

```powershell
.\env\Scripts\activate
python manage.py check
pytest -q
rg "font-weight:\s*850|font-weight:\s*750" static/css/clinicflow.css
rg "--cf-bg:\s*#eef5f8|--cf-brand:\s*#0f6b55|#0891b2" static/css/clinicflow.css
```

Expected: `manage.py check` and `pytest` pass. The two `rg` checks return no matches.

---

### Task 2: Dashboard Shell

**Files:**
- Modify: `templates/dashboard/base.html`
- Modify: `templates/dashboard/partials/nav_link.html`
- Modify: `templates/dashboard/partials/search_results.html`

**Goal:** Apply Stone-Sage shell layout to sidebar, topbar, account menu, search, toast container, and mobile navigation.

- [ ] **Step 1: Update navigation groups and labels**

Use these groups:

```text
Operations: Today, Calendar, Appointments, Patients
Practice: Services, Booking Widget, Settings
Account: Billing, Profile, Logout
```

Rename the dashboard link label from `Dashboard` to `Today`. Rename `Assistant` to `Booking Widget` unless a specific deterministic assistant settings page remains visible.

- [ ] **Step 2: Update shell classes and sizing**

Use `cf-sidebar`, `cf-topbar`, `cf-dashboard-main`, `cf-topbar-search`, `cf-menu-panel`, `cf-toast-container`, and Stone-Sage tokens. Keep sidebar width `272px` and topbar height `64px`.

- [ ] **Step 3: Add accessible labels**

Add `aria-label` to mobile menu button, sidebar close button, account button if icon-only, and toast dismiss buttons.

- [ ] **Step 4: Fix HTMX focus handling**

Update the `htmx:afterSwap` behavior so temporary `tabindex="-1"` is applied to a region or heading, focused, and removed on blur. Do not permanently remove buttons, links, or inputs from tab order.

- [ ] **Step 5: Verify shell**

Run:

```powershell
.\env\Scripts\activate
python manage.py check
pytest -q
```

Manual check: desktop sidebar, mobile drawer, bottom nav, account dropdown, search dropdown, and toast readability.

---

### Task 3: Shared HTMX Partials

**Files:**
- Modify: `templates/dashboard/partials/appointment_list.html`
- Modify: `templates/dashboard/partials/appointment_row.html`
- Modify: `templates/dashboard/partials/appointment_detail.html`
- Modify: `templates/dashboard/partials/appointment_form.html`
- Modify: `templates/dashboard/partials/add_patient_modal.html`
- Modify: `templates/dashboard/partials/patient_list.html`
- Modify: `templates/dashboard/partials/patient_row.html`
- Modify: `templates/dashboard/partials/patient_detail.html`
- Modify: `templates/dashboard/partials/patient_detail_content.html`
- Modify: `templates/dashboard/partials/patient_edit_modal_form.html`
- Modify: `templates/dashboard/partials/duplicate_list.html`
- Modify: `templates/dashboard/partials/merge_confirm.html`
- Modify: `templates/dashboard/partials/merge_success.html`
- Modify: `templates/dashboard/partials/service_list.html`
- Modify: `templates/dashboard/partials/service_row.html`
- Modify: `templates/dashboard/partials/service_form.html`
- Modify: `templates/dashboard/partials/faq_row.html`

**Goal:** Normalize reusable HTMX surfaces without changing URLs, view behavior, or target IDs.

- [ ] **Step 1: Normalize table partials**

Use this structure for operational tables:

```html
<section class="cf-table-wrap">
  <div class="cf-table-header">
    <div>
      <h2 class="cf-section-title">...</h2>
      <p class="cf-muted">...</p>
    </div>
  </div>
  <div class="overflow-x-auto">
    <table class="cf-table">
      ...
    </table>
  </div>
</section>
```

- [ ] **Step 2: Normalize modal partials**

Use `.cf-modal-backdrop`, `.cf-modal`, `.cf-modal-header`, `.cf-modal-body`, `.cf-modal-footer`, and `role="dialog" aria-modal="true" aria-labelledby="..."` on the modal container.

- [ ] **Step 3: Normalize fields and errors**

Replace raw input/select/textarea utility classes with `.cf-field`, `.cf-label`, `.cf-input`, `.cf-select`, `.cf-textarea`, `.cf-help`, and `.cf-error`.

- [ ] **Step 4: Reduce appointment row action noise**

Keep one primary visible row action where possible. Move edit, reschedule, cancel, and notes emphasis into the detail modal where it already belongs.

- [ ] **Step 5: Verify partial behavior**

Run:

```powershell
.\env\Scripts\activate
python manage.py check
pytest tests/test_domain.py -q
pytest -q
```

Manual check: HTMX appointment, patient, service, FAQ, and merge partials still swap into the expected targets.

---

### Task 4: Today Dashboard

**Files:**
- Modify: `templates/dashboard/home.html`
- Modify if needed: `dashboard/views.py`

**Goal:** Recompose the dashboard as an appointment-first front-desk workspace.

- [ ] **Step 1: Reframe page header**

Use `Today at {{ clinic.name }}` or `Today at a glance`. Keep date/timezone metadata visible.

- [ ] **Step 2: Reorder metrics**

Primary KPI strip should prioritize:

```text
Today
Pending
Open slots or next available slot CTA
No-shows
```

Keep all-time patients, completed, cancelled, and upcoming as secondary owner-value metrics.

- [ ] **Step 3: Make today schedule time-first**

Use columns in this order for the dashboard schedule: time, patient, service, source/payment, status.

- [ ] **Step 4: Replace generic copy and icons**

Remove rocket/hype empty state language. Rename `Smart booking active` to `Booking widget active`.

- [ ] **Step 5: Verify dashboard**

Run:

```powershell
.\env\Scripts\activate
python manage.py check
pytest tests/test_flows.py -q
pytest -q
```

Manual check: empty and non-empty dashboard states at desktop and mobile widths.

---

### Task 5: Appointments and Calendar

**Files:**
- Modify: `templates/dashboard/appointments.html`
- Modify: `templates/dashboard/calendar.html`
- Modify if needed: `dashboard/views.py`

**Goal:** Apply the design system to the two highest-frequency operational screens.

- [ ] **Step 1: Redesign appointments filters**

Use `.cf-toolbar`, `.cf-field`, `.cf-label`, `.cf-input`, and `.cf-select`. Preserve filter values when status tabs are clicked.

- [ ] **Step 2: Normalize appointment modals**

Use singular titles such as `Cancel appointment` and `Reschedule appointment`. Keep existing validation and HTMX targets.

- [ ] **Step 3: Apply calendar Stone-Sage shell**

Wrap FullCalendar in a Stone-Sage card. Use a single toolbar for service filter, view controls, and legend.

- [ ] **Step 4: Update event colors**

If event colors are provided from `dashboard/views.py`, map appointment statuses to the Stone-Sage status colors in `DESIGN.md`.

- [ ] **Step 5: Verify appointments and calendar**

Run:

```powershell
.\env\Scripts\activate
python manage.py check
pytest tests/test_domain.py -q
pytest -q
```

Manual check: appointment filters, create/edit/cancel/reschedule, calendar service filter, event detail modal, drag success/error toast.

---

### Task 6: Patients, Services, and Settings

**Files:**
- Modify: `templates/dashboard/patients.html`
- Modify: `templates/dashboard/services.html`
- Modify: `templates/dashboard/settings.html`
- Modify: `templates/dashboard/business_hours.html`
- Modify: `templates/dashboard/unavailable_dates.html`
- Modify: `templates/dashboard/slot_preview.html`

**Goal:** Bring secondary operational pages into the same design language and responsive behavior.

- [ ] **Step 1: Redesign patients page**

Use table-first patient identity hierarchy: name, phone, optional email, appointment count, last visit. Keep add/edit/detail/merge workflows clinic-scoped.

- [ ] **Step 2: Redesign services page**

Use compact cards or table. Service color must be a small dot/stripe only, not a full-card theme.

- [ ] **Step 3: Redesign settings page**

Use tabs and grouped forms. Explain cause/effect for business hours, unavailable dates, and slot preview.

- [ ] **Step 4: Migrate legacy scheduling pages**

If standalone `business_hours.html`, `unavailable_dates.html`, or `slot_preview.html` remain reachable, migrate them to `cf-*` classes or remove/deprecate them only after confirming no route needs them.

- [ ] **Step 5: Verify patient, service, and settings flows**

Run:

```powershell
.\env\Scripts\activate
python manage.py check
pytest tests/test_domain.py -q
pytest -q
```

Manual check: patient search/detail/edit/merge, service create/edit/archive/restore/toggle, settings tabs, business hours save, unavailable date add/delete, slot preview.

---

### Task 7: Public Booking and Widget

**Files:**
- Modify: `templates/widget/widget.html`
- Modify: `templates/widget/partials/slots.html`
- Modify: `templates/widget/partials/booking_success.html`
- Modify: `templates/widget/partials/booking_error.html`
- Modify: `templates/widget/booking_success.html`
- Modify if needed: `widget/views.py`

**Goal:** Make the patient-facing flow trust-focused, mobile-safe, and status-accurate while preserving guest booking safeguards.

- [ ] **Step 1: Convert booking to five-step flow**

Use labeled steps:

```text
Service
Date and time
Your details
Review
Confirmation
```

- [ ] **Step 2: Add trust copy**

Include:

```text
No account needed.
Your information is shared only with {{ clinic.name }} for this appointment.
We use your phone number to match your booking and send updates.
```

- [ ] **Step 3: Add review state**

Review card must show clinic, service, duration, date, time, patient name, phone, optional email, reason if enabled, timezone, and approval expectation.

- [ ] **Step 4: Fix confirmation copy**

Use `Booking confirmed` only for confirmed appointments. Use `Appointment request received` for manual approval or pending appointments.

- [ ] **Step 5: Fix embed sizing**

Update `embed_js` output in `widget/views.py` if needed so desktop is `420px x 650px` and mobile uses viewport-safe sizing.

- [ ] **Step 6: Verify widget**

Run:

```powershell
.\env\Scripts\activate
python manage.py check
pytest -q
```

Manual check: widget service/date/details/review/confirmation, mobile viewport, slot conflict, error state, embed launcher, no unsupported AI claims.

---

### Task 8: Auth, Emails, Billing, and Profile

**Files:**
- Modify: `templates/accounts/login.html`
- Modify: `templates/accounts/signup.html`
- Modify: `templates/emails/base_email.html`
- Modify: `templates/emails/confirmation_patient.html`
- Modify: `templates/emails/reminder_patient.html`
- Modify: `templates/emails/new_booking_staff.html`
- Modify: `templates/dashboard/billing.html`
- Modify: `templates/dashboard/profile.html`

**Goal:** Finish remaining visible surfaces and remove unsupported client-facing claims.

- [ ] **Step 1: Redesign auth pages**

Use Stone-Sage brand panel, centered card, readable form controls, and minimal copy.

- [ ] **Step 2: Update emails**

Use inline-safe Stone-Sage colors from `DESIGN.md` section `18. Auth and Emails`.

- [ ] **Step 3: Update billing**

Remove unsupported online-payment, marketplace, advanced automation, or real-AI implications. Use plan/status badges from the design system.

- [ ] **Step 4: Update profile**

Use `.cf-page`, `.cf-card`, `.cf-field`, and disabled `.cf-input` styling. Keep profile read-only unless edit behavior exists.

- [ ] **Step 5: Verify remaining surfaces**

Run:

```powershell
.\env\Scripts\activate
python manage.py check
pytest tests/test_flows.py -q
pytest -q
```

---

### Task 9: Design Drift Tests and Cleanup

**Files:**
- Create: `tests/test_design_system.py`
- Modify: `static/css/clinicflow.css`
- Modify templates only where drift remains
- Modify: `.gitignore` if the user approves ignoring `.superpowers/`

**Goal:** Add guardrails so the old teal/slate/cyan style does not creep back into dashboard templates.

- [ ] **Step 1: Add design drift tests**

Create `tests/test_design_system.py` with this test module:

```python
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_css_uses_stone_sage_tokens():
    css = (PROJECT_ROOT / "static" / "css" / "clinicflow.css").read_text(encoding="utf-8")

    assert "--cf-bg: #ebe7dd" in css
    assert "--cf-brand: #365449" in css
    assert "--cf-brand-strong: #243a33" in css
    assert "--cf-danger: #7a2d28" in css
    assert "--cf-warning: #6b4714" in css
    assert "font-weight: 850" not in css


def test_dashboard_templates_do_not_use_old_color_utilities():
    banned = (
        "text-slate-",
        "bg-cyan-",
        "border-slate-",
        "bg-emerald-",
        "text-cyan-",
        "font-[850]",
    )
    dashboard_templates = PROJECT_ROOT / "templates" / "dashboard"
    hits = []

    for path in dashboard_templates.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        for pattern in banned:
            if pattern in text:
                hits.append(f"{path.relative_to(PROJECT_ROOT)} contains {pattern}")

    assert hits == []
```

- [ ] **Step 2: Add smoke tests for primary pages if needed**

If existing tests do not cover page rendering, extend `tests/test_flows.py` or create a focused smoke test file. Test authenticated dashboard pages render for a clinic member and public widget renders for a clinic slug.

- [ ] **Step 3: Remove compatibility CSS only when safe**

Run:

```powershell
rg "ui-page-title|ui-input|ui-select|soft-card|font-black|text-slate|bg-cyan|border-slate|text-cyan|bg-emerald" templates static/css/clinicflow.css
```

Remove compatibility aliases only if no templates need them. Keep aliases if public widget, auth, or email migration still depends on them.

- [ ] **Step 4: Final verification**

Run:

```powershell
.\env\Scripts\activate
python manage.py check
pytest -q
rg "font-weight:\s*850|font-\[850\]" static/css templates
rg "text-slate-|bg-cyan-|border-slate-|bg-emerald-|text-cyan-" templates/dashboard
```

Expected: Django check and pytest pass. The final two `rg` commands return no matches.

---

## Manual QA Checklist

Check these viewport sizes:

```text
375x667
390x844
768x1024
1366x768
1440x900
```

Check these screens:

- Login and signup.
- Today dashboard.
- Appointments table and appointment modals.
- Calendar and event detail modal.
- Patients table, detail, edit, duplicate merge.
- Services list and service form.
- Settings tabs, business hours, unavailable dates, slot preview.
- Booking widget settings and FAQ flows.
- Public widget booking flow.
- Booking success and error states.
- Billing and profile.

Check these behaviors:

- Sidebar desktop and mobile drawer.
- Bottom mobile nav does not cover controls.
- Tables scroll horizontally only inside wrappers.
- Native select dropdown options are readable.
- Custom dropdown/search/menu rows are readable.
- Modals fit mobile height and are keyboard accessible.
- Toasts are readable and dismissible.
- Focus ring is visible on all interactive controls.
- Widget fits mobile viewport.
- No unsupported AI/payment/portal/marketplace copy appears.

## Subagent Execution Flow

For each task:

1. Dispatch one implementer subagent with the task text and relevant files.
2. Run task-specific commands.
3. Dispatch a spec-compliance reviewer against `DESIGN.md`.
4. Dispatch a code-quality/accessibility reviewer.
5. Fix review findings before moving to the next task.

Use this order:

```text
Task 1 CSS Foundation
Task 2 Dashboard Shell
Task 3 Shared HTMX Partials
Task 4 Today Dashboard
Task 5 Appointments and Calendar
Task 6 Patients, Services, and Settings
Task 7 Public Booking and Widget
Task 8 Auth, Emails, Billing, and Profile
Task 9 Design Drift Tests and Cleanup
```

## Final Acceptance Criteria

- `python manage.py check` passes.
- `pytest -q` passes.
- The dashboard and widget visibly follow Stone-Sage Clinical Ledger.
- No unreadable dropdowns, menus, toasts, badges, disabled fields, or modals.
- Desktop, tablet, and mobile layouts are usable.
- Guest booking still works without login.
- Patient phone matching still works.
- Appointment slot validation and double-booking prevention remain intact.
- Clinic-owned data remains scoped to the active clinic or clinic group.
- No unsupported V1 features or claims are introduced.
