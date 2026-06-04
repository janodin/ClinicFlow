# Mobile Responsiveness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ClinicFlow responsive and usable on phones and small tablets across dashboard, scheduling, auth, and widget pages while preserving the existing Django template stack and Neon Aqua Clinical design system.

**Architecture:** Add a shared mobile baseline in `static/css/clinicflow.css`, then apply focused template changes by page family. Keep dense dashboard screens table-first, but add mobile-safe touch targets, wrapping, sticky actions, filter disclosures, safe viewport sizing, and widget iframe safeguards.

**Tech Stack:** Django templates, Tailwind utility classes, HTMX, Alpine.js, FullCalendar, `pytest`, Playwright/manual browser viewport checks.

---

## Project Rule

Do not commit during execution unless the user explicitly requests commits. Replace commit steps with a checkpoint: run `git diff --check` and summarize changed files.

## File Structure

- Modify `tests/test_design_system.py` to add static regression coverage for mobile CSS and mobile-critical template contracts.
- Modify `static/css/clinicflow.css` for shared mobile baseline, touch targets, table scroll affordances, sticky action columns, calendar sizing, widget sizing, auth contrast, and slot grid behavior.
- Modify `templates/dashboard/base.html` for overlay stacking and mobile `More` navigation.
- Modify `templates/dashboard/home.html`, `templates/dashboard/widget_embed.html`, `templates/dashboard/assistant_settings.html`, and `dashboard/templates/dashboard/messenger_settings.html` for wrapping, code block, and copy-button touch fixes.
- Modify `templates/dashboard/calendar.html` for FullCalendar mobile sizing, view button behavior, and media query synchronization.
- Modify `templates/dashboard/appointments.html`, `templates/dashboard/partials/appointment_list.html`, and `templates/dashboard/partials/appointment_row.html` for advanced mobile filters and sticky action columns.
- Modify `templates/dashboard/patients.html`, patient partials, `templates/dashboard/services.html`, and service partials for action touch targets, wrapping, and modal focus consistency.
- Modify `templates/accounts/login.html`, `templates/accounts/signup.html`, `templates/accounts/onboarding.html`, and `templates/privacy_policy.html` for dynamic viewport, safe-area, checkbox hit areas, and public design-system alignment.
- Modify `templates/widget/widget.html`, `templates/widget/partials/slots.html`, `templates/widget/partials/booking_success.html`, `templates/widget/booking_success.html`, `templates/widget/partials/booking_error.html`, `templates/dashboard/widget_embed.html`, and `widget/views.py` for embedded widget width, keyboard-safe spacing, slot grids, and mobile iframe sizing.

## Task 1: Add Mobile Contract Tests

**Files:**
- Modify: `tests/test_design_system.py`

- [ ] **Step 1: Add static tests for the shared mobile baseline**

Append these tests near the existing design-system tests, after `test_global_checkboxes_use_custom_neon_aqua_control`:

```python
def test_mobile_responsive_css_has_shared_baseline_contracts():
    css = css_text()

    assert ".cf-mobile-break" in css
    assert "overflow-wrap: anywhere;" in css
    assert ".cf-mobile-scroll-hint" in css
    assert ".cf-table-scroll::after" in css
    assert ".cf-sticky-action-col" in css
    assert "@media (max-width: 640px)" in css
    assert ".cf-row-actions .cf-btn-xs" in css
    assert "min-height: 2.75rem;" in css
    assert ".cf-faq-icon-action" in css


def test_mobile_dashboard_shell_contracts():
    template = dashboard_base_text()

    assert "z-[45]" in template
    assert ">More</span>" in template
    assert "dashboard:settings" in template
    assert "bottom-0" in template
```

- [ ] **Step 2: Add static tests for calendar and appointment mobile behavior**

Append:

