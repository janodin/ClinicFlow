# Table Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the heavy sticky table Actions treatment with quiet design-system action clusters in appointment and patient tables.

**Architecture:** Update static design tests first, then remove `cf-sticky-action-col` from affected table headers/cells and remove the sticky CSS helper if no longer used. Preserve existing `.cf-row-actions`, HTMX targets, Alpine modal triggers, URLs, labels, and dense table layout.

**Tech Stack:** Django templates, Tailwind utility classes, `static/css/kliniassist.css`, pytest static design-system tests.

---

## Task 1: Update Table Actions Contract

**Files:**
- Modify: `tests/test_design_system.py`

- [ ] **Step 1: Write the failing test update**

In `test_appointments_mobile_filter_and_sticky_action_contracts`, replace the sticky-column assertions:

```python
    assert "cf-sticky-action-col" in list_template
    assert "cf-sticky-action-col" in row_template
```

with:

```python
    assert "cf-sticky-action-col" not in list_template
    assert "cf-sticky-action-col" not in row_template
    assert "cf-row-actions cf-appointment-row-actions" in row_template
    assert "cf-appointment-view-action" in row_template
    assert "cf-btn-danger" in row_template
```

In `test_patient_and_service_mobile_contracts`, replace:

```python
    assert "cf-sticky-action-col" in patient_list
```

with:

```python
    patient_row = source_text("templates/dashboard/partials/patient_row.html")
    assert "cf-sticky-action-col" not in patient_list
    assert "cf-sticky-action-col" not in patient_row
    assert "cf-row-actions" in patient_list
    assert "cf-row-actions" in patient_row
    assert "cf-appointment-view-action" in patient_list
    assert "cf-service-edit-action" in patient_list
```

In `test_mobile_responsive_css_has_shared_baseline_contracts`, replace:

```python
    sticky = css_rule_block(".cf-sticky-action-col")
    assert "position: sticky;" in sticky
    assert "right: 0;" in sticky
    assert "box-shadow:" in sticky
```

with:

```python
    assert ".cf-sticky-action-col" not in css
```

- [ ] **Step 2: Run tests and verify red**

Run:

```powershell
.\env\Scripts\python.exe -m pytest tests/test_design_system.py::test_appointments_mobile_filter_and_sticky_action_contracts tests/test_design_system.py::test_patient_and_service_mobile_contracts tests/test_design_system.py::test_mobile_responsive_css_has_shared_baseline_contracts -q
```

Expected: FAIL because templates/CSS still contain `cf-sticky-action-col`.

## Task 2: Remove Sticky Action Treatment

**Files:**
- Modify: `templates/dashboard/partials/appointment_list.html`
- Modify: `templates/dashboard/partials/appointment_row.html`
- Modify: `templates/dashboard/partials/patient_list.html`
- Modify: `templates/dashboard/partials/patient_row.html`
- Modify: `static/css/kliniassist.css`

- [ ] **Step 1: Remove sticky classes from appointment table**

Change the Actions header in `appointment_list.html` from:

```html
<th scope="col" class="pr-5 text-right cf-sticky-action-col">Actions</th>
```

to:

```html
<th scope="col" class="pr-5 text-right">Actions</th>
```

Change the Actions cell in `appointment_row.html` from:

```html
<td class="pr-5 cf-sticky-action-col">
```

to:

```html
<td class="pr-5">
```

- [ ] **Step 2: Remove sticky classes from patient table**

Change the Actions header in `patient_list.html` from:

```html
<th class="cf-sticky-action-col pr-5 text-right">Actions</th>
```

to:

```html
<th class="pr-5 text-right">Actions</th>
```

Change the Actions cell in `patient_list.html` from:

```html
<td class="cf-sticky-action-col pr-5">
```

to:

```html
<td class="pr-5">
```

Change the Actions cell in `patient_row.html` from:

```html
<td class="cf-sticky-action-col pr-5">
```

to:

```html
<td class="pr-5">
```

- [ ] **Step 3: Remove sticky CSS helper**

Delete this block from `static/css/kliniassist.css`:

```css
.cf-sticky-action-col {
  position: sticky;
  right: 0;
  z-index: 2;
  background: var(--cf-surface);
  box-shadow: -10px 0 18px rgba(8, 51, 68, .08);
}
```

- [ ] **Step 4: Verify green**

Run:

```powershell
.\env\Scripts\python.exe -m pytest tests/test_design_system.py::test_appointments_mobile_filter_and_sticky_action_contracts tests/test_design_system.py::test_patient_and_service_mobile_contracts tests/test_design_system.py::test_mobile_responsive_css_has_shared_baseline_contracts -q
```

Expected: PASS.

## Task 3: Final Verification

**Files:**
- No implementation files unless verification exposes a root cause.

- [ ] **Step 1: Run full design-system tests**

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

- [ ] **Step 3: Run diff whitespace check**

Run:

```powershell
git diff --check
```

Expected: no whitespace errors; CRLF warnings are acceptable.

## Self-Review Notes

- Spec coverage: removes sticky action column and preserves quiet action clusters.
- HTMX/Alpine behavior is preserved because only class attributes and CSS helper are changed.
- Dense table layout is preserved; no card conversion or new menus are introduced.
