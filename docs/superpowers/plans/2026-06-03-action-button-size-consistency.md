# Action Button Size Consistency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all dashboard item-level action clusters use the same compact size as the Appointments table action buttons.

**Architecture:** Use the existing design-system CSS and templates. Promote the current Appointments-only compact row-action sizing to the shared `.cf-row-actions` selector, then apply that wrapper and `cf-btn-xs` to every item-level action cluster in scope.

**Tech Stack:** Django templates, Tailwind utility classes, shared `static/css/kliniassist.css`, pytest design-system tests.

**Repo Policy:** Do not commit unless the user explicitly requests a commit.

---

## File Structure

- Modify `static/css/kliniassist.css`: move Appointments compact action sizing from `.cf-appointment-row-actions` to `.cf-row-actions`, keeping existing mobile button-width behavior.
- Modify `templates/dashboard/partials/appointment_row.html`: keep action buttons visually unchanged while adding the shared `cf-row-actions` wrapper.
- Modify `templates/dashboard/partials/patient_list.html`: shrink Patients table actions to the Appointments action size.
- Modify `templates/dashboard/partials/patient_row.html`: shrink HTMX replacement patient-row actions to the Appointments action size.
- Modify `templates/dashboard/partials/patient_detail_content.html`: shrink appointment-history row actions to the Appointments action size.
- Modify `templates/dashboard/partials/service_row.html`: shrink service item action buttons to the Appointments action size.
- Modify `templates/dashboard/partials/faq_row.html`: shrink FAQ row action icons to the Appointments action size; leave edit-mode Save/Cancel controls unchanged because they are form controls, not row actions.
- Modify `templates/dashboard/partials/duplicate_list.html`: shrink duplicate-patient merge item actions to the Appointments action size; leave panel-level Refresh/Close controls unchanged.
- Modify `templates/dashboard/settings.html`: shrink unavailable-date delete row action in the settings tab.
- Modify `templates/dashboard/unavailable_dates.html`: shrink unavailable-date delete row action in the standalone page.
- Modify `tests/test_design_system.py`: add regression coverage that item-level action clusters use `cf-row-actions`, `cf-btn-xs`, and compact icons.

---

### Task 1: Add Failing Regression Tests

**Files:**
- Modify: `tests/test_design_system.py`
- Test: `tests/test_design_system.py`

- [ ] **Step 1: Add row-action size regression tests**

Append these helpers and tests near the existing appointment-row action tests:

```python
ROW_ACTION_TEMPLATE_PATHS = [
    "templates/dashboard/partials/appointment_row.html",
    "templates/dashboard/partials/patient_list.html",
    "templates/dashboard/partials/patient_row.html",
    "templates/dashboard/partials/patient_detail_content.html",
    "templates/dashboard/partials/service_row.html",
    "templates/dashboard/partials/faq_row.html",
    "templates/dashboard/settings.html",
    "templates/dashboard/unavailable_dates.html",
]


def test_item_level_action_clusters_match_appointment_button_size():
    for relative_path in ROW_ACTION_TEMPLATE_PATHS:
        template = source_text(relative_path)
        assert "cf-row-actions" in template, relative_path

        for match in re.finditer(
            r"<(?P<tag>a|button)\b(?P<attrs>[^>]*\bclass=\"[^\"]*\bcf-btn\b[^\"]*\"[^>]*)>",
            template,
        ):
            attrs = match.group("attrs")
            surrounding = template[max(0, match.start() - 250) : match.start()]
            if "cf-row-actions" not in surrounding:
                continue
            assert "cf-btn-xs" in attrs, f"{relative_path}: {match.group(0)}"
            assert "cf-btn-sm" not in attrs, f"{relative_path}: {match.group(0)}"
            assert "!min-h-0" not in attrs, f"{relative_path}: {match.group(0)}"


def test_item_level_action_icons_use_compact_appointment_size():
    for relative_path in ROW_ACTION_TEMPLATE_PATHS:
        template = source_text(relative_path)
        for match in re.finditer(r"<i\b[^>]*data-lucide=\"[^\"]+\"[^>]*>", template):
            surrounding = template[max(0, match.start() - 300) : match.start()]
            if "cf-row-actions" not in surrounding:
                continue
            icon = match.group(0)
            assert "h-3 w-3" in icon, f"{relative_path}: {icon}"
            assert "shrink-0" in icon, f"{relative_path}: {icon}"
            assert 'aria-hidden="true"' in icon, f"{relative_path}: {icon}"
```

- [ ] **Step 2: Run the tests to verify they fail before implementation**