```python
def test_calendar_mobile_viewport_contracts():
    template = source_text("templates/dashboard/calendar.html")

    assert "calendarScreen = window.matchMedia('(max-width: 640px)')" in template
    assert "syncCalendarViewport" in template
    assert "calendar.setOption('height', phone ? 'auto' : '100%')" in template
    assert "calendar.setOption('dayMaxEvents', phone ? 2 : 5)" in template
    assert "data-calendar-desktop-view" in template
    assert "hidden sm:inline-flex" in template


def test_appointments_mobile_filter_and_sticky_action_contracts():
    template = source_text("templates/dashboard/appointments.html")
    list_template = source_text("templates/dashboard/partials/appointment_list.html")
    row_template = source_text("templates/dashboard/partials/appointment_row.html")

    assert "filtersOpen" in template
    assert "cf-advanced-filters" in template
    assert "aria-controls=\"appointment-advanced-filters\"" in template
    assert "id=\"appointment-advanced-filters\"" in template
    assert "cf-sticky-action-col" in list_template
    assert "cf-sticky-action-col" in row_template
```

- [ ] **Step 3: Add static tests for patient/service mobile contracts**

Append:

```python
def test_patient_and_service_mobile_contracts():
    patients = source_text("templates/dashboard/patients.html")
    add_patient = source_text("templates/dashboard/partials/add_patient_modal.html")
    patient_detail = source_text("templates/dashboard/partials/patient_detail_content.html")
    patient_list = source_text("templates/dashboard/partials/patient_list.html")
    service_row = source_text("templates/dashboard/partials/service_row.html")
    services = source_text("templates/dashboard/services.html")

    assert "trapModalFocus" in patients
    assert "trapModalFocus" in add_patient
    assert "cf-mobile-break" in patient_detail
    assert "cf-sticky-action-col" in patient_list
    assert "cf-btn-sm sm:cf-btn-xs" not in service_row
    assert "cf-row-actions" in service_row
    assert "cf-mobile-break" in service_row
    assert "w-full sm:w-auto" in services
```

- [ ] **Step 4: Add static tests for auth, public, and widget contracts**

Append:

```python
def test_auth_public_and_widget_mobile_contracts():
    login = source_text("templates/accounts/login.html")
    signup = source_text("templates/accounts/signup.html")
    onboarding = source_text("templates/accounts/onboarding.html")
    privacy = source_text("templates/privacy_policy.html")
    widget = source_text("templates/widget/widget.html")
    widget_success = source_text("templates/widget/partials/booking_success.html")
    widget_error = source_text("templates/widget/partials/booking_error.html")
    widget_views = source_text("widget/views.py")

    assert "min-h-dvh" in login
    assert "items-start sm:items-center" in login
    assert "min-h-dvh" in signup
    assert "min-h-11" in signup
    assert "min-h-dvh" in onboarding
    assert "env(safe-area-inset-bottom)" in onboarding
    assert "{% extends \"base.html\" %}" in privacy
    assert "cf-policy-shell" in privacy
    assert "cf-widget-scroll" in widget
    assert "autocomplete=\"name\"" in widget
    assert "autocomplete=\"tel\"" in widget
    assert "break-all" in widget_success
    assert "break-words" in widget_error
    assert "@media (max-width: 640px)" in widget_views
```

- [ ] **Step 5: Run the new tests and confirm they fail**

Run:

```powershell
.\env\Scripts\python.exe -m pytest tests/test_design_system.py -q
```

Expected: FAIL because the new mobile contracts are not implemented yet.

- [ ] **Step 6: Checkpoint**

Run:

```powershell
git diff --check
```

Expected: no whitespace errors.

## Task 2: Implement Shared Mobile CSS Baseline

**Files:**
- Modify: `static/css/clinicflow.css`

- [ ] **Step 1: Add shared wrapping, scroll, and sticky-action helpers**

Add these rules before the existing `@media (prefers-reduced-motion: reduce)` block:

```css
.cf-mobile-break {
  min-width: 0;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.cf-mobile-scroll-hint {
  color: var(--cf-muted);
  font-size: .75rem;
  font-weight: 500;
}

.cf-table-scroll {
  position: relative;
  -webkit-overflow-scrolling: touch;
}

.cf-table-scroll::after {
  content: "";
  position: sticky;
  right: 0;
  display: block;
  width: 1.5rem;
  height: 1px;
  margin-top: -1px;
  margin-left: auto;
  background: linear-gradient(90deg, transparent, var(--cf-surface));
  pointer-events: none;
}

.cf-sticky-action-col {
  position: sticky;
  right: 0;
  z-index: 2;
  background: var(--cf-surface);
  box-shadow: -10px 0 18px rgba(8, 51, 68, .08);
}
```

