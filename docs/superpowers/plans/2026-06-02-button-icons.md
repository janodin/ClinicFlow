# Button Icons Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add supplemental Lucide icons to all labeled KliniAssist `cf-btn` controls across dashboard, auth, booking, and widget templates.

**Architecture:** This is a template-only enhancement. Keep existing `cf-btn` CSS, labels, URLs, form methods, HTMX attributes, Alpine hooks, DOM IDs, and icon-only controls unchanged; insert semantic `<i data-lucide="..." class="h-4 w-4"></i>` elements before button text.

**Tech Stack:** Django templates, Tailwind utility classes, Lucide icons, pytest design-system tests.

---

## File Structure

- Modify `tests/test_design_system.py`: add a regression test that scans every app template for labeled `cf-btn` controls without Lucide icons, plus update existing exact-string assertions that currently assume icon-free button markup.
- Modify dashboard pages: `templates/dashboard/appointments.html`, `templates/dashboard/calendar.html`, `templates/dashboard/patients.html`, `templates/dashboard/services.html`, `templates/dashboard/home.html`, `templates/dashboard/settings.html`, `templates/dashboard/unavailable_dates.html`, `templates/dashboard/slot_preview.html`, `templates/dashboard/business_hours.html`, `templates/dashboard/assistant_settings.html`, and `dashboard/templates/dashboard/messenger_settings.html` only where a `cf-btn` lacks an icon.
- Modify dashboard partials: `templates/dashboard/partials/appointment_detail.html`, `appointment_form.html`, `appointment_list.html`, `appointment_row.html`, `patient_detail_content.html`, `patient_edit_modal_form.html`, `add_patient_modal.html`, `patient_row.html`, `patient_list.html`, `service_form.html`, `service_row.html`, `service_list.html`, `faq_row.html`, `duplicate_list.html`, `merge_confirm.html`, and `merge_success.html`.
- Modify public/auth/widget templates: `templates/accounts/login.html`, `templates/accounts/signup.html`, `templates/widget/widget.html`, `templates/widget/booking_success.html`, `templates/widget/partials/booking_success.html`, and `templates/widget/partials/booking_error.html`.
- Do not modify `static/css/clinicflow.css`; `.cf-btn` already has `inline-flex` and `gap: .5rem`.
- Do not commit during execution unless the user explicitly requests it.

## Task 1: Add Failing Button Icon Regression Tests

**Files:**
- Modify: `tests/test_design_system.py:1-80`
- Modify: `tests/test_design_system.py:394-399`
- Modify: `tests/test_design_system.py:701-706`
- Modify: `tests/test_design_system.py:952-955`

- [ ] **Step 1: Add scanner helpers and the failing regression test**

Add this code after `partial_text()` in `tests/test_design_system.py`:

```python
CF_BTN_TEMPLATE_PATHS = [
    "templates/dashboard/appointments.html",
    "templates/dashboard/calendar.html",
    "templates/dashboard/patients.html",
    "templates/dashboard/services.html",
    "templates/dashboard/home.html",
    "templates/dashboard/settings.html",
    "templates/dashboard/unavailable_dates.html",
    "templates/dashboard/slot_preview.html",
    "templates/dashboard/business_hours.html",
    "templates/dashboard/assistant_settings.html",
    "dashboard/templates/dashboard/messenger_settings.html",
    "templates/dashboard/partials/appointment_detail.html",
    "templates/dashboard/partials/appointment_form.html",
    "templates/dashboard/partials/appointment_list.html",
    "templates/dashboard/partials/appointment_row.html",
    "templates/dashboard/partials/patient_detail_content.html",
    "templates/dashboard/partials/patient_edit_modal_form.html",
    "templates/dashboard/partials/add_patient_modal.html",
    "templates/dashboard/partials/patient_row.html",
    "templates/dashboard/partials/patient_list.html",
    "templates/dashboard/partials/service_form.html",
    "templates/dashboard/partials/service_row.html",
    "templates/dashboard/partials/service_list.html",
    "templates/dashboard/partials/faq_row.html",
    "templates/dashboard/partials/duplicate_list.html",
    "templates/dashboard/partials/merge_confirm.html",
    "templates/dashboard/partials/merge_success.html",
    "templates/accounts/login.html",
    "templates/accounts/signup.html",
    "templates/widget/widget.html",
    "templates/widget/booking_success.html",
    "templates/widget/partials/booking_success.html",
    "templates/widget/partials/booking_error.html",
]

CF_BTN_TAG_RE = re.compile(
    r"<(?P<tag>a|button)\b(?P<attrs>[^>]*\bclass=\"[^\"]*\bcf-btn\b[^\"]*\"[^>]*)>"
    r"(?P<body>.*?)</(?P=tag)>",
    re.DOTALL,
)
HTML_TAG_RE = re.compile(r"<[^>]+>")
TEMPLATE_TAG_RE = re.compile(r"{[%{#].*?[#}%]}", re.DOTALL)


def visible_button_text(body):
    text = HTML_TAG_RE.sub(" ", body)
    text = TEMPLATE_TAG_RE.sub(" ", text)
    return " ".join(text.split())


def test_labeled_cf_buttons_include_supplemental_lucide_icons():
    missing = []
    for relative_path in CF_BTN_TEMPLATE_PATHS:
        template = source_text(relative_path)
        for match in CF_BTN_TAG_RE.finditer(template):
            body = match.group("body")
            label = visible_button_text(body)
            if not label or not re.search(r"[A-Za-z]", label):
                continue
            if "data-lucide=" not in body:
                missing.append(f"{relative_path}: {label}")

    assert missing == []
```

- [ ] **Step 2: Update exact assertions that currently assume no icons**

Replace the exact calendar header assertion in `test_calendar_page_header_groups_description_actions_and_filters()`:

```python
    assert "href=\"{% url 'dashboard:appointments' %}\" class=\"cf-btn cf-btn-primary\"" in template
    assert "data-lucide=\"calendar-plus\"" in template
    assert "Add appointment</a>" in template
```

Replace the appointment row assertion in `test_task_3_appointment_rows_keep_one_visible_primary_action()`:

```python
    assert template.count("class=\"cf-btn") == 1
    assert "data-lucide=\"eye\"" in template
    assert "View</a>" in template
    assert "appointment_edit" not in template
    assert "mode=cancel" not in template
    assert "mode=reschedule" not in template
```

Keep these calendar assertions in `test_task_5_calendar_uses_single_neon_aqua_shell_and_accessible_modal()` but add the icon assertion between them:

```python
    assert "href=\"{% url 'dashboard:appointments' %}\" class=\"cf-btn cf-btn-primary\"" in template
    assert "data-lucide=\"calendar-plus\"" in template
    assert "href=\"{% url 'dashboard:appointments' %}\" class=\"cf-btn cf-btn-primary cf-btn-sm\"" not in template
```

- [ ] **Step 3: Run the focused test and confirm it fails**

Run:

```powershell
.\env\Scripts\python.exe -m pytest tests/test_design_system.py::test_labeled_cf_buttons_include_supplemental_lucide_icons -q
```

Expected: `FAIL` with a `missing` list containing current buttons such as `Export CSV`, `Add appointment`, `Sign In`, and `Confirm Appointment`.

## Task 2: Add Icons To Dashboard Page Templates

**Files:**
- Modify: `templates/dashboard/appointments.html`
- Modify: `templates/dashboard/calendar.html`
- Modify: `templates/dashboard/patients.html`
- Modify: `templates/dashboard/services.html`
- Modify: `templates/dashboard/home.html`
- Modify: `templates/dashboard/settings.html`
- Modify: `templates/dashboard/unavailable_dates.html`
- Modify: `templates/dashboard/slot_preview.html`
- Modify: `templates/dashboard/business_hours.html`
- Modify: `templates/dashboard/assistant_settings.html`
- Modify: `dashboard/templates/dashboard/messenger_settings.html`

- [ ] **Step 1: Add semantic icons before labels in page-level buttons**

Use these exact icon mappings for page templates:

```text
Export CSV -> download
Add appointment -> calendar-plus
Create appointment -> calendar-plus
Cancel -> x-circle
today -> calendar-clock
month -> calendar-days
week -> calendar-range
day -> calendar
Check Duplicates -> scan-search
Add Patient -> user-plus
Add Service -> plus-circle
Add service -> plus-circle
New appointment -> calendar-plus
Save Changes -> save
Save Business Hours -> save
Add Unavailable Date -> calendar-off
Save Unavailable Date -> save
Delete -> trash-2
Preview Slots -> eye
Open -> external-link
Add FAQ -> plus-circle
```

Example replacements:

```html
<a ... class="cf-btn cf-btn-secondary"><i data-lucide="download" class="h-4 w-4"></i>Export CSV</a>
<button @click="open=true" class="cf-btn cf-btn-primary"><i data-lucide="calendar-plus" class="h-4 w-4"></i>Add appointment</button>
<button class="cf-btn cf-btn-primary"><i data-lucide="save" class="h-4 w-4"></i>Save Changes</button>
<button type="button" @click="deleteOpen=false" class="cf-btn cf-btn-secondary flex-1"><i data-lucide="x-circle" class="h-4 w-4"></i>Cancel</button>
```

Keep existing icons in `templates/dashboard/home.html`, `templates/dashboard/assistant_settings.html`, and `dashboard/templates/dashboard/messenger_settings.html`; only add icons to any `cf-btn` body that still lacks `data-lucide`.

- [ ] **Step 2: Run the scanner test**

Run:

```powershell
.\env\Scripts\python.exe -m pytest tests/test_design_system.py::test_labeled_cf_buttons_include_supplemental_lucide_icons -q
```

Expected: still `FAIL`, but missing entries from the dashboard page templates edited in this task should be gone.

## Task 3: Add Icons To Dashboard Partial Templates

**Files:**
- Modify: `templates/dashboard/partials/appointment_detail.html`
- Modify: `templates/dashboard/partials/appointment_form.html`
- Modify: `templates/dashboard/partials/appointment_list.html`
- Modify: `templates/dashboard/partials/appointment_row.html`
- Modify: `templates/dashboard/partials/patient_detail_content.html`
- Modify: `templates/dashboard/partials/patient_edit_modal_form.html`
- Modify: `templates/dashboard/partials/add_patient_modal.html`
- Modify: `templates/dashboard/partials/patient_row.html`
- Modify: `templates/dashboard/partials/patient_list.html`
- Modify: `templates/dashboard/partials/service_form.html`
- Modify: `templates/dashboard/partials/service_row.html`
- Modify: `templates/dashboard/partials/service_list.html`
- Modify: `templates/dashboard/partials/faq_row.html`
- Modify: `templates/dashboard/partials/duplicate_list.html`
- Modify: `templates/dashboard/partials/merge_confirm.html`
- Modify: `templates/dashboard/partials/merge_success.html`

- [ ] **Step 1: Add icons before labels in action partials**

Use these exact icon mappings for partial templates:

```text
Back / Back to Patients / Back to Booking -> arrow-left
View -> eye
Edit -> pencil
Update -> save
Add Note -> message-square-plus
Reschedule -> calendar-clock
Confirm Cancel -> ban
Save Changes -> save
Create Appointment -> calendar-plus
Create Service -> plus-circle
Close -> x-circle
Add Patient -> user-plus
Add Service -> plus-circle
Clear Filters -> x-circle
First -> chevrons-left
Previous -> chevron-left
Next -> chevron-right
Last -> chevrons-right
Archive -> archive
Restore -> rotate-ccw
Save -> save
Delete -> trash-2
Confirm Merge -> git-merge
Merge -> git-merge
Cancel -> x-circle
Check Again -> scan-search
```

Leave numeric pagination links and the current page `<span class="cf-btn ...">{{ num }}</span>` unchanged because there is no semantic action icon for a bare page number.

Example replacements:

```html
<a href="{% url 'dashboard:patients' %}" class="cf-btn cf-btn-secondary"><i data-lucide="arrow-left" class="h-4 w-4"></i>Back</a>
<a href="#" @click.prevent="detailOpen=true" hx-get="{% url 'dashboard:appointment_detail' appointment.id %}" hx-target="#detail-modal-body" class="cf-btn cf-btn-sm cf-btn-secondary"><i data-lucide="eye" class="h-4 w-4"></i>View</a>
<button type="submit" class="cf-btn cf-btn-primary flex-1"><i data-lucide="save" class="h-4 w-4"></i>{% if appointment %}Save Changes{% else %}Create Appointment{% endif %}</button>
<button type="submit" class="cf-btn cf-btn-sm cf-btn-danger"><i data-lucide="archive" class="h-4 w-4"></i>Archive</button>
```

- [ ] **Step 2: Run the scanner test**

Run:

```powershell
.\env\Scripts\python.exe -m pytest tests/test_design_system.py::test_labeled_cf_buttons_include_supplemental_lucide_icons -q
```

Expected: still `FAIL` only for remaining auth/widget templates if Task 4 has not run yet. If any dashboard partial remains in the missing list, add a semantic icon to that specific button before continuing.

## Task 4: Add Icons To Auth And Widget Templates

**Files:**
- Modify: `templates/accounts/login.html`
- Modify: `templates/accounts/signup.html`
- Modify: `templates/widget/widget.html`
- Modify: `templates/widget/booking_success.html`
- Modify: `templates/widget/partials/booking_success.html`
- Modify: `templates/widget/partials/booking_error.html`

- [ ] **Step 1: Add icons before public/auth labels**

Use these exact icon mappings:

```text
Sign In -> log-in
Create Account -> user-plus
Continue -> arrow-right
Confirm Appointment -> check-circle-2
Book Another Appointment -> calendar-plus
Back to Booking -> arrow-left
```

Example replacements:

```html
<button class="cf-btn cf-btn-primary w-full"><i data-lucide="log-in" class="h-4 w-4"></i>Sign In</button>
<button @click="goToStep3()" class="cf-btn w-full text-white disabled:opacity-50" :style="'background-color:' + accentColor" :disabled="!slot"><i data-lucide="arrow-right" class="h-4 w-4"></i>Continue</button>
<button type="submit" class="cf-btn w-full text-white" :style="'background-color:' + accentColor"><i data-lucide="check-circle-2" class="h-4 w-4"></i>Confirm Appointment</button>
```

- [ ] **Step 2: Run the scanner test and confirm it passes**

Run:

```powershell
.\env\Scripts\python.exe -m pytest tests/test_design_system.py::test_labeled_cf_buttons_include_supplemental_lucide_icons -q
```

Expected: `PASS`.

## Task 5: Run Full Focused Verification

**Files:**
- Verify: `tests/test_design_system.py`
- Verify: all modified templates

- [ ] **Step 1: Run the full design-system test file**

Run:

```powershell
.\env\Scripts\python.exe -m pytest tests/test_design_system.py -q
```

Expected: all tests pass. If exact-string failures appear, update only the assertions that changed because the templates now include `<i data-lucide="...">` elements; do not loosen unrelated design assertions.

- [ ] **Step 2: Run Django checks**

Run:

```powershell
.\env\Scripts\python.exe manage.py check
```

Expected: `System check identified no issues`.

- [ ] **Step 3: Inspect the final diff**

Run:

```powershell
git diff -- tests/test_design_system.py templates dashboard/templates docs/superpowers/specs/2026-06-02-button-icons-design.md docs/superpowers/plans/2026-06-02-button-icons.md
```

Expected: diff contains only supplemental icon markup, the new regression test, necessary assertion updates, and the design/plan documents. No URLs, methods, HTMX targets, Alpine hooks, DOM IDs, labels, or CSS button rules changed.

## Self-Review

- Spec coverage: Tasks 2-4 cover dashboard, auth, booking, and widget templates; Task 1 enforces supplemental Lucide icons on labeled `cf-btn` controls; Task 5 verifies template/system health.
- Placeholder scan: The plan contains no placeholder implementation steps.
- Type/signature consistency: Test helper names are defined before use, template paths are concrete, and icon classes use the agreed `h-4 w-4` sizing.
- Scope decision: Numeric pagination page-number controls remain unchanged because the approved design requires semantic, non-decorative icons and page numbers do not map cleanly to action icons.
