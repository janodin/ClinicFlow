# Widget Header Button Spacing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the spacing between the widget Home and Minimize buttons from 8px to 4px.

**Architecture:** This is a single Django template class adjustment backed by a widget template contract test. No JavaScript behavior, server-side code, or CSS file changes are needed.

**Tech Stack:** Django templates, Tailwind utility classes, Django `TestCase`, pytest.

---

## Approved Spec

Use `docs/superpowers/specs/2026-06-04-widget-header-button-spacing-design.md` as the source of truth.

Core requirements:

- Change only the Home/Minimize header control wrapper from `gap-2` to `gap-1`.
- Do not change other `gap-2` containers.
- Do not change button dimensions, icons, labels, behavior, JavaScript, storage, URLs, or server-side code.

## File Structure

- Modify: `widget/tests.py`
  - Update `test_widget_header_includes_home_and_minimize_controls` to assert the header control wrapper uses `gap-1`.
- Modify: `templates/widget/widget.html`
  - Change the Home/Minimize header control wrapper class from `flex items-center gap-2` to `flex items-center gap-1`.

No other implementation files should change. No migrations are needed.

### Task 1: Add Header Gap Contract Assertion

**Files:**

- Modify: `widget/tests.py`
- Test: `widget/tests.py::WidgetTests::test_widget_header_includes_home_and_minimize_controls`

- [ ] **Step 1: Write the failing assertion**

In `widget/tests.py`, update `test_widget_header_includes_home_and_minimize_controls` by adding this assertion after the `header = ...` line and before the existing button assertions:

```python
        self.assertIn('class="flex items-center gap-1"', header)
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest widget/tests.py::WidgetTests::test_widget_header_includes_home_and_minimize_controls -q }
```

Expected: FAIL because the current header control wrapper uses `gap-2`.

### Task 2: Change Header Control Gap

**Files:**

- Modify: `templates/widget/widget.html`
- Test: `widget/tests.py::WidgetTests::test_widget_header_includes_home_and_minimize_controls`

- [ ] **Step 1: Apply the minimal template change**

In `templates/widget/widget.html`, change only the Home/Minimize header control wrapper from:

```html
      <div class="flex items-center gap-2">
```

to:

```html
      <div class="flex items-center gap-1">
```

Do not change the booking step wrappers that also use `gap-2`.

- [ ] **Step 2: Run the focused test to verify it passes**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest widget/tests.py::WidgetTests::test_widget_header_includes_home_and_minimize_controls -q }
```

Expected: PASS.

### Task 3: Final Verification

**Files:**

- Verify: `widget/tests.py`
- Verify: `templates/widget/widget.html`
- Verify: Django system checks

- [ ] **Step 1: Run widget design tests**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest tests/test_design_system.py -k widget -q }
```

Expected: PASS.

- [ ] **Step 2: Run Django checks**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python manage.py check }
```

Expected output includes:

```text
System check identified no issues
```

- [ ] **Step 3: Inspect task-specific diff**

Run:

```powershell
git diff -- widget/tests.py templates/widget/widget.html docs/superpowers/specs/2026-06-04-widget-header-button-spacing-design.md docs/superpowers/plans/2026-06-04-widget-header-button-spacing-implementation-plan.md
```

Expected task-specific diff:

- `widget/tests.py` asserts `class="flex items-center gap-1"` in the widget header.
- `templates/widget/widget.html` changes the Home/Minimize control wrapper from `gap-2` to `gap-1`.
- No other Home/Minimize behavior changes are introduced.

- [ ] **Step 4: Leave changes uncommitted unless explicitly requested**

Do not commit unless the user explicitly asks. If the user explicitly requests a commit, use:

```powershell
git add widget/tests.py templates/widget/widget.html docs/superpowers/specs/2026-06-04-widget-header-button-spacing-design.md docs/superpowers/plans/2026-06-04-widget-header-button-spacing-implementation-plan.md
git commit -m "style: tighten widget header controls"
```

## Success Criteria

- Home and Minimize remain touch-friendly and accessible.
- Visual spacing between the two buttons is reduced from `gap-2` to `gap-1`.
- Other widget gaps and behaviors remain unchanged.
- Focused test, widget design tests, and `manage.py check` pass.