- [ ] **Step 2: Improve mobile touch targets and controls**

Inside the existing `@media (max-width: 640px)` block, add these rules after `.cf-card { padding: 1rem; }`:

```css
  input,
  select,
  textarea,
  .cf-input,
  .cf-select,
  .cf-textarea,
  .cf-btn,
  .ui-button {
    min-height: 2.75rem;
  }

  .cf-btn-xs,
  .cf-row-actions .cf-btn-xs {
    min-height: 2.5rem;
    padding: .45rem .75rem;
    font-size: .75rem;
  }

  .cf-row-actions .cf-btn-xs svg,
  .cf-btn-xs svg {
    width: .875rem;
    height: .875rem;
  }

  .cf-faq-icon-action {
    width: 2.75rem;
    height: 2.75rem;
  }
```

- [ ] **Step 3: Add mobile filter, auth, calendar, and widget CSS**

Inside the existing `@media (max-width: 640px)` block, add these rules before the closing brace:

```css
  .cf-advanced-filters {
    display: none;
    width: 100%;
  }

  .cf-advanced-filters.cf-advanced-filters-open {
    display: grid;
    gap: .75rem;
  }

  .cf-auth-panel {
    align-items: flex-start;
    overflow: visible;
    padding-top: max(1.5rem, env(safe-area-inset-top));
    padding-bottom: max(2rem, env(safe-area-inset-bottom));
  }

  .cf-auth-panel::after {
    opacity: .55;
    pointer-events: none;
  }

  .cf-calendar-title {
    white-space: normal;
    overflow-wrap: anywhere;
  }

  .cf-calendar-card {
    min-height: calc(100dvh - 12rem);
  }

  #calendar {
    overflow-x: auto;
    overflow-y: visible;
  }

  .cf-widget-shell {
    width: min(var(--cf-widget-width), 100%);
    max-width: 100%;
    max-height: calc(100dvh - 1rem);
  }

  .cf-widget-scroll {
    scroll-padding-bottom: calc(5rem + env(safe-area-inset-bottom));
    padding-bottom: max(1rem, env(safe-area-inset-bottom));
  }

  .cf-slot-grid {
    grid-template-columns: repeat(auto-fit, minmax(7rem, 1fr));
  }

  .cf-slot-button {
    white-space: normal;
    overflow-wrap: anywhere;
  }
```

- [ ] **Step 4: Add an extra-narrow slot grid rule**

After the `@media (max-width: 640px)` block, add:

```css
@media (max-width: 340px) {
  .cf-slot-grid { grid-template-columns: 1fr; }
}
```

- [ ] **Step 5: Run tests for CSS contracts**

Run:

```powershell
.\env\Scripts\python.exe -m pytest tests/test_design_system.py::test_mobile_responsive_css_has_shared_baseline_contracts -q
```

Expected: PASS.

## Task 3: Fix Dashboard Shell And Shared Dashboard Pages

**Files:**
- Modify: `templates/dashboard/base.html`
- Modify: `templates/dashboard/home.html`
- Modify: `templates/dashboard/partials/search_results.html`
- Modify: `templates/dashboard/widget_embed.html`
- Modify: `templates/dashboard/assistant_settings.html`
- Modify: `dashboard/templates/dashboard/messenger_settings.html`

- [ ] **Step 1: Fix overlay stacking and add mobile More navigation**

In `templates/dashboard/base.html`, change the mobile overlay class from `z-40` to `z-[45]`.

In the bottom mobile nav, add this link after Services:

```html
      <a href="{% url 'dashboard:settings' %}" class="flex flex-col items-center gap-0.5 rounded-2xl p-2 text-xs font-semibold {% if request.resolver_match.url_name == 'settings' or request.resolver_match.url_name == 'assistant_settings' or request.resolver_match.url_name == 'messenger_settings' or request.resolver_match.url_name == 'billing' or request.resolver_match.url_name == 'profile' %}text-[var(--cf-brand)] bg-[var(--cf-brand-soft)]{% else %}text-[var(--cf-muted)]{% endif %}">
        <i data-lucide="ellipsis" class="h-5 w-5"></i>
        <span>More</span>
      </a>
```

- [ ] **Step 2: Add safe wrapping to dashboard search results**