Run: `.\env\Scripts\python -m pytest tests/test_design_system.py::test_item_level_action_clusters_match_appointment_button_size tests/test_design_system.py::test_item_level_action_icons_use_compact_appointment_size -q`

Expected: FAIL because several row/action templates still use `cf-btn-sm`, custom padding, or lack `cf-row-actions`.

---

### Task 2: Promote Shared Row-Action CSS

**Files:**
- Modify: `static/css/kliniassist.css`
- Test: `tests/test_design_system.py`

- [ ] **Step 1: Replace Appointments-only compact selectors**

Change this CSS:

```css
.cf-appointment-row-actions .cf-btn-xs {
  min-height: 1.625rem;
  padding: .2rem .45rem;
  font-size: .6875rem;
}

.cf-appointment-row-actions .cf-btn-xs svg {
  width: .7rem;
  height: .7rem;
}
```

To this shared version:

```css
.cf-row-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: .5rem;
}

.cf-row-actions .cf-btn-xs {
  min-height: 1.625rem;
  padding: .2rem .45rem;
  font-size: .6875rem;
}

.cf-row-actions .cf-btn-xs svg {
  width: .7rem;
  height: .7rem;
}
```

- [ ] **Step 2: Update the existing CSS test expectations**

In `test_task_3_appointment_rows_surface_inline_actions`, replace Appointments-only selector assertions with shared selector assertions:

```python
assert "cf-row-actions" in template
assert ".cf-row-actions .cf-btn-xs" in stylesheet
assert "min-height: 1.625rem;" in stylesheet
assert "padding: .2rem .45rem;" in stylesheet
assert ".cf-row-actions .cf-btn-xs svg" in stylesheet
assert "width: .7rem;" in stylesheet
assert "height: .7rem;" in stylesheet
```

- [ ] **Step 3: Run the targeted CSS/template tests**

Run: `.\env\Scripts\python -m pytest tests/test_design_system.py::test_task_3_appointment_rows_surface_inline_actions tests/test_design_system.py::test_css_contains_cards_tables_and_badges -q`

Expected: PASS after CSS and appointment template updates are complete.

---

### Task 3: Update Templates to Shared Compact Actions

**Files:**
- Modify: `templates/dashboard/partials/appointment_row.html`
- Modify: `templates/dashboard/partials/patient_list.html`
- Modify: `templates/dashboard/partials/patient_row.html`
- Modify: `templates/dashboard/partials/patient_detail_content.html`
- Modify: `templates/dashboard/partials/service_row.html`
- Modify: `templates/dashboard/partials/faq_row.html`
- Modify: `templates/dashboard/partials/duplicate_list.html`
- Modify: `templates/dashboard/settings.html`
- Modify: `templates/dashboard/unavailable_dates.html`
- Test: `tests/test_design_system.py`

- [ ] **Step 1: Update Appointments row wrapper**

Use this wrapper in `appointment_row.html` so the existing visual reference participates in the shared selector:

```html
<div class="cf-row-actions cf-appointment-row-actions">
```

- [ ] **Step 2: Update Patients table row actions**

Use this compact action block in `patient_list.html`:

```html
<div class="cf-row-actions">
  <a href="{% url 'dashboard:patient_detail' patient.id %}" class="cf-btn cf-btn-xs cf-appointment-view-action"><i data-lucide="eye" class="h-3 w-3 shrink-0" aria-hidden="true"></i>View</a>
  <button @click="editOpen=true" hx-get="{% url 'dashboard:patient_edit' patient.id %}" hx-target="#edit-modal-body" class="cf-btn cf-btn-xs cf-btn-secondary cf-service-edit-action"><i data-lucide="pencil" class="h-3 w-3 shrink-0" aria-hidden="true"></i>Edit</button>
</div>
```

- [ ] **Step 3: Update HTMX patient row actions**

Use the same compact action block in `patient_row.html`:

```html
<div class="cf-row-actions">
  <a href="{% url 'dashboard:patient_detail' patient.id %}" class="cf-btn cf-btn-xs cf-appointment-view-action"><i data-lucide="eye" class="h-3 w-3 shrink-0" aria-hidden="true"></i>View</a>
  <button @click="editOpen=true" hx-get="{% url 'dashboard:patient_edit' patient.id %}" hx-target="#edit-modal-body" class="cf-btn cf-btn-xs cf-btn-secondary cf-service-edit-action"><i data-lucide="pencil" class="h-3 w-3 shrink-0" aria-hidden="true"></i>Edit</button>
</div>
```

