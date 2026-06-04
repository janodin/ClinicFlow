# Widget Home Button Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a compact widget header Home button that explicitly resets in-progress booking/chat UI state and returns to the widget home screen.

**Architecture:** This is a frontend-only Django template and Alpine.js change. The header gains an icon-only Home button that calls a local `goHome()` method, while `minimize()` remains state-preserving and separate.

**Tech Stack:** Django templates, Alpine.js, Lucide icons, Tailwind utility classes, Django `TestCase`, pytest.

---

## Approved Spec

Use `docs/superpowers/specs/2026-06-04-widget-home-button-design.md` as the source of truth.

Core requirements:

- Add Home button beside Minimize in `templates/widget/widget.html`.
- Home means start over and resets booking/chat UI draft state.
- Minimize remains state-preserving.
- No browser storage, server-side drafts, model changes, URL changes, appointment logic changes, or chat/n8n behavior changes.

## File Structure

- Modify: `widget/tests.py`
  - Add targeted template contract tests for the header controls and `goHome()` reset method.
  - Keep existing `test_widget_minimize_preserves_in_memory_state` intact.
- Modify: `templates/widget/widget.html`
  - Add the Home icon button before Minimize.
  - Add a `goHome()` Alpine method that resets local frontend state.
  - Keep `minimize()` from calling `goHome()` or setting `mode = 'home'`.

No other implementation files should change. No Django migrations are needed.

### Task 1: Add Header Home Control Contract Test

**Files:**

- Modify: `widget/tests.py`
- Test: `widget/tests.py::WidgetTests::test_widget_header_includes_home_and_minimize_controls`

- [ ] **Step 1: Write the failing test**

Add this test inside `class WidgetTests(TestCase)` in `widget/tests.py`, immediately after `test_widget_minimize_preserves_in_memory_state`:

```python
    def test_widget_header_includes_home_and_minimize_controls(self):
        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()

        header_start = content.index("<header")
        header_end = content.index("</header>", header_start)
        header = content[header_start:header_end]

        self.assertIn('@click="goHome()"', header)
        self.assertIn('aria-label="Go to widget home"', header)
        self.assertIn('data-lucide="home"', header)
        self.assertIn('@click="minimize()"', header)
        self.assertIn('aria-label="Minimize"', header)
        self.assertLess(header.index('@click="goHome()"'), header.index('@click="minimize()"'))
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest widget/tests.py::WidgetTests::test_widget_header_includes_home_and_minimize_controls -q }
```

Expected: FAIL because the header does not yet contain `goHome()` or `data-lucide="home"`.

### Task 2: Add goHome Reset Contract Test

**Files:**

- Modify: `widget/tests.py`
- Test: `widget/tests.py::WidgetTests::test_widget_home_button_resets_in_memory_state`

- [ ] **Step 1: Write the failing test**

Add this test inside `class WidgetTests(TestCase)` in `widget/tests.py`, immediately after `test_widget_header_includes_home_and_minimize_controls`:

```python
    def test_widget_home_button_resets_in_memory_state(self):
        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()
        selected_date = response.context["selected_date"].strftime("%Y-%m-%d")

        go_home_start = content.index("goHome() {")
        go_home_end = content.index("minimize()", go_home_start)
        go_home_block = content[go_home_start:go_home_end]

        expected_resets = [
            "this.mode = 'home';",
            "this.bookStep = 1;",
            "this.selectedService = '';",
            f"this.date = '{selected_date}';",
            "this.slot = '';",
            "this.chatTab = 'conversation';",
            "this.chatHistory = [];",
            "this.chatOptions = [];",
            "this.chatState = 'greeting';",
            "this.chatInput = '';",
            "this.faqQuery = '';",
            "this.collectInfo = { full_name: '', phone: '', email: '' };",
        ]
        for reset in expected_resets:
            with self.subTest(reset=reset):
                self.assertIn(reset, go_home_block)

        self.assertNotIn("localStorage", go_home_block)
        self.assertNotIn("sessionStorage", go_home_block)
        self.assertNotIn("fetch(", go_home_block)
        self.assertNotIn("htmx.ajax", go_home_block)

        minimize_start = content.index("minimize() {")
        minimize_end = content.index("startChat()", minimize_start)
        minimize_block = content[minimize_start:minimize_end]
        self.assertNotIn("goHome()", minimize_block)
        self.assertNotIn("this.mode = 'home'", minimize_block)
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest widget/tests.py::WidgetTests::test_widget_home_button_resets_in_memory_state -q }
```