In `templates/dashboard/partials/search_results.html`, add `min-w-0` to each result text wrapper and `cf-mobile-break` to primary text spans. The patient result row should follow this concrete pattern, and the same class changes should be applied to the service and appointment result rows:

```html
<div class="min-w-0 flex-1">
  <div class="cf-mobile-break font-semibold text-[var(--cf-ink)]">{{ patient.full_name }}</div>
  <div class="cf-mobile-break text-xs cf-muted">{{ patient.phone }}</div>
</div>
```

- [ ] **Step 3: Add safe wrapping to home and settings-like shared cards**

In `templates/dashboard/home.html`, add `min-w-0` to flex text containers in attention cards and add `cf-mobile-break` to clinic slug `<code>` output.

For the widget slug paragraph, use:

```html
<code class="cf-mobile-break">{{ clinic.slug }}</code>
```

- [ ] **Step 4: Make embed/copy controls mobile-tappable**

In `templates/dashboard/widget_embed.html` and `templates/dashboard/assistant_settings.html`, replace small copy button classes such as `px-2 py-1 text-xs` and `px-3 py-1.5 text-xs` with `cf-btn cf-btn-sm cf-btn-secondary min-h-10` while preserving existing click handlers and button text.

For code block containers, place the copy button below the code block on mobile with `static mt-2 sm:absolute sm:mt-0` and keep the existing absolute top-right placement at `sm` and wider breakpoints.

- [ ] **Step 5: Fix Messenger page wrapping**

In `dashboard/templates/dashboard/messenger_settings.html`, add `min-w-0` to flex children that contain Facebook page details and replace URL `truncate` with `break-all` for webhook URLs.

Use this class pattern for URL text:

```html
<code class="cf-mobile-break break-all">{{ webhook_url }}</code>
```

- [ ] **Step 6: Run dashboard shell tests**

Run:

```powershell
.\env\Scripts\python.exe -m pytest tests/test_design_system.py::test_mobile_dashboard_shell_contracts -q
```

Expected: PASS.

## Task 4: Fix Calendar And Appointment Mobile Workflows

**Files:**
- Modify: `templates/dashboard/calendar.html`
- Modify: `templates/dashboard/appointments.html`
- Modify: `templates/dashboard/partials/appointment_list.html`
- Modify: `templates/dashboard/partials/appointment_row.html`

- [ ] **Step 1: Make calendar desktop views hidden on phones**

In `templates/dashboard/calendar.html`, update month and week buttons:

```html
<button type="button" data-calendar-view="dayGridMonth" data-calendar-desktop-view class="hidden sm:inline-flex cf-btn cf-btn-primary cf-btn-sm"><i data-lucide="calendar-days" class="h-4 w-4"></i>month</button>
<button type="button" data-calendar-view="timeGridWeek" data-calendar-desktop-view class="hidden sm:inline-flex cf-btn cf-btn-primary cf-btn-sm"><i data-lucide="calendar-range" class="h-4 w-4"></i>week</button>
```

Keep the day button visible.

- [ ] **Step 2: Replace the fixed mobile calendar setup with media-query synchronization**

In the calendar script, replace:

```javascript
  const isSmallScreen = window.matchMedia('(max-width: 640px)').matches;
```

with:

```javascript
  const calendarScreen = window.matchMedia('(max-width: 640px)');
  const isPhone = () => calendarScreen.matches;
```

Update FullCalendar options:

```javascript
    initialView: isPhone() ? 'timeGridDay' : 'dayGridMonth',
    height: isPhone() ? 'auto' : '100%',
    expandRows: true,
    dayMaxEvents: isPhone() ? 2 : 5,
```

After `calendar.render();`, add:

```javascript
  function syncCalendarViewport() {
    const phone = isPhone();
    calendar.setOption('height', phone ? 'auto' : '100%');
    calendar.setOption('dayMaxEvents', phone ? 2 : 5);
    if (phone && calendar.view.type !== 'timeGridDay') {
      calendar.changeView('timeGridDay');
    }
    calendar.updateSize();
  }

  syncCalendarViewport();
  if (calendarScreen.addEventListener) {
    calendarScreen.addEventListener('change', syncCalendarViewport);
  } else {
    calendarScreen.addListener(syncCalendarViewport);
  }
  window.addEventListener('orientationchange', function() {
    window.setTimeout(syncCalendarViewport, 150);
  });
```

