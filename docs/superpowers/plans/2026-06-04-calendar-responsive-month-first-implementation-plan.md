# Calendar Responsive Month-First Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the dashboard Calendar month-first on every screen while improving responsive layout, loading/error UX, active view controls, touch-safe drag/drop, and FullCalendar design-system styling.

**Architecture:** Keep the existing Django template + FullCalendar integration. Add test coverage first, then update the calendar event payload with status/editability metadata, refine `templates/dashboard/calendar.html` JavaScript/markup, and centralize Calendar styling in `static/css/kliniassist.css` using existing Neon Aqua Clinical tokens.

**Tech Stack:** Django views/templates, FullCalendar 6, Alpine.js modal state, HTMX modal loading, Tailwind utility classes, `static/css/kliniassist.css`, pytest.

---

## File Structure

- `tests/test_design_system.py`: Static contracts for month-first behavior, responsive CSS, active view controls, loading/error UX, HTMX fallback hooks, and touch-safe drag/drop hooks.
- `dashboard/tests.py`: Calendar events API tests for status metadata and per-event editability.
- `dashboard/views.py`: Existing `calendar_events` endpoint gains `extendedProps.status` and per-event `editable` booleans.
- `templates/dashboard/calendar.html`: Month-first FullCalendar config, visible view controls, active view sync, loading/error messages, touch-safe editing, and HTMX detail failure fallback.
- `static/css/kliniassist.css`: Calendar card sizing, small-screen horizontal month scroll, active view buttons, legend dots, time-grid styling, and readable status token refinements.

No commits will be made unless the user explicitly asks for one.

## Task 1: Static Calendar Design Contracts

**Files:**
- Modify: `tests/test_design_system.py`

- [ ] **Step 1: Replace the month/mobile viewport contract test**

Replace `test_calendar_mobile_viewport_contracts` with this code:

```python
def test_calendar_mobile_viewport_contracts():
    template = source_text("templates/dashboard/calendar.html")
    css = css_text()
    mobile_css = css_media_block("max-width: 640px")

    assert "calendarScreen = window.matchMedia('(max-width: 768px)')" in template
    assert "calendarCoarsePointer = window.matchMedia('(pointer: coarse)')" in template
    assert "const isPhone = () => calendarScreen.matches;" in template
    assert "const isCoarsePointer = () => calendarCoarsePointer.matches;" in template
    assert "initialView: 'dayGridMonth'" in template
    assert "initialView: isPhone() ? 'timeGridDay' : 'dayGridMonth'" not in template
    assert "calendar.changeView('timeGridDay')" not in template
    assert "syncCalendarViewport" in template
    assert "calendar.setOption('height', phone ? 'auto' : '100%')" in template
    assert "calendar.setOption('dayMaxEvents', phone ? 2 : 5)" in template
    assert "calendar.updateSize();" in template
    assert "calendarScreen.addEventListener('change', syncCalendarViewport)" in template
    assert "calendarScreen.addListener(syncCalendarViewport)" in template
    assert "window.addEventListener('orientationchange'" in template
    assert "window.setTimeout(syncCalendarViewport, 150)" in template
    assert "data-calendar-view=\"dayGridMonth\"" in template
    assert "data-calendar-view=\"timeGridWeek\"" in template
    assert "data-calendar-view=\"timeGridDay\"" in template
    assert "data-calendar-desktop-view" not in template
    assert "cf-calendar-desktop-view" not in template
    assert ".cf-calendar-view-button[aria-pressed=\"true\"]" in css
    assert ".cf-calendar-view-button[aria-pressed=\"false\"]" in css
    assert ".cf-calendar-grid-scroll" in css
    assert "min-width: 42rem;" in mobile_css
```

- [ ] **Step 2: Add a responsive CSS contract test**

Add this test after `test_calendar_mobile_viewport_contracts`:

```python
def test_calendar_responsive_css_collapses_header_filters_and_safe_month_scroll():
    css = css_text()
    tablet_css = css_media_block("max-width: 768px")
    mobile_css = css_media_block("max-width: 640px")

    card = css_rule_block(".cf-calendar-card")
    scroll = css_rule_block(".cf-calendar-grid-scroll")
    title = css_rule_block(".cf-calendar-title")
    legend_badge = css_rule_block(".cf-calendar-legend-badge")
    time_label = css_rule_block("#calendar .fc-timegrid-slot-label")
    time_event = css_rule_block("#calendar .fc-timegrid-event")

    assert "height: calc(100dvh - 15rem);" in card
    assert "min-height: 32rem;" in card
    assert "overflow: hidden;" in scroll
    assert "font-weight: 400;" in title
    assert "position: relative;" in legend_badge
    assert "font-variant-numeric: tabular-nums;" in time_label
    assert "border-radius: var(--cf-radius-sm);" in time_event
    assert "height: calc(100dvh - 8.5rem);" in tablet_css
    assert "min-height: calc(100dvh - 8.5rem);" in tablet_css
    assert ".cf-calendar-header" in tablet_css
    assert "grid-template-columns: 1fr;" in tablet_css
    assert ".cf-calendar-grid-scroll" in tablet_css
    assert "overflow-x: auto;" in tablet_css
    assert "min-width: 44rem;" in tablet_css
    assert ".cf-calendar-title" in mobile_css
    assert "white-space: normal;" in mobile_css
    assert "overflow-wrap: anywhere;" in mobile_css
    assert "min-width: 42rem;" in mobile_css
```

- [ ] **Step 3: Add a Calendar interaction contract test**

Add this test after the responsive CSS test:

```python
def test_calendar_interaction_contracts_for_loading_active_views_and_touch_drag():
    template = source_text("templates/dashboard/calendar.html")

    assert "aria-pressed=\"true\"" in template
    assert "aria-pressed=\"false\"" in template
    assert "syncCalendarViewButtons(info.view.type);" in template
    assert "button.setAttribute('aria-pressed', active ? 'true' : 'false');" in template
    assert "button.classList.toggle('cf-calendar-view-active', active);" in template
    assert "loading: function(isLoading)" in template
    assert "setCalendarBusy(isLoading);" in template
    assert "showCalendarError('Calendar events could not be loaded. Please try again.');" in template
    assert "eventAllow: function(dropInfo, draggedEvent)" in template
    assert "return isCalendarEventEditable(draggedEvent);" in template
    assert "editable: !isCoarsePointer()" in template
    assert "calendarCoarsePointer.addEventListener('change', syncCalendarEditability)" in template
    assert "calendarCoarsePointer.addListener(syncCalendarEditability)" in template
    assert "showCalendarDetailError" in template
    assert "htmx:responseError" in template
    assert "htmx:sendError" in template
```

- [ ] **Step 4: Update the mixed mobile viewport test for month-first Calendar**

In `test_mobile_responsive_calendar_and_widget_use_safe_viewports`, replace:

```python
    assert "initialView: isPhone() ? 'timeGridDay' : 'dayGridMonth'" in calendar
```

with:

```python
    assert "initialView: 'dayGridMonth'" in calendar
    assert "initialView: isPhone() ? 'timeGridDay' : 'dayGridMonth'" not in calendar
```

- [ ] **Step 5: Run static Calendar tests and verify red**

Run:

```powershell
.\env\Scripts\python.exe -m pytest tests/test_design_system.py::test_calendar_mobile_viewport_contracts tests/test_design_system.py::test_calendar_responsive_css_collapses_header_filters_and_safe_month_scroll tests/test_design_system.py::test_calendar_interaction_contracts_for_loading_active_views_and_touch_drag tests/test_design_system.py::test_mobile_responsive_calendar_and_widget_use_safe_viewports -q
```

Expected: FAIL because Calendar is still phone-day-first, CSS lacks the new scroll/time-grid/active-view contracts, and template lacks the new interaction hooks.

## Task 2: Calendar Events Metadata Contract

**Files:**
- Modify: `dashboard/tests.py`
- Modify: `dashboard/views.py`

- [ ] **Step 1: Write failing API metadata tests**

Add these tests after `test_calendar_events_title_shows_time_and_patient_only` in `dashboard/tests.py`:

