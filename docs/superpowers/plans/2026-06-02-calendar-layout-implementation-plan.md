# Calendar Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework the dashboard calendar page into the approved screenshot-style layout with Service, Status, and Add appointment above and outside the calendar card while preserving KliniAssist colors, FullCalendar behavior, filters, appointment modal behavior, and tenant-safe server flows.

**Architecture:** This is a presentation-only change. The Django view and event/reschedule endpoints stay unchanged; `templates/dashboard/calendar.html` gains a new calendar header/tools structure and a small title-sync helper, while `static/css/kliniassist.css` adds scoped calendar layout and FullCalendar overrides.

**Tech Stack:** Django templates, Tailwind utility classes, `static/css/kliniassist.css`, Alpine.js, HTMX, FullCalendar 6.1.15, pytest.

---

## File Structure

- Modify `tests/test_design_system.py`: update the calendar design-system test and add a CSS contract test to assert the new screenshot-style layout hooks while preserving existing IDs and accessibility assertions.
- Modify `templates/dashboard/calendar.html`: restructure the page into outside top tools, then the calendar card containing header, legend, loading, calendar grid, and existing modal.
- Modify `static/css/kliniassist.css`: add scoped `.cf-calendar-*` styles and `#calendar .fc-*` overrides using existing KliniAssist variables.
- Use existing `dashboard/tests.py` calendar tests for behavior regression verification; no server-side code changes are planned.

Commits are intentionally omitted from task steps because this repository instructs agents not to commit unless explicitly requested.

---

### Task 1: Add Layout Contract Tests

**Files:**
- Modify: `tests/test_design_system.py:745-789`
- Test: `tests/test_design_system.py`

- [ ] **Step 1: Update the calendar design-system assertions**

Update `test_task_5_calendar_uses_single_neon_aqua_shell_and_accessible_modal` with these additional assertions after `assert "id=\"calendar\"" in template`:

```python
    assert "id=\"calendar-title\"" in template
    assert "cf-calendar-header" in template
    assert "cf-calendar-nav" in template
    assert "cf-calendar-views" in template
    assert "cf-calendar-tools" in template
    assert "cf-calendar-legend" in template
    assert "updateCalendarTitle" in template
    assert "datesSet" in template

    tools_index = template.index("class=\"cf-calendar-tools\"")
    header_index = template.index("class=\"cf-calendar-header\"")
    grid_index = template.index("<div id=\"calendar\"")
    assert tools_index < header_index < grid_index
```

Also add `test_task_5_calendar_css_supports_reference_grid_layout` after the calendar template test:

```python
def test_task_5_calendar_css_supports_reference_grid_layout():
    css = css_text()

    for selector in [
        ".cf-calendar-card",
        ".cf-calendar-header",
        ".cf-calendar-nav",
        ".cf-calendar-views",
        ".cf-calendar-title",
        ".cf-calendar-tools",
        ".cf-calendar-filters",
        ".cf-calendar-legend",
        "#calendar .fc-col-header-cell-cushion",
        "#calendar .fc-daygrid-day-number",
        "#calendar .fc-daygrid-day-frame",
        "#calendar .fc-event",
    ]:
        assert selector in css

    header = css_rule_block(".cf-calendar-header")
    assert "grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr)" in header

    title = css_rule_block(".cf-calendar-title")
    assert "text-align: center" in title
    assert "white-space: nowrap" in title

    event = css_rule_block("#calendar .fc-event")
    assert "border-radius: var(--cf-radius-sm)" in event
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```powershell
.\env\Scripts\python.exe -m pytest tests/test_design_system.py::test_task_5_calendar_uses_single_neon_aqua_shell_and_accessible_modal tests/test_design_system.py::test_task_5_calendar_css_supports_reference_grid_layout -q
```

Expected: FAIL because the calendar template hooks and `.cf-calendar-*` CSS rules are not yet present.

---

### Task 2: Restructure Calendar Template

**Files:**
- Modify: `templates/dashboard/calendar.html:15-54`
- Modify: `templates/dashboard/calendar.html:72-180`
- Test: `tests/test_design_system.py`

- [ ] **Step 1: Replace the card controls with screenshot-style header/tools layout**

In `templates/dashboard/calendar.html`, replace the opening calendar card content from the `<div x-data=... class="cf-card...">` through the `<div id="calendar"...></div>` with this structure. Keep the existing modal block immediately after it unchanged.

```html
<div x-data="{ detailOpen: false, trapCalendarFocus(event, root) { const focusable = Array.from(root.querySelectorAll(`a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])`)).filter((el) => el.offsetParent !== null); if (!focusable.length) return; const first = focusable[0]; const last = focusable[focusable.length - 1]; if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); } } }" @open-modal.window="detailOpen = true" @close-calendar-modal.window="detailOpen = false" @keydown.escape.window="detailOpen = false" class="cf-card cf-calendar-card flex flex-col" style="height: calc(100vh - 190px);">
  <div class="cf-calendar-header">
    <div class="cf-calendar-nav" aria-label="Calendar navigation">
      <button type="button" id="calendar-prev" class="cf-btn cf-btn-primary cf-btn-sm" aria-label="Previous calendar period"><i data-lucide="chevron-left" class="h-4 w-4"></i></button>
      <button type="button" id="calendar-next" class="cf-btn cf-btn-primary cf-btn-sm" aria-label="Next calendar period"><i data-lucide="chevron-right" class="h-4 w-4"></i></button>
      <button type="button" id="calendar-today" class="cf-btn cf-btn-primary cf-btn-sm">today</button>
    </div>
    <h2 id="calendar-title" class="cf-calendar-title" aria-live="polite">Calendar</h2>
    <div class="cf-calendar-views" aria-label="Calendar views">
      <button type="button" data-calendar-view="dayGridMonth" class="cf-btn cf-btn-primary cf-btn-sm">month</button>
      <button type="button" data-calendar-view="timeGridWeek" class="cf-btn cf-btn-primary cf-btn-sm">week</button>
      <button type="button" data-calendar-view="timeGridDay" class="cf-btn cf-btn-primary cf-btn-sm">day</button>
    </div>
  </div>

  <div class="cf-calendar-tools">
    <div class="cf-calendar-filters">
      <div class="cf-field">
        <label for="filter-service" class="cf-label">Service</label>
        <select id="filter-service" class="cf-select">
          <option value="">All Services</option>
          {% for service in clinic.services.all %}
            <option value="{{ service.id }}">{{ service.name }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="cf-field">
        <label for="filter-status" class="cf-label">Status</label>
        <select id="filter-status" class="cf-select">
          <option value="">All Statuses</option>
          {% for value, label in status_choices %}
            <option value="{{ value }}">{{ label }}</option>
          {% endfor %}
        </select>
      </div>
    </div>
    <a href="{% url 'dashboard:appointments' %}" class="cf-btn cf-btn-primary cf-btn-sm">Add appointment</a>
  </div>

  <div class="cf-calendar-legend" aria-label="Appointment status legend">
    <span class="cf-badge cf-status-booked">Booked</span>
    <span class="cf-badge cf-status-confirmed">Confirmed</span>
    <span class="cf-badge cf-status-completed">Completed</span>
    <span class="cf-badge cf-status-cancelled">Cancelled</span>
    <span class="cf-badge cf-status-no-show">No-show</span>
  </div>

  <div id="calendar-loading" role="status" aria-live="polite" class="mb-3 hidden rounded-2xl border border-[var(--cf-line)] bg-[var(--cf-surface-muted)] px-4 py-2 text-sm font-semibold text-[var(--cf-muted)]">Updating calendar...</div>
  <div id="calendar" class="min-h-0 flex-1" style="height: 100%;"></div>
```

- [ ] **Step 2: Add FullCalendar title sync in JavaScript**

In the script, after `const loadingEl = document.getElementById('calendar-loading');`, add:

```javascript
  const titleEl = document.getElementById('calendar-title');
  function updateCalendarTitle(title) {
    if (titleEl) titleEl.textContent = title;
  }
```

Inside the `new FullCalendar.Calendar(calendarEl, { ... })` options, after `editable: true,`, add:

```javascript
    datesSet: function(info) {
      updateCalendarTitle(info.view.title);
    },
```

- [ ] **Step 3: Run the focused template test and verify it passes**

Run:

```powershell
.\env\Scripts\python.exe -m pytest tests/test_design_system.py::test_task_5_calendar_uses_single_neon_aqua_shell_and_accessible_modal -q
```

Expected: PASS.

---

### Task 3: Add Scoped Calendar CSS

**Files:**
- Modify: `static/css/kliniassist.css` after `.cf-field .cf-label { margin-bottom: 0; }`
- Test: `tests/test_design_system.py`, `dashboard/tests.py`

- [ ] **Step 1: Add scoped calendar layout and FullCalendar styles**

Insert this CSS after the `.cf-field .cf-label { margin-bottom: 0; }` rule in `static/css/kliniassist.css`:

```css
.cf-calendar-card {
  padding: 1rem;
  gap: .75rem;
}

.cf-calendar-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
  gap: .75rem;
}

.cf-calendar-nav,
.cf-calendar-views {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: .35rem;
}

.cf-calendar-views { justify-content: flex-end; }

.cf-calendar-title {
  margin: 0;
  color: var(--cf-ink);
  font-size: clamp(1rem, 1.8vw, 1.25rem);
  font-weight: 800;
  letter-spacing: -.02em;
  text-align: center;
  white-space: nowrap;
}

.cf-calendar-tools {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  justify-content: space-between;
  gap: .75rem;
}

.cf-calendar-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: .75rem;
}

.cf-calendar-filters .cf-select { min-width: 11rem; }

.cf-calendar-legend {
  display: flex;
  flex-wrap: wrap;
  gap: .4rem;
}

#calendar {
  overflow: hidden;
  border: 1px solid var(--cf-line);
  border-radius: var(--cf-radius-sm);
  background: var(--cf-surface);
}