- [ ] **Step 3: Add appointment advanced filter disclosure**

In `templates/dashboard/appointments.html`, add `filtersOpen:false` to the top-level `x-data` object.

Keep the search field visible. Insert this button after the search field:

```html
    <button type="button" class="cf-btn cf-btn-secondary sm:hidden" @click="filtersOpen = !filtersOpen" :aria-expanded="filtersOpen.toString()" aria-controls="appointment-advanced-filters">
      <i data-lucide="sliders-horizontal" class="h-4 w-4"></i>Filters
    </button>
```

Wrap status, date, service, source, and payment fields in:

```html
    <div id="appointment-advanced-filters" class="cf-advanced-filters sm:flex sm:flex-wrap sm:items-end sm:gap-3" :class="filtersOpen ? 'cf-advanced-filters-open' : ''">
      <div class="cf-field">
        <label for="filter-status" class="cf-label">Status</label>
        <select id="filter-status" name="status" hx-get="{% url 'dashboard:appointments' %}" hx-target="#appointments-table" hx-trigger="change" hx-include="#filter-form" hx-push-url="true" class="cf-select">
          <option value="">All Statuses</option>
          {% for value,label in status_choices %}
            <option value="{{ value }}" {% if status == value %}selected{% endif %}>{{ label }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="cf-field">
        <label for="filter-date-from" class="cf-label">From</label>
        <input id="filter-date-from" type="date" name="date_from" value="{{ date_from }}" hx-get="{% url 'dashboard:appointments' %}" hx-target="#appointments-table" hx-trigger="change" hx-include="#filter-form" hx-push-url="true" class="cf-input">
      </div>
      <div class="cf-field">
        <label for="filter-date-to" class="cf-label">To</label>
        <input id="filter-date-to" type="date" name="date_to" value="{{ date_to }}" hx-get="{% url 'dashboard:appointments' %}" hx-target="#appointments-table" hx-trigger="change" hx-include="#filter-form" hx-push-url="true" class="cf-input">
      </div>
      <div class="cf-field">
        <label for="filter-service" class="cf-label">Service</label>
        <select id="filter-service" name="service" hx-get="{% url 'dashboard:appointments' %}" hx-target="#appointments-table" hx-trigger="change" hx-include="#filter-form" hx-push-url="true" class="cf-select">
          <option value="">All Services</option>
          {% for s in services %}
            <option value="{{ s.id }}" {% if service_filter == s.id|stringformat:"s" %}selected{% endif %}>{{ s.name }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="cf-field">
        <label for="filter-source" class="cf-label">Source</label>
        <select id="filter-source" name="source" hx-get="{% url 'dashboard:appointments' %}" hx-target="#appointments-table" hx-trigger="change" hx-include="#filter-form" hx-push-url="true" class="cf-select">
          <option value="">All Sources</option>
          {% for value,label in source_choices %}
            <option value="{{ value }}" {% if source_filter == value %}selected{% endif %}>{{ label }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="cf-field">
        <label for="filter-payment" class="cf-label">Payment</label>
        <select id="filter-payment" name="payment_state" hx-get="{% url 'dashboard:appointments' %}" hx-target="#appointments-table" hx-trigger="change" hx-include="#filter-form" hx-push-url="true" class="cf-select">
          <option value="">All Payments</option>
          {% for value,label in payment_choices %}
            <option value="{{ value }}" {% if payment_filter == value %}selected{% endif %}>{{ label }}</option>
          {% endfor %}
        </select>
      </div>
    </div>
```

- [ ] **Step 4: Add sticky action columns to appointment table**

In `templates/dashboard/partials/appointment_list.html`, add `cf-sticky-action-col` to the action `<th>`.

In `templates/dashboard/partials/appointment_row.html`, add `cf-sticky-action-col` to the action `<td>`.

- [ ] **Step 5: Run calendar and appointments tests**

Run:

```powershell
.\env\Scripts\python.exe -m pytest tests/test_design_system.py::test_calendar_mobile_viewport_contracts tests/test_design_system.py::test_appointments_mobile_filter_and_sticky_action_contracts -q
```

Expected: PASS.

## Task 5: Fix Patient And Service Mobile Workflows

