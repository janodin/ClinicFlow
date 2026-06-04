# Widget Minimize State Preservation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the patient's in-progress widget screen and typed values when they minimize and reopen the booking widget on the same host page.

**Architecture:** The parent embed script already hides and re-shows the same iframe instead of destroying it. The fix is to stop the iframe's internal Alpine component from resetting `mode` to `home` during `minimize()`, with a regression test that locks the contract.

**Tech Stack:** Django, Django templates, Alpine.js, HTMX, Django `TestCase`, pytest.

---

## Approved Spec

Use `docs/superpowers/specs/2026-06-04-widget-minimize-state-preservation-design.md` as the source of truth.

Core requirements:

- Same-page only state preservation.
- Preserve current booking/chat screen and typed but unsubmitted field values.
- Do not add `localStorage`, `sessionStorage`, database drafts, server-side drafts, models, or migrations.
- Keep the existing `kliniassist-minimize` parent message.
- Do not change booking validation, slot validation, patient matching, or appointment creation.

## File Structure

- Modify: `widget/tests.py`
  - Add one regression test to `WidgetTests` that inspects the rendered widget JavaScript `minimize()` block.
  - The test proves `minimize()` still emits `kliniassist-minimize` and no longer sets `this.mode = 'home'`.
- Modify: `templates/widget/widget.html`
  - Remove the `this.mode = 'home';` line from `minimize()`.
  - Keep the existing parent `postMessage` behavior unchanged.

No other files should change for the implementation. No Django model changes or migrations are needed.

### Task 1: Add Minimize State Regression Test

**Files:**

- Modify: `widget/tests.py`
- Test: `widget/tests.py::WidgetTests::test_widget_minimize_preserves_in_memory_state`

- [ ] **Step 1: Write the failing test**

Add this test inside `class WidgetTests(TestCase)` in `widget/tests.py`, after `test_widget_home_loads_without_doctor_controls`:

```python
    def test_widget_minimize_preserves_in_memory_state(self):
        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()

        minimize_start = content.index("minimize() {")
        minimize_end = content.index("startChat()", minimize_start)
        minimize_block = content[minimize_start:minimize_end]

        self.assertIn("kliniassist-minimize", minimize_block)
        self.assertNotIn("this.mode = 'home'", minimize_block)
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest widget/tests.py::WidgetTests::test_widget_minimize_preserves_in_memory_state -q }
```

Expected: FAIL because the current `minimize()` block contains `this.mode = 'home';`.

The failure should include this assertion detail:

```text
AssertionError: "this.mode = 'home'" unexpectedly found in ...
```

### Task 2: Remove The Reset From Minimize

**Files:**

- Modify: `templates/widget/widget.html`
- Test: `widget/tests.py::WidgetTests::test_widget_minimize_preserves_in_memory_state`

- [ ] **Step 1: Apply the minimal template change**

Change the `minimize()` method in `templates/widget/widget.html` from:

```javascript
      minimize() {
        if (window.parent !== window) {
          window.parent.postMessage({type: 'kliniassist-minimize'}, '*');
        }
        this.mode = 'home';
      },
```

to:

```javascript
      minimize() {
        if (window.parent !== window) {
          window.parent.postMessage({type: 'kliniassist-minimize'}, '*');
        }
      },
```

Do not add browser storage, draft persistence, or extra reset logic.

- [ ] **Step 2: Run the focused test to verify it passes**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest widget/tests.py::WidgetTests::test_widget_minimize_preserves_in_memory_state -q }
```

Expected: PASS.

- [ ] **Step 3: Run the widget app test file**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest widget/tests.py -q }
```

Expected: PASS for all widget tests.

### Task 3: Final Verification And Working Tree Review

**Files:**

- Verify: `widget/tests.py`
- Verify: `templates/widget/widget.html`
- Verify: `tests/test_design_system.py`
- Verify: Django system checks

- [ ] **Step 1: Run widget-related design-system tests**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest tests/test_design_system.py -k widget -q }
```

Expected: PASS.

- [ ] **Step 2: Run Django system checks**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python manage.py check }
```

Expected output includes:

```text
System check identified no issues
```

- [ ] **Step 3: Inspect the working tree**

Run:

```powershell
git status --short
```

Expected: only the intended implementation files and planning documents are changed by this work. Existing unrelated user changes may also appear and must not be reverted.

Run:

```powershell
git diff -- widget/tests.py templates/widget/widget.html docs/superpowers/specs/2026-06-04-widget-minimize-state-preservation-design.md docs/superpowers/plans/2026-06-04-widget-minimize-state-preservation-implementation-plan.md
```

Expected implementation diff:

- `widget/tests.py` has the new `test_widget_minimize_preserves_in_memory_state` test.
- `templates/widget/widget.html` removes only `this.mode = 'home';` from `minimize()`.

- [ ] **Step 4: Leave changes uncommitted unless the user explicitly requests a commit**

The repository instructions require explicit user approval before committing. If the user has explicitly requested a commit for this work, use:

```powershell
git add widget/tests.py templates/widget/widget.html docs/superpowers/specs/2026-06-04-widget-minimize-state-preservation-design.md docs/superpowers/plans/2026-06-04-widget-minimize-state-preservation-implementation-plan.md
git commit -m "fix: preserve widget state on minimize"
```

If the user has not explicitly requested a commit, do not commit.

## Success Criteria

- Reopening the same iframe after minimize resumes the current booking or chat screen.
- Typed but unsubmitted DOM input values remain intact because the iframe was hidden, not recreated.
- `minimize()` still sends `kliniassist-minimize` to the parent page.
- No persistent draft storage is introduced.
- Targeted widget tests, widget design-system tests, and `manage.py check` pass.