#calendar .fc-theme-standard td,
#calendar .fc-theme-standard th,
#calendar .fc-scrollgrid {
  border-color: var(--cf-line);
}

#calendar .fc-col-header-cell {
  background: var(--cf-bg-strong);
}

#calendar .fc-col-header-cell-cushion {
  padding: .45rem .25rem;
  color: var(--cf-muted);
  font-size: .75rem;
  font-weight: 800;
  letter-spacing: .08em;
  text-decoration: none;
  text-transform: uppercase;
}

#calendar .fc-daygrid-day-number {
  padding: .45rem .5rem;
  color: var(--cf-ink);
  font-size: .9375rem;
  font-weight: 700;
  text-decoration: none;
}

#calendar .fc-day-other {
  background: var(--cf-bg-strong);
}

#calendar .fc-day-other .fc-daygrid-day-number {
  color: var(--cf-faint);
  opacity: .65;
}

#calendar .fc-daygrid-day-frame {
  min-height: 6.25rem;
}

#calendar .fc-event {
  margin-inline: .25rem;
  border-radius: var(--cf-radius-sm);
  padding: .125rem .35rem;
  font-size: .75rem;
  font-weight: 700;
  line-height: 1.2;
}

#calendar .fc-daygrid-more-link {
  margin-inline: .25rem;
  color: var(--cf-brand);
  font-size: .75rem;
  font-weight: 700;
}

@media (max-width: 768px) {
  .cf-calendar-card { height: auto !important; min-height: calc(100vh - 160px); }

  .cf-calendar-header {
    grid-template-columns: 1fr;
    justify-items: stretch;
  }

  .cf-calendar-title { order: -1; }

  .cf-calendar-nav,
  .cf-calendar-views,
  .cf-calendar-tools,
  .cf-calendar-filters {
    justify-content: stretch;
  }

  .cf-calendar-nav .cf-btn,
  .cf-calendar-views .cf-btn,
  .cf-calendar-tools > .cf-btn,
  .cf-calendar-filters .cf-field {
    flex: 1 1 auto;
  }

  .cf-calendar-filters .cf-select { min-width: 100%; }

  #calendar .fc-daygrid-day-frame { min-height: 5rem; }
}
```

- [ ] **Step 2: Run the focused template/design test**

Run:

```powershell
.\env\Scripts\python.exe -m pytest tests/test_design_system.py::test_task_5_calendar_uses_single_neon_aqua_shell_and_accessible_modal tests/test_design_system.py::test_task_5_calendar_css_supports_reference_grid_layout tests/test_design_system.py::test_task_5_appointments_and_calendar_avoid_replaced_legacy_utilities -q
```

Expected: PASS.

---

### Task 4: Verify Calendar Behavior Regressions

**Files:**
- Verify: `dashboard/tests.py`
- Verify: `tests/test_design_system.py`

- [ ] **Step 1: Run calendar page behavior tests**

Run:

```powershell
.\env\Scripts\python.exe -m pytest dashboard/tests.py::test_calendar_page_uses_event_title_time_only dashboard/tests.py::test_calendar_page_uses_html_safe_alpine_focus_selector -q
```

Expected: PASS. These confirm the page still renders, `displayEventTime: false` remains, and the Alpine focus selector remains HTML-safe.

- [ ] **Step 2: Run calendar event and reschedule regression tests**

Run:

```powershell
.\env\Scripts\python.exe -m pytest dashboard/tests.py -k "calendar_events or calendar_reschedule or calendar_cancel_triggers_refetch_without_table_row_target or calendar_edit_triggers_refetch_without_table_row_target" -q
```

Expected: PASS. This confirms event JSON, filters, calendar modal refresh behavior, drag/drop reschedule validation, cross-clinic isolation, unavailable dates, break validation, and UTC input handling still work.

- [ ] **Step 3: Run Django system check**

Run:

```powershell
.\env\Scripts\python.exe manage.py check
```

Expected: `System check identified no issues`.

- [ ] **Step 4: Inspect git diff for scope**

Run:

```powershell
git diff -- templates/dashboard/calendar.html static/css/kliniassist.css tests/test_design_system.py docs/superpowers/specs/2026-06-02-calendar-layout-design.md docs/superpowers/plans/2026-06-02-calendar-layout-implementation-plan.md
```

Expected: Diff only includes the approved presentation-only calendar layout changes plus the approved spec/plan docs. No server-side endpoint, model, migration, or appointment validation changes should appear.

---

## Self-Review

- Spec coverage: The plan covers the approved option A header, visible filters/action row, scoped grid styling, mobile wrapping, title sync, existing IDs, modal accessibility, and behavior preservation.
- Placeholder scan: No placeholder implementation steps remain; every code-changing step includes concrete code.
- Type/name consistency: New template/CSS hooks consistently use `calendar-title`, `cf-calendar-header`, `cf-calendar-nav`, `cf-calendar-views`, `cf-calendar-tools`, `cf-calendar-filters`, `cf-calendar-legend`, and `updateCalendarTitle`.
- Scope check: No model, migration, route, endpoint, appointment validation, tenant-scoping, or color-palette change is included.