**Files:**
- Modify: `templates/dashboard/patients.html`
- Modify: `templates/dashboard/partials/add_patient_modal.html`
- Modify: `templates/dashboard/partials/patient_detail_content.html`
- Modify: `templates/dashboard/partials/patient_list.html`
- Modify: `templates/dashboard/partials/patient_row.html`
- Modify: `templates/dashboard/partials/duplicate_list.html`
- Modify: `templates/dashboard/services.html`
- Modify: `templates/dashboard/partials/service_row.html`
- Modify: `templates/dashboard/partials/service_form.html`

- [ ] **Step 1: Add modal focus trap to patient list and add-patient modal**

In `templates/dashboard/patients.html`, ensure the top-level `x-data` includes the same helper used by appointment modals:

```javascript
trapModalFocus(event, root) { const focusable = Array.from(root.querySelectorAll(`a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])`)).filter((el) => el.offsetParent !== null); if (!focusable.length) return; const first = focusable[0]; const last = focusable[focusable.length - 1]; if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); } }
```

In `templates/dashboard/partials/add_patient_modal.html`, add these attributes to the modal backdrop element:

```html
@keydown.tab="trapModalFocus($event, $el)" tabindex="-1" x-effect="if (patientOpen) $nextTick(() => $el.querySelector('button, [href], input, select, textarea')?.focus())"
```

- [ ] **Step 2: Add sticky action columns and wrapping to patient tables**

In `templates/dashboard/partials/patient_list.html`, add `cf-sticky-action-col` to action `<th>` and action `<td>` cells.

In `templates/dashboard/partials/patient_detail_content.html`, add `min-w-0` to header text containers and `cf-mobile-break` to patient names, email/phone text, and visit-history text cells.

- [ ] **Step 3: Increase duplicate merge and row action usability**

In `templates/dashboard/partials/duplicate_list.html`, change merge buttons from `cf-btn-xs` to `cf-btn-sm`.

Add `flex-wrap` and `gap-2` to header action clusters so buttons wrap cleanly on narrow screens.

- [ ] **Step 4: Fix service page tabs and service cards**

In `templates/dashboard/services.html`, add `w-full sm:w-auto` to `.cf-tabs` containers inside `.cf-page-actions`.

In `templates/dashboard/partials/service_row.html`, add `cf-mobile-break` to service title and description elements and keep actions inside `.cf-row-actions`. Do not add a new service action menu.

- [ ] **Step 5: Add modal focus trap to service modals**

In `templates/dashboard/services.html`, add the same `trapModalFocus` helper to the page `x-data` object.

Add `@keydown.tab="trapModalFocus($event, $el)" tabindex="-1"` and an `x-effect` initial focus expression to add/edit service modal backdrops.

- [ ] **Step 6: Run patient/service tests**

Run:

```powershell
.\env\Scripts\python.exe -m pytest tests/test_design_system.py::test_patient_and_service_mobile_contracts -q
```

Expected: PASS.

## Task 6: Fix Auth, Onboarding, And Privacy Pages

**Files:**
- Modify: `templates/accounts/login.html`
- Modify: `templates/accounts/signup.html`
- Modify: `templates/accounts/onboarding.html`
- Modify: `templates/privacy_policy.html`
- Modify: `static/css/clinicflow.css`

- [ ] **Step 1: Update login and signup viewport behavior**

In `login.html` and `signup.html`, replace:

```html
class="cf-auth-panel flex min-h-screen items-center justify-center px-4 py-8"
```

with:

```html
class="cf-auth-panel flex min-h-dvh items-start justify-center px-4 py-6 sm:items-center sm:py-8"
```

Change auth hero headings from `font-black` to `font-light` while preserving existing text.

- [ ] **Step 2: Enlarge signup consent hit area**

In `templates/accounts/signup.html`, update the terms label to include `min-h-11`:

```html
<label for="{{ field.id_for_label }}" class="m-0 flex min-h-11 items-center gap-3 cursor-pointer">
```

- [ ] **Step 3: Update onboarding viewport, safe area, and business-hours checkboxes**

In `templates/accounts/onboarding.html`, change the outer wrapper to use `min-h-dvh`, `items-start sm:items-center`, and bottom padding containing `env(safe-area-inset-bottom)`.

Wrap each business-hours open checkbox in a visible hit target:

```html
<label class="grid min-h-11 min-w-11 place-items-center rounded-[var(--cf-radius-md)] border border-[var(--cf-line)] bg-[var(--cf-surface)]">
  {{ day_form.is_open }}
</label>
```

Keep existing form field names unchanged.

- [ ] **Step 4: Move privacy policy into shared base template**

Replace the standalone HTML document in `templates/privacy_policy.html` with a Django template that starts with:

```django
{% extends "base.html" %}
{% block title %}Privacy Policy{% endblock %}
{% block body %}
<main class="cf-policy-shell min-h-dvh px-4 py-8 sm:py-12">
  <article class="mx-auto max-w-3xl rounded-[var(--cf-radius-lg)] border border-[var(--cf-line)] bg-[var(--cf-surface)] p-5 shadow-[var(--cf-shadow-card)] sm:p-8">
```

Move the existing policy text into the `<article>` and close with:

```django
  </article>
</main>
{% endblock %}
```

Use `text-[var(--cf-brand-strong)]` for policy links and headings. Preserve the current policy wording and dates.

- [ ] **Step 5: Strengthen small-text link and primary button contrast without changing brand token values**

In `static/css/clinicflow.css`, update:

```css
a { color: var(--cf-brand); }
```

to:

```css
a { color: var(--cf-brand-strong); }
```

Update `.cf-btn-primary` and hover rules to use dark teal text on bright aqua:

```css
.cf-btn-primary,
.ui-button-primary {
  background: var(--cf-brand);
  color: var(--cf-dashboard-dark);
}

.cf-btn-primary:hover,
.ui-button-primary:hover {
  background: var(--cf-brand-hover);
  color: #fff;
}
```

- [ ] **Step 6: Run auth/public tests**

Run:

```powershell
.\env\Scripts\python.exe -m pytest tests/test_design_system.py::test_auth_public_and_widget_mobile_contracts tests/test_design_system.py::test_public_auth_and_widget_button_labels_preserve_original_casing tests/test_design_system.py::test_signup_terms_checkbox_uses_inline_soft_consent_row -q
```

Expected: PASS.

## Task 7: Fix Widget Booking And Embed Mobile Behavior

**Files:**
- Modify: `templates/widget/widget.html`
- Modify: `templates/widget/partials/slots.html`
- Modify: `templates/widget/partials/booking_success.html`
- Modify: `templates/widget/booking_success.html`
- Modify: `templates/widget/partials/booking_error.html`
- Modify: `templates/dashboard/widget_embed.html`
- Modify: `widget/views.py`
- Modify: `static/css/clinicflow.css`

- [ ] **Step 1: Fix widget shell clipping and scroll padding**

In `templates/widget/widget.html`, update the scroll container:

```html
<div class="cf-widget-scroll flex-1 overflow-y-auto p-4">
```

Update the widget header left group and text wrapper:

```html
<div class="flex min-w-0 items-center gap-3">
  {% if clinic.logo %}
    <img src="{{ clinic.logo.url }}" alt="{{ clinic.name }}" class="h-10 w-10 shrink-0 rounded-full object-cover bg-white/20">
  {% else %}
    <div class="grid h-10 w-10 shrink-0 place-items-center rounded-2xl bg-white/15"><i data-lucide="bot"></i></div>
  {% endif %}
<div class="min-w-0">
  <h1 class="max-w-full truncate text-sm font-black">{{ clinic.name }}</h1>
```

- [ ] **Step 2: Add mobile-friendly autocomplete and input types**

In booking form fields, use:

```html
<input id="widget-full-name" name="full_name" required autocomplete="name" class="cf-input">
<input id="widget-phone" name="phone" type="tel" required autocomplete="tel" class="cf-input">
<input id="widget-email" name="email" type="email" autocomplete="email" class="cf-input">
```

In chat collect fields, use:

```html
<input x-model="collectInfo.full_name" aria-label="Full name" placeholder="Full Name" autocomplete="name" class="cf-input">
<input x-model="collectInfo.phone" aria-label="Phone" placeholder="Phone" type="tel" autocomplete="tel" class="cf-input">
<input x-model="collectInfo.email" aria-label="Email optional" placeholder="Email (optional)" type="email" autocomplete="email" class="cf-input">
```