Expected: FAIL with `ValueError: substring not found` for `goHome() {` because the method does not exist yet.

### Task 3: Add Home Button And goHome Method

**Files:**

- Modify: `templates/widget/widget.html`
- Test: `widget/tests.py::WidgetTests::test_widget_header_includes_home_and_minimize_controls`
- Test: `widget/tests.py::WidgetTests::test_widget_home_button_resets_in_memory_state`
- Test: `widget/tests.py::WidgetTests::test_widget_minimize_preserves_in_memory_state`

- [ ] **Step 1: Add the Home button before Minimize**

Change the header controls in `templates/widget/widget.html` from:

```html
      <div class="flex items-center gap-2">
        <button @click="minimize()" class="min-h-10 min-w-10 rounded-xl" aria-label="Minimize"><i data-lucide="minus" class="h-5 w-5"></i></button>
      </div>
```

to:

```html
      <div class="flex items-center gap-2">
        <button @click="goHome()" class="min-h-10 min-w-10 rounded-xl" aria-label="Go to widget home"><i data-lucide="home" class="h-5 w-5"></i></button>
        <button @click="minimize()" class="min-h-10 min-w-10 rounded-xl" aria-label="Minimize"><i data-lucide="minus" class="h-5 w-5"></i></button>
      </div>
```

- [ ] **Step 2: Add the `goHome()` method before `minimize()`**

In the Alpine object in `templates/widget/widget.html`, add this method between `back()` and `minimize()`:

```javascript
      goHome() {
        this.mode = 'home';
        this.bookStep = 1;
        this.selectedService = '';
        this.date = '{{ selected_date|date:"Y-m-d" }}';
        this.slot = '';
        this.chatTab = 'conversation';
        this.chatHistory = [];
        this.chatOptions = [];
        this.chatState = 'greeting';
        this.chatInput = '';
        this.faqQuery = '';
        this.collectInfo = { full_name: '', phone: '', email: '' };
      },
```

Do not change `minimize()` except to keep it immediately after `goHome()`. It should remain:

```javascript
      minimize() {
        if (window.parent !== window) {
          window.parent.postMessage({type: 'clinicflow-minimize'}, '*');
        }
      },
```

- [ ] **Step 3: Run focused Home control tests**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest widget/tests.py::WidgetTests::test_widget_header_includes_home_and_minimize_controls widget/tests.py::WidgetTests::test_widget_home_button_resets_in_memory_state widget/tests.py::WidgetTests::test_widget_minimize_preserves_in_memory_state -q }
```

Expected: PASS for all three tests.

### Task 4: Final Verification And Working Tree Review

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

- [ ] **Step 3: Optionally run the full widget test module and classify failures**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest widget/tests.py -q }
```

Expected in the current dirty worktree: the new Home/minimize tests pass, while the existing unrelated AI-first chat-flow failures may still fail. If failures occur, confirm they are not caused by `goHome()` or the header controls.

- [ ] **Step 4: Inspect the working tree**

Run:

```powershell
git status --short
```

Expected: the working tree may contain unrelated pre-existing changes. Do not revert them.

Run:

```powershell
git diff -- widget/tests.py templates/widget/widget.html docs/superpowers/specs/2026-06-04-widget-home-button-design.md docs/superpowers/plans/2026-06-04-widget-home-button-implementation-plan.md
```

Expected task-specific diff:

- `widget/tests.py` has the two new Home button tests.
- `templates/widget/widget.html` adds the Home header button and `goHome()` reset method.
- `minimize()` still posts `clinicflow-minimize` and does not reset mode or call `goHome()`.

- [ ] **Step 5: Leave changes uncommitted unless the user explicitly requests a commit**

The repository instructions require explicit user approval before committing. If the user explicitly requests a commit for this work, use:

```powershell
git add widget/tests.py templates/widget/widget.html docs/superpowers/specs/2026-06-04-widget-home-button-design.md docs/superpowers/plans/2026-06-04-widget-home-button-implementation-plan.md
git commit -m "feat: add widget home reset button"
```

If the user has not explicitly requested a commit, do not commit.

## Success Criteria

- Header shows Home immediately before Minimize.
- Home returns to the home screen and resets booking/chat UI draft state.
- Minimize remains state-preserving.
- No persistence or server calls are added for Home.
- Focused Home/minimize tests, widget design-system tests, and `manage.py check` pass.