- [ ] **Step 4: Update patient detail appointment-history action**

Use this compact action block in `patient_detail_content.html`:

```html
<div class="cf-row-actions">
  <button @click.prevent="detailOpen=true" hx-get="{% url 'dashboard:appointment_detail' appointment.id %}" hx-target="#detail-modal-body" class="cf-btn cf-btn-xs cf-appointment-view-action"><i data-lucide="eye" class="h-3 w-3 shrink-0" aria-hidden="true"></i>View</button>
</div>
```

- [ ] **Step 5: Update service item actions**

Use `cf-row-actions justify-start` on the service action container and convert each service action button to `cf-btn-xs` with compact icons:

```html
<div class="cf-row-actions mt-auto justify-start border-t border-[var(--cf-line)] pt-4">
```

Each service action button should follow this shape:

```html
class="cf-btn cf-btn-xs cf-btn-secondary cf-service-edit-action"
<i data-lucide="pencil" class="h-3 w-3 shrink-0" aria-hidden="true"></i>Edit
```

- [ ] **Step 6: Update FAQ view-mode actions**

Use this compact action wrapper and button size in `faq_row.html` view mode:

```html
<div class="cf-row-actions gap-1 shrink-0" x-show="!editing">
```

Each FAQ view-mode action button should use `cf-btn cf-btn-xs ...` and an icon like:

```html
<i data-lucide="pencil" class="h-3 w-3 shrink-0" aria-hidden="true"></i>
```

- [ ] **Step 7: Update unavailable-date row actions**

Use this compact action wrapper around each duplicate-patient merge action in `duplicate_list.html`:

```html
<div class="cf-row-actions shrink-0">
  <button hx-get="{% url 'dashboard:patient_merge' %}?primary_id={{ primary.id }}&duplicate_id={{ duplicate.id }}" hx-target="#duplicate-panel" hx-swap="innerHTML" class="cf-btn cf-btn-xs cf-btn-primary"><i data-lucide="git-merge" class="h-3 w-3 shrink-0" aria-hidden="true"></i>Merge</button>
</div>
```

- [ ] **Step 8: Update unavailable-date row actions**

Wrap both unavailable-date delete buttons in `settings.html` and `unavailable_dates.html` with `cf-row-actions justify-start` or `cf-row-actions`, and use this compact button shape:

```html
<button type="button" @click="deleteUrl='{% url 'dashboard:delete_unavailable_date' ud.id %}'; deleteOpen=true" class="cf-btn cf-btn-xs cf-btn-danger"><i data-lucide="trash-2" class="h-3 w-3 shrink-0" aria-hidden="true"></i>Delete</button>
```

- [ ] **Step 9: Run row-action tests**

Run: `.\env\Scripts\python -m pytest tests/test_design_system.py::test_item_level_action_clusters_match_appointment_button_size tests/test_design_system.py::test_item_level_action_icons_use_compact_appointment_size tests/test_design_system.py::test_task_3_appointment_rows_surface_inline_actions tests/test_design_system.py::test_service_row_toggle_button_uses_stateful_action_styles -q`

Expected: PASS.

---

### Task 4: Final Verification

**Files:**
- Test: `tests/test_design_system.py`

- [ ] **Step 1: Run full design-system tests**

Run: `.\env\Scripts\python -m pytest tests/test_design_system.py -q`

Expected: PASS.

- [ ] **Step 2: Run Django system check**

Run: `.\env\Scripts\python manage.py check`

Expected: PASS with no system check issues.

- [ ] **Step 3: Inspect changed files**

Run: `git diff -- static/css/kliniassist.css templates/dashboard/partials/appointment_row.html templates/dashboard/partials/patient_list.html templates/dashboard/partials/patient_row.html templates/dashboard/partials/patient_detail_content.html templates/dashboard/partials/service_row.html templates/dashboard/partials/faq_row.html templates/dashboard/settings.html templates/dashboard/unavailable_dates.html tests/test_design_system.py docs/superpowers/specs/2026-06-03-action-button-size-consistency-design.md docs/superpowers/plans/2026-06-03-action-button-size-consistency.md`

Expected: Diff only contains action-button consistency changes and the two planning documents.

---

## Self-Review

- Spec coverage: all scoped row/action clusters are covered by Tasks 2 and 3, with regression tests in Task 1.
- Placeholder scan: no placeholders or unresolved implementation instructions remain.
- Type/name consistency: the shared selector is consistently named `cf-row-actions`, and templates consistently use `cf-btn-xs` for scoped item-level actions.