```python
def test_calendar_events_include_status_metadata_and_editable_flag(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)

    response = client.get(reverse("dashboard:calendar_events"))

    assert response.status_code == 200
    data = response.json()
    assert data[0]["extendedProps"]["status"] == appointment.status
    assert data[0]["editable"] is True


def test_calendar_events_mark_completed_and_cancelled_as_not_editable(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)

    for blocked_status in [Appointment.STATUS_COMPLETED, Appointment.STATUS_CANCELLED]:
        appointment.status = blocked_status
        appointment.save(update_fields=["status"])

        response = client.get(reverse("dashboard:calendar_events"))

        assert response.status_code == 200
        data = response.json()
        assert data[0]["extendedProps"]["status"] == blocked_status
        assert data[0]["editable"] is False
```

- [ ] **Step 2: Run metadata tests and verify red**

Run:

```powershell
.\env\Scripts\python.exe -m pytest dashboard/tests.py::test_calendar_events_include_status_metadata_and_editable_flag dashboard/tests.py::test_calendar_events_mark_completed_and_cancelled_as_not_editable -q
```

Expected: FAIL with missing `extendedProps` or `editable` keys.

- [ ] **Step 3: Add event metadata in `dashboard/views.py`**

Inside the `for appointment in qs:` loop in `calendar_events`, insert this before `events.append(...)`:

```python
        is_reschedulable = appointment.status not in {
            Appointment.STATUS_COMPLETED,
            Appointment.STATUS_CANCELLED,
        }
```

Then add these keys to the event dictionary:

```python
                "editable": is_reschedulable,
                "extendedProps": {"status": appointment.status},
```

The event dictionary should include these keys near `className` and `url`:

```python
                "className": f"status-{appointment.status}",
                "editable": is_reschedulable,
                "extendedProps": {"status": appointment.status},
                "url": f"{reverse('dashboard:appointment_detail', args=[appointment.id])}?source=calendar",
```

- [ ] **Step 4: Run metadata tests and verify green**

Run:

```powershell
.\env\Scripts\python.exe -m pytest dashboard/tests.py::test_calendar_events_include_status_metadata_and_editable_flag dashboard/tests.py::test_calendar_events_mark_completed_and_cancelled_as_not_editable -q
```

Expected: PASS.

## Task 3: Month-First Calendar Template Behavior

**Files:**
- Modify: `templates/dashboard/calendar.html`

- [ ] **Step 1: Remove inline event cursor style and inline card height**

Remove this inline style block from `templates/dashboard/calendar.html`:

```html
<style>
  .fc-event { cursor: pointer; }
</style>
```

Change the Calendar card opening tag from:

```html
<div class="cf-card cf-calendar-card flex flex-col" style="height: calc(100vh - 240px);">
```

to:

```html
<div class="cf-card cf-calendar-card flex flex-col">
```

Change the calendar grid element from:

```html
<div id="calendar" class="min-h-0 flex-1" style="height: 100%;"></div>
```

to:

```html
<div id="calendar" class="cf-calendar-grid-scroll min-h-0 flex-1"></div>
```

- [ ] **Step 2: Make all view buttons visible and stateful**

Replace the `.cf-calendar-views` contents with:

```html
      <button type="button" data-calendar-view="dayGridMonth" aria-pressed="true" class="cf-btn cf-btn-sm cf-calendar-view-button cf-calendar-view-active"><i data-lucide="calendar-days" class="h-4 w-4"></i>month</button>
      <button type="button" data-calendar-view="timeGridWeek" aria-pressed="false" class="cf-btn cf-btn-sm cf-calendar-view-button"><i data-lucide="calendar-range" class="h-4 w-4"></i>week</button>
      <button type="button" data-calendar-view="timeGridDay" aria-pressed="false" class="cf-btn cf-btn-sm cf-calendar-view-button"><i data-lucide="calendar" class="h-4 w-4"></i>day</button>
```

- [ ] **Step 3: Add compact legend status dots**

Replace the legend badge markup with:

```html
    <span class="cf-badge cf-calendar-legend-badge cf-status-booked"><span class="cf-calendar-status-dot" aria-hidden="true"></span>Booked</span>
    <span class="cf-badge cf-calendar-legend-badge cf-status-confirmed"><span class="cf-calendar-status-dot" aria-hidden="true"></span>Confirmed</span>
    <span class="cf-badge cf-calendar-legend-badge cf-status-completed"><span class="cf-calendar-status-dot" aria-hidden="true"></span>Completed</span>
    <span class="cf-badge cf-calendar-legend-badge cf-status-cancelled"><span class="cf-calendar-status-dot" aria-hidden="true"></span>Cancelled</span>
    <span class="cf-badge cf-calendar-legend-badge cf-status-no-show"><span class="cf-calendar-status-dot" aria-hidden="true"></span>No-show</span>
```

- [ ] **Step 4: Replace the Calendar JavaScript behavior**

In the existing `<script>`, keep the same outer `DOMContentLoaded` listener and replace the Calendar setup helpers/config with the following behavior:

```javascript
  const calendarScreen = window.matchMedia('(max-width: 768px)');
  const calendarCoarsePointer = window.matchMedia('(pointer: coarse)');
  const isPhone = () => calendarScreen.matches;
  const isCoarsePointer = () => calendarCoarsePointer.matches;
  const viewButtons = document.querySelectorAll('[data-calendar-view]');
  let calendarErrorVisible = false;
  function updateCalendarTitle(title) {
    if (titleEl) titleEl.textContent = title;
  }
  function setCalendarBusy(isBusy) {
    calendarEl.setAttribute('aria-busy', isBusy ? 'true' : 'false');
    if (!loadingEl) return;
    if (isBusy) {
      calendarErrorVisible = false;
      loadingEl.textContent = 'Updating calendar...';
      loadingEl.classList.remove('cf-calendar-message-error');
      loadingEl.classList.remove('hidden');
    } else if (!calendarErrorVisible) {
      loadingEl.classList.add('hidden');
    }
  }
  function showCalendarError(message) {
    calendarErrorVisible = true;
    if (loadingEl) {
      loadingEl.textContent = message;
      loadingEl.classList.add('cf-calendar-message-error');
      loadingEl.classList.remove('hidden');
    }
    window.dispatchEvent(new CustomEvent('toast-message', {
      detail: { message, type: 'error' }
    }));
  }
  function showCalendarDetailError() {
    document.getElementById('detail-modal-body').innerHTML = `
      <div class="cf-modal-body">
        <h2 id="appointment-detail-title" class="cf-modal-title">Appointment details unavailable</h2>
        <p class="cf-muted mt-2">We could not load this appointment. Close the modal and try again.</p>
      </div>
    `;
  }
  function isCalendarEventEditable(event) {
    const status = event.extendedProps ? event.extendedProps.status : null;
    return !isCoarsePointer() && status !== 'completed' && status !== 'cancelled';
  }
  function syncCalendarViewButtons(activeView) {
    viewButtons.forEach(function(button) {
      const active = button.dataset.calendarView === activeView;
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
      button.classList.toggle('cf-calendar-view-active', active);
    });
  }
```

Then update the FullCalendar config to include:

```javascript
    initialView: 'dayGridMonth',
    height: isPhone() ? 'auto' : '100%',
    expandRows: true,
    dayMaxEvents: isPhone() ? 2 : 5,
    displayEventTime: false,
    moreLinkText: '+{num} more',
    headerToolbar: false,
    editable: !isCoarsePointer(),
    eventAllow: function(dropInfo, draggedEvent) {
      return isCalendarEventEditable(draggedEvent);
    },
    loading: function(isLoading) {
      setCalendarBusy(isLoading);
    },
```

Inside `datesSet`, add:

```javascript
      syncCalendarViewButtons(info.view.type);
```

At the start of `eventDrop`, add:

```javascript
      if (!isCalendarEventEditable(info.event)) {
        info.revert();
        return;
      }
```

In the `events` fetch catch block, call the new visible error before `failureCallback(err)`:

```javascript
          showCalendarError('Calendar events could not be loaded. Please try again.');
          failureCallback(err);
```

Replace `syncCalendarViewport` with:

```javascript
  function syncCalendarViewport() {
    const phone = isPhone();
    calendar.setOption('height', phone ? 'auto' : '100%');
    calendar.setOption('dayMaxEvents', phone ? 2 : 5);
    calendar.updateSize();
  }
```

Add this editability sync helper after `syncCalendarViewport`:

```javascript
  function syncCalendarEditability() {
    calendar.setOption('editable', !isCoarsePointer());
  }
```

After the existing `calendarScreen` listener setup, add the coarse-pointer listener setup:

```javascript
  if (calendarCoarsePointer.addEventListener) {
    calendarCoarsePointer.addEventListener('change', syncCalendarEditability);
  } else {
    calendarCoarsePointer.addListener(syncCalendarEditability);
  }
```

Before the closing `});` of `DOMContentLoaded`, add scoped HTMX detail failure handling:

```javascript
  document.body.addEventListener('htmx:responseError', function(event) {
    if (event.detail.target && event.detail.target.id === 'detail-modal-body') {
      showCalendarDetailError();
    }
  });
  document.body.addEventListener('htmx:sendError', function(event) {
    if (event.detail.target && event.detail.target.id === 'detail-modal-body') {
      showCalendarDetailError();
    }
  });
```

- [ ] **Step 5: Run static interaction tests and verify template green where CSS is not involved**

Run:

```powershell
.\env\Scripts\python.exe -m pytest tests/test_design_system.py::test_calendar_mobile_viewport_contracts tests/test_design_system.py::test_calendar_interaction_contracts_for_loading_active_views_and_touch_drag -q
```

Expected: PASS after the template behavior is updated.

## Task 4: Calendar CSS And Design-System Styling

**Files:**
- Modify: `static/css/kliniassist.css`

- [ ] **Step 1: Strengthen status text tokens for tiny badges**

Change these root variables:

```css
  --cf-status-confirmed-text: var(--cf-info);
  --cf-status-no-show-text: var(--cf-muted);
```

to:

```css
  --cf-status-confirmed-text: var(--cf-brand-strong);
  --cf-status-no-show-text: #4a5870;
```

- [ ] **Step 2: Update Calendar card, title, and grid-scroll CSS**

Update the Calendar CSS blocks so they include:

```css
.cf-calendar-card {
  height: calc(100dvh - 15rem);
  min-height: 32rem;
  overflow: hidden;
  gap: .75rem;
  padding: 1rem;
}
```

```css
.cf-calendar-title {
  margin: 0;
  color: var(--cf-ink);
  font-size: clamp(1rem, 1.8vw, 1.25rem);
  font-weight: 400;
  letter-spacing: -.02em;
  text-align: center;
  white-space: nowrap;
}
```

```css
.cf-calendar-grid-scroll {
  min-height: 0;
  overflow: hidden;
}
```

- [ ] **Step 3: Add view button active/inactive CSS**

Add this near the other Calendar toolbar CSS:

```css
.cf-calendar-view-button[aria-pressed="true"],
.cf-calendar-view-button.cf-calendar-view-active {
  border-color: var(--cf-brand);
  background: var(--cf-brand);
  color: var(--cf-dashboard-dark);
}

.cf-calendar-view-button[aria-pressed="false"] {
  border-color: var(--cf-line);
  background: var(--cf-surface);
  color: var(--cf-muted);
}

.cf-calendar-view-button[aria-pressed="false"]:hover {
  border-color: var(--cf-brand-hover);
  background: var(--cf-brand-soft);
  color: var(--cf-brand-hover);
}
```

- [ ] **Step 4: Add compact legend-dot CSS**

Add this near `.cf-calendar-legend`:

```css
.cf-calendar-legend-badge {
  position: relative;
}

.cf-calendar-status-dot {
  width: .45rem;
  height: .45rem;
  border-radius: var(--cf-radius-pill);
  background: currentColor;
}
```

- [ ] **Step 5: Move event cursor and add time-grid styling**

Update `#calendar .fc-event` to include:

```css
  cursor: pointer;
```

Add these scoped FullCalendar rules after the existing day-grid event rules:

```css
#calendar .fc-timegrid-axis,
#calendar .fc-timegrid-slot-label {
  color: var(--cf-muted);
  font-size: .75rem;
  font-variant-numeric: tabular-nums;
}

#calendar .fc-timegrid-slot {
  height: 2.5rem;
}

#calendar .fc-timegrid-event {
  border-radius: var(--cf-radius-sm);
  padding: .125rem .35rem;
  font-size: .75rem;
  font-weight: 700;
  line-height: 1.2;
  box-shadow: var(--cf-shadow-subtle);
}

#calendar .fc-now-indicator-line {
  border-color: var(--cf-brand);
}

#calendar .fc-now-indicator-arrow {
  border-top-color: var(--cf-brand);
  border-bottom-color: var(--cf-brand);
}
```

- [ ] **Step 6: Update tablet and phone responsive Calendar CSS**

In `@media (max-width: 768px)`, keep the existing header stacking behavior and update/add these rules:

```css
  .cf-calendar-card {
    height: calc(100dvh - 8.5rem);
    min-height: calc(100dvh - 8.5rem);
  }

  #calendar.cf-calendar-grid-scroll {
    overflow-x: auto;
    overflow-y: visible;
    -webkit-overflow-scrolling: touch;
  }

  .cf-calendar-grid-scroll .fc {
    min-width: 44rem;
  }
```

In `@media (max-width: 640px)`, keep the existing mobile title wrapping and add:

```css
  .cf-calendar-grid-scroll .fc {
    min-width: 42rem;
  }
```

- [ ] **Step 7: Run CSS contract test and verify green**

Run:

```powershell
.\env\Scripts\python.exe -m pytest tests/test_design_system.py::test_calendar_responsive_css_collapses_header_filters_and_safe_month_scroll -q
```

Expected: PASS.

## Task 5: Calendar Verification

**Files:**
- No implementation files unless verification exposes a root cause.

- [ ] **Step 1: Run all targeted Calendar tests**

Run:

```powershell
.\env\Scripts\python.exe -m pytest tests/test_design_system.py::test_calendar_mobile_viewport_contracts tests/test_design_system.py::test_calendar_responsive_css_collapses_header_filters_and_safe_month_scroll tests/test_design_system.py::test_calendar_interaction_contracts_for_loading_active_views_and_touch_drag tests/test_design_system.py::test_mobile_responsive_calendar_and_widget_use_safe_viewports dashboard/tests.py::test_calendar_events_include_status_metadata_and_editable_flag dashboard/tests.py::test_calendar_events_mark_completed_and_cancelled_as_not_editable -q
```

Expected: PASS.

- [ ] **Step 2: Run full design-system tests**

Run:

```powershell
.\env\Scripts\python.exe -m pytest tests/test_design_system.py -q
```

Expected: PASS.

- [ ] **Step 3: Run focused dashboard Calendar tests**

Run:

```powershell
.\env\Scripts\python.exe -m pytest dashboard/tests.py -k calendar -q
```

Expected: PASS.

- [ ] **Step 4: Run Django system checks**

Run:

```powershell
.\env\Scripts\python.exe manage.py check
```

Expected: `System check identified no issues`.

- [ ] **Step 5: Run diff whitespace check**

Run:

```powershell
git diff --check
```

Expected: no whitespace errors; CRLF warnings are acceptable in this workspace.

- [ ] **Step 6: Note known unrelated full-suite blocker**

If running the full suite, expect the existing unrelated `widget/tests.py` chat-step state failures unless they have been fixed separately. Do not change widget/chat code as part of this Calendar task.

## Self-Review Notes

- Spec coverage: Month-first on all screens, safe horizontal scroll, responsive card sizing, filters/header stacking, loading/error UX, active views, touch-safe drag/drop, modal failure fallback, optional time-grid styling, status readability.
- Scope check: This is Calendar-only plus event metadata needed by Calendar drag/drop UX. No new product feature is introduced.
- Placeholder scan: No `TBD`, `TODO`, or unspecified implementation steps remain.
- Type/name consistency: Tests and implementation use `cf-calendar-grid-scroll`, `cf-calendar-view-button`, `cf-calendar-view-active`, `calendarCoarsePointer`, `syncCalendarViewButtons`, `syncCalendarEditability`, and `showCalendarDetailError` consistently.