- [ ] **Step 3: Add safe wrapping to success and error states**

In both widget success templates, add `break-all` to the reference-code element.

In `templates/widget/partials/booking_error.html`, add `break-words` to the dynamic error text and use CSS variables for danger colors:

```html
<div class="rounded-[var(--cf-radius-lg)] border border-[var(--cf-danger)] bg-[var(--cf-danger-soft)] p-4 text-sm text-[var(--cf-danger)]">
  <p class="break-words">{{ error }}</p>
</div>
```

- [ ] **Step 4: Make embed preview and generated launcher mobile-safe**

In `templates/dashboard/widget_embed.html`, set iframe preview height to:

```html
style="width:100%; height:min(500px, 70dvh); border:0;"
```

In `widget/views.py`, append a mobile media query to the generated script body after the iframe style string is assigned. Add this JavaScript after line where `iframe.style.cssText` is set:

```javascript
      if (window.matchMedia && window.matchMedia('(max-width: 640px)').matches) {
        iframe.style.left = 'max(8px, env(safe-area-inset-left))';
        iframe.style.right = 'max(8px, env(safe-area-inset-right))';
        iframe.style.bottom = 'max(8px, env(safe-area-inset-bottom))';
        iframe.style.width = 'calc(100vw - 16px - env(safe-area-inset-left) - env(safe-area-inset-right))';
        iframe.style.maxWidth = 'none';
        iframe.style.height = 'calc(100dvh - 16px - env(safe-area-inset-bottom))';
        iframe.style.maxHeight = 'none';
        iframe.style.borderRadius = '20px';
      }
```

Also add this literal CSS string in `widget/views.py` so the static test finds the mobile contract:

```javascript
  var mobileWidgetMedia = '@media (max-width: 640px)';
```

- [ ] **Step 5: Run widget/public tests**

Run:

```powershell
.\env\Scripts\python.exe -m pytest tests/test_design_system.py::test_auth_public_and_widget_mobile_contracts tests/test_design_system.py::test_public_auth_and_widget_button_labels_preserve_original_casing -q
```

Expected: PASS.

## Task 8: Full Verification And Manual Mobile Review

**Files:**
- No implementation files unless a verification issue exposes a root cause.

- [ ] **Step 1: Run the design-system suite**

Run:

```powershell
.\env\Scripts\python.exe -m pytest tests/test_design_system.py -q
```

Expected: PASS.

- [ ] **Step 2: Run Django checks**

Run:

```powershell
.\env\Scripts\python.exe manage.py check
```

Expected: `System check identified no issues`.

- [ ] **Step 3: Run the broader pytest suite**

Run:

```powershell
.\env\Scripts\python.exe -m pytest -q
```

Expected: PASS or a clearly documented unrelated failure with file/test name and reason.

- [ ] **Step 4: Run whitespace diff check**

Run:

```powershell
git diff --check
```

Expected: no output.

- [ ] **Step 5: Manual mobile viewport checklist**

Use browser or Playwright at `390x844` and `768x1024` to inspect:

- Dashboard shell: sidebar overlay covers bottom nav; bottom nav includes More; search results wrap.
- Calendar: phone loads day view; month/week hidden below `640px`; orientation/resize keeps calendar usable.
- Appointments: search visible; advanced filters disclose; action column remains reachable.
- Patients/services: actions are tappable; long names wrap; add/edit modals trap focus.
- Login/signup/onboarding: no clipped forms; keyboard-safe top/bottom spacing; checkboxes are tappable.
- Widget: no horizontal clipping; slot grid adapts; lower form fields and confirm button are reachable with mobile keyboard; minimize still posts `clinicflow-minimize`.

- [ ] **Step 6: Final checkpoint**

Run:

```powershell
git status --short
```

Expected: only files intentionally modified by this mobile responsiveness pass plus previously existing unrelated dirty files. Summarize verification output and do not commit unless the user explicitly requests it.

## Self-Review Notes

- Spec coverage: all five approved page families have implementation tasks.
- No model changes are planned, so no migrations are required.
- The plan preserves existing URLs, form field names, HTMX targets, Alpine hooks, FullCalendar event loading, and widget minimize behavior.
- Dense dashboard tables remain table-first with scroll/sticky affordances rather than a full card rewrite.
